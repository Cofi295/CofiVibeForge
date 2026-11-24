#!/usr/bin/env python3
"""Clean-Slate Diff & AST Forensics Auditor for AI Bug Fixes.

Blocks destructive AI debugging anti-patterns before completion:
1. Band-Aid Stacking: purely additive bugfix diffs that wrap broken code instead of deleting it.
2. Blind Error Masking: added `except Exception: pass`, bare `except: pass`, or `.catch(() => {})`.
3. Commented-Out Zombie Code & Orphan Top-Level Imports / Syntax Errors.
4. Producer-Consumer Key Drift (accurate static dict-return & local-var AST tracking, zero false positives).
5. Unclosed `subprocess.Popen`, missing Windows UTF-8 stdio reconfigure, and mock-masked critic gates.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DIFF_FILE_HEADER_RE = re.compile(r"^\+\+\+\s+b/(.+)$")
SWALLOWED_PY_RE = re.compile(
    r"^\+\s*except(?:\s+\(?[A-Za-z0-9_, ]*(?:Exception|BaseException)[A-Za-z0-9_, ]*\)?)?\s*:\s*(?:pass|\.\.\.)\s*(?:#.*)?$"
)
SWALLOWED_JS_RE = re.compile(r"^\+.*\.catch\(\s*\([^)]*\)\s*=>\s*\{\s*\}\s*\)")
COMMENTED_CODE_PY_RE = re.compile(
    r"^\+\s*#\s*(?:def\s+\w+|class\s+\w+|if\s+.+:|elif\s+.+:|for\s+.+:|while\s+.+:|return\b|raise\b|[A-Za-z_]\w*\s*=\s*.+)"
)
COMMENTED_CODE_JS_RE = re.compile(
    r"^\+\s*//\s*(?:const\s+\w+|let\s+\w+|var\s+\w+|function\s+\w+|if\s*\(|for\s*\(|return\b|[A-Za-z_$][\w$]*\s*=\s*.+;)"
)


def _run_cmd(cmd: list[str], cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, creationflags=WIN_NO_WINDOW,
    )


def _is_test_or_doc_path(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    name = Path(norm).name.lower()
    if norm.endswith((".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".lock")):
        return True
    if name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".spec.ts", ".test.js")):
        return True
    return "/tests/" in f"/{norm}/" or "/docs/" in f"/{norm}/"


def audit_diff_text(diff_text: str, *, mode: str = "bugfix") -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    current_file: str | None = None
    is_new_file = False
    added_code = deleted_code = consecutive_zombie = 0
    pending_except_header = False

    def flush_file_stats() -> None:
        nonlocal added_code, deleted_code, consecutive_zombie, pending_except_header
        if current_file and not is_new_file and not _is_test_or_doc_path(current_file) and mode == "bugfix":
            if added_code >= 8 and deleted_code == 0:
                issues.append({"code": "BAND_AID_STACKING_SUSPECT", "severity": "warning", "file": current_file, "line": 1, "message": f"Bugfix added {added_code} code lines and deleted 0 old lines in '{current_file}'. Verify you deleted broken legacy logic cleanly rather than stacking an override patch underneath."})
            elif deleted_code > 0 and added_code > (deleted_code * 3 + 20):
                issues.append({"code": "CODE_INFLATION_WARNING", "severity": "warning", "file": current_file, "line": 1, "message": f"Bugfix inflated '{current_file}' (+{added_code} / -{deleted_code} lines). Check whether straight-line simplification can replace nested branches."})
        added_code = deleted_code = consecutive_zombie = 0
        pending_except_header = False

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            flush_file_stats()
            current_file, is_new_file = None, False
            continue
        if raw_line.startswith("new file mode "):
            is_new_file = True
            continue
        m_hdr = DIFF_FILE_HEADER_RE.match(raw_line)
        if m_hdr:
            current_file = m_hdr.group(1).strip()
            continue
        if current_file is None or raw_line.startswith(("@@", "---", "+++")):
            consecutive_zombie = 0
            pending_except_header = False
            continue
        if raw_line.startswith("+"):
            body = raw_line[1:].strip()
            if body and not body.startswith(("#", "//", "/*", "*")):
                added_code += 1
            if SWALLOWED_PY_RE.match(raw_line) or SWALLOWED_JS_RE.match(raw_line):
                issues.append({"code": "SWALLOWED_EXCEPTION", "severity": "error", "file": current_file, "line": 1, "message": f"Blind exception swallowing detected in added diff: `{body}`."})
            if pending_except_header and re.match(r"^\+\s*(?:pass|\.\.\.)\s*(?:#.*)?$", raw_line):
                issues.append({"code": "SWALLOWED_EXCEPTION", "severity": "error", "file": current_file, "line": 1, "message": "Multi-line `except ...: pass` bandage detected; fix root cause or handle specific error explicitly."})
            pending_except_header = bool(re.match(r"^\+\s*except(?:\s+\(?[A-Za-z0-9_, ]*(?:Exception|BaseException)[A-Za-z0-9_, ]*\)?)?\s*:\s*(?:#.*)?$", raw_line))
            if COMMENTED_CODE_PY_RE.match(raw_line) or COMMENTED_CODE_JS_RE.match(raw_line):
                consecutive_zombie += 1
                if consecutive_zombie == 2:
                    issues.append({"code": "COMMENTED_ZOMBIE_CODE", "severity": "error", "file": current_file, "line": 1, "message": "Commented-out legacy code block detected in diff; delete obsolete code cleanly (Git preserves history)."})
            else:
                consecutive_zombie = 0
        elif raw_line.startswith("-"):
            body = raw_line[1:].strip()
            if body and not body.startswith(("#", "//", "/*", "*")):
                deleted_code += 1
            consecutive_zombie, pending_except_header = 0, False
        else:
            consecutive_zombie, pending_except_header = 0, False

    flush_file_stats()
    return issues


def _iter_own_nodes(fn: ast.AST) -> list[ast.AST]:
    """Traverse AST nodes directly owned by `fn` in source order, skipping nested defs/classes/lambdas."""
    nodes: list[ast.AST] = []
    stack: list[ast.AST] = list(reversed(getattr(fn, "body", [])))
    while stack:
        cur = stack.pop()
        nodes.append(cur)
        children = [c for c in ast.iter_child_nodes(cur) if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda))]
        stack.extend(reversed(children))
    return nodes


def _extract_dict_literal_keys(node: ast.Dict) -> set[str] | None:
    keys: set[str] = set()
    for k in node.keys:
        if k is None or not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            return None
        keys.add(k.value)
    return keys


def _extract_static_return_keys(fn: ast.AST) -> set[str] | None:
    local_dicts: dict[str, set[str]] = {}
    dynamic_vars: set[str] = set()
    returns: list[ast.Return] = []
    for sub in _iter_own_nodes(fn):
        if isinstance(sub, ast.Return):
            returns.append(sub)
        elif isinstance(sub, ast.Assign) and len(sub.targets) == 1:
            tgt = sub.targets[0]
            if isinstance(tgt, ast.Name):
                dkeys = _extract_dict_literal_keys(sub.value) if isinstance(sub.value, ast.Dict) else None
                if dkeys is not None and tgt.id not in dynamic_vars:
                    local_dicts.setdefault(tgt.id, set()).update(dkeys)
                else:
                    dynamic_vars.add(tgt.id)
            elif isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name):
                slc = tgt.slice
                if isinstance(slc, ast.Constant) and isinstance(slc.value, str) and tgt.value.id in local_dicts:
                    local_dicts[tgt.value.id].add(slc.value)
                else:
                    dynamic_vars.add(tgt.value.id)
        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and sub.value is not None:
            dkeys = _extract_dict_literal_keys(sub.value) if isinstance(sub.value, ast.Dict) else None
            if dkeys is not None and sub.target.id not in dynamic_vars:
                local_dicts.setdefault(sub.target.id, set()).update(dkeys)
            else:
                dynamic_vars.add(sub.target.id)
        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and isinstance(sub.func.value, ast.Name):
            vname = sub.func.value.id
            if sub.func.attr == "update":
                ukeys = _extract_dict_literal_keys(sub.args[0]) if (len(sub.args) == 1 and isinstance(sub.args[0], ast.Dict) and vname in local_dicts) else None
                if ukeys is not None:
                    local_dicts[vname].update(ukeys)
                else:
                    dynamic_vars.add(vname)
            elif sub.func.attr == "setdefault":
                if sub.args and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str) and vname in local_dicts:
                    local_dicts[vname].add(sub.args[0].value)
                else:
                    dynamic_vars.add(vname)

    keys: set[str] = set()
    for ret in returns:
        val = ret.value
        if val is None or (isinstance(val, ast.Constant) and val.value is None):
            continue
        if isinstance(val, ast.Dict):
            dkeys = _extract_dict_literal_keys(val)
            if dkeys is None:
                return None
            keys.update(dkeys)
        elif isinstance(val, ast.Name) and val.id in local_dicts and val.id not in dynamic_vars:
            keys.update(local_dicts[val.id])
        else:
            return None
    return keys or None


def _audit_producer_consumer_keys(rel_path: str, tree: ast.Module) -> list[dict[str, Any]]:
    scoped_fns: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scoped_fns.append(("", node))
        elif isinstance(node, ast.ClassDef):
            scoped_fns.extend((node.name, m) for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))

    func_return_keys: dict[tuple[str, str], set[str]] = {}
    for owner, fn in scoped_fns:
        rkeys = _extract_static_return_keys(fn)
        if rkeys:
            func_return_keys[(owner, fn.name)] = rkeys  # type: ignore[attr-defined]
    if not func_return_keys:
        return []

    issues: list[dict[str, Any]] = []
    for owner, fn in scoped_fns:
        own = _iter_own_nodes(fn)
        var_to_prod: dict[str, tuple[str, str]] = {}
        reassigned: set[str] = set()
        for sub in own:
            tname, val = None, None
            if isinstance(sub, ast.Assign) and len(sub.targets) == 1 and isinstance(sub.targets[0], ast.Name):
                tname, val = sub.targets[0].id, sub.value
            elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and sub.value is not None:
                tname, val = sub.target.id, sub.value
            if tname is None:
                continue
            key_ref: tuple[str, str] | None = None
            if isinstance(val, ast.Call):
                if isinstance(val.func, ast.Name) and ("", val.func.id) in func_return_keys:
                    key_ref = ("", val.func.id)
                elif owner and isinstance(val.func, ast.Attribute) and isinstance(val.func.value, ast.Name) and val.func.value.id == "self" and (owner, val.func.attr) in func_return_keys:
                    key_ref = (owner, val.func.attr)
            if key_ref is not None and tname not in reassigned:
                var_to_prod[tname] = key_ref
            else:
                var_to_prod.pop(tname, None)
                reassigned.add(tname)

        for sub in own:
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get" and isinstance(sub.func.value, ast.Name):
                vname = sub.func.value.id
                if vname in var_to_prod and sub.args and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                    k_queried = sub.args[0].value
                    prod_ref = var_to_prod[vname]
                    if k_queried not in func_return_keys[prod_ref]:
                        issues.append({"code": "PRODUCER_CONSUMER_KEY_DRIFT", "severity": "error", "file": rel_path, "line": getattr(sub, "lineno", 1), "message": f"Consumer reads `{vname}.get('{k_queried}')`, but producer `{prod_ref[1]}()` only returns keys {sorted(func_return_keys[prod_ref])}."})
    return issues


def audit_python_source(rel_path: str, text: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError as exc:
        return [{"code": "SYNTAX_ERROR", "severity": "error", "file": rel_path, "line": exc.lineno or 1, "message": f"SyntaxError: {exc.msg}"}]
    if Path(rel_path).name == "__init__.py":
        return issues

    imported: list[tuple[str, int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append((alias.asname or alias.name.split(".")[0], node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for alias in node.names:
                if alias.name != "*":
                    imported.append((alias.asname or alias.name, node.lineno, f"{node.module or ''}.{alias.name}".lstrip(".")))

    if imported:
        used_names: set[str] = set()
        all_dunder_strings: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        all_dunder_strings.update(e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                used_names.update(re.findall(r"[A-Za-z_]\w*", node.value))
        raw_lines = text.splitlines()
        for bound, lineno, full_name in imported:
            if bound.startswith("_") or bound in used_names or bound in all_dunder_strings:
                continue
            raw_line = raw_lines[lineno - 1] if 1 <= lineno <= len(raw_lines) else ""
            if "noqa" not in raw_line.lower():
                issues.append({"code": "ORPHAN_IMPORT", "severity": "error", "file": rel_path, "line": lineno, "message": f"Unused top-level import '{bound}' ({full_name}) left behind; remove orphan import cleanly."})

    if not _is_test_or_doc_path(rel_path):
        if "subprocess.Popen(" in text and not any(t in text for t in (".kill(", ".terminate(", "taskkill", "_kill_process_tree", "_kill_locked")):
            line_no = next((i for i, l in enumerate(text.splitlines(), 1) if "subprocess.Popen(" in l), 1)
            issues.append({"code": "UNCLOSED_SUBPROCESS_POPEN", "severity": "warning", "file": rel_path, "line": line_no, "message": "subprocess.Popen() used without visible process-tree cleanup (.kill/.terminate/taskkill)."})
        if "sys.stdout.write(" in text and "ensure_ascii=False" in text and "reconfigure" not in text:
            line_no = next((i for i, l in enumerate(text.splitlines(), 1) if "sys.stdout.write(" in l), 1)
            issues.append({"code": "STDIO_UTF8_RECONFIGURE_MISSING", "severity": "error", "file": rel_path, "line": line_no, "message": "sys.stdout.write with ensure_ascii=False requires sys.stdout.reconfigure(encoding='utf-8') on Windows."})

    if _is_test_or_doc_path(rel_path) and "monkeypatch.setattr" in text:
        for idx_l, raw_l in enumerate(text.splitlines(), start=1):
            if "monkeypatch.setattr" in raw_l and any(g in raw_l for g in ("audit_footage_hygiene", "audit_edit_timeline_and_screen", "audit_plan_package")):
                issues.append({"code": "MOCK_MASKED_CRITIC_GATE", "severity": "warning", "file": rel_path, "line": idx_l, "message": "Test mocks a core critic gate; pair with unmocked Producer-Consumer contract test or --verify-workspace."})

    issues.extend(_audit_producer_consumer_keys(rel_path, tree))
    return issues


def collect_repo_diff_and_files(repo: Path, explicit_files: list[str] | None = None) -> tuple[str, list[Path]]:
    cmd = ["git", "diff", "--no-color", "-U0", "HEAD", "--", *(explicit_files or [])]
    res = _run_cmd(cmd, cwd=repo)
    if res.returncode != 0:
        res = _run_cmd(["git", "diff", "--no-color", "-U0", "--", *(explicit_files or [])], cwd=repo)
    diff_text = res.stdout or ""
    if explicit_files:
        return diff_text, [(repo / f).resolve() for f in explicit_files if (repo / f).is_file()]

    status_res = _run_cmd(["git", "status", "--porcelain"], cwd=repo)
    touched: list[Path] = []
    for line in (status_res.stdout or "").splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip().strip('"')
        rel = rel.split(" -> ", 1)[1].strip() if " -> " in rel else rel
        candidate = (repo / rel).resolve()
        if candidate.is_file():
            touched.append(candidate)
    return diff_text, touched


def verify_real_workspace_contracts(repo: Path, workspace: Path) -> list[dict[str, Any]]:
    """Run unmocked Producer-Consumer contract & scale replay against a real workspace on disk."""
    ws = workspace.resolve()
    if not ws.is_dir():
        return [{"code": "WORKSPACE_NOT_FOUND", "severity": "error", "file": str(ws), "line": 1, "message": f"Target workspace directory does not exist: {ws}"}]
    if str(repo.resolve()) not in sys.path:
        sys.path.insert(0, str(repo.resolve()))
    try:
        from documentary.critic_loops import audit_footage_hygiene  # type: ignore
    except ImportError:
        return []

    job_payload: dict[str, Any] = {"id": ws.name, "editing_dna": {"director_mode": "v2", "preset_id": "forensic_noir_director_v2"}}
    vm_p = ws / "visual_manifest.json"
    if vm_p.is_file():
        vm = json.loads(vm_p.read_text(encoding="utf-8", errors="replace"))
        if isinstance(vm, dict) and isinstance(vm.get("channel_profile_id"), str):
            job_payload["channel_profile_id"] = vm["channel_profile_id"]
    rep = audit_footage_hygiene(ws, job_payload)
    if str(rep.get("status") or "").upper() == "PASSED":
        return []
    return [
        {"code": "REAL_WORKSPACE_CONTRACT_FAILURE", "severity": "error", "file": str(fail.get("path") or ws.name), "line": 1, "message": f"[{fail.get('beat_id')}] {fail.get('reason')}"}
        for fail in (rep.get("failures") or [])[:10] if isinstance(fail, dict)
    ]


def audit_repository(repo: Path, *, files: list[str] | None = None, mode: str = "bugfix", verify_workspace: Path | None = None) -> dict[str, Any]:
    repo = repo.resolve()
    diff_text, touched_files = collect_repo_diff_and_files(repo, files)
    issues = audit_diff_text(diff_text, mode=mode)
    for path in touched_files:
        if path.suffix.lower() == ".py":
            issues.extend(audit_python_source(path.relative_to(repo).as_posix(), path.read_text(encoding="utf-8", errors="replace")))
    if verify_workspace is not None:
        issues.extend(verify_real_workspace_contracts(repo, verify_workspace))

    trail_cli = shutil.which("trail")
    trail_note = (f"trail_cli_detected ({trail_cli})" if trail_cli else "trail_dir_present (run `trail check` before commit)") if (repo / ".trail").is_dir() else "not_indexed"
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {"passed": len(errors) == 0, "mode": mode, "touched_files": [p.relative_to(repo).as_posix() for p in touched_files], "trail_status": trail_note, "error_count": len(errors), "warning_count": len(warnings), "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit bugfix diff & touched files for Clean-Slate compliance.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Target git repository root.")
    parser.add_argument("--files", nargs="*", default=None, help="Optional subset of relative file paths.")
    parser.add_argument("--mode", choices=("bugfix", "feature"), default="bugfix", help="Audit mode (default: bugfix).")
    parser.add_argument("--verify-workspace", type=Path, default=None, help="Optional real workspace directory to run unmocked Producer-Consumer contract replay.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings (e.g. band-aid suspect) as non-zero exit.")
    parser.add_argument("--json", action="store_true", help="Output JSON report.")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"[clean_slate_audit] Repo directory not found: {args.repo}", file=sys.stderr)
        return 2

    report = audit_repository(args.repo, files=args.files, mode=args.mode, verify_workspace=args.verify_workspace)
    ok = report["passed"] and (not args.strict or report["warning_count"] == 0)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[clean_slate_audit] {'PASSED' if ok else 'FAILED'} ({report['mode']}) — touched {len(report['touched_files'])} file(s) | {report['error_count']} error(s), {report['warning_count']} warning(s) | trail={report['trail_status']}")
        for item in report["issues"]:
            print(f"  [{item['severity'].upper()}] {item['code']} @ {item['file']}:{item['line']} — {item['message']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
