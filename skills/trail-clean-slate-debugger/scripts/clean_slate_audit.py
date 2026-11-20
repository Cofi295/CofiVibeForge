#!/usr/bin/env python3
"""Clean-Slate Diff & AST Forensics Auditor for AI Bug Fixes.

Blocks the most destructive AI debugging anti-patterns before completion:
1. Band-Aid Stacking: purely additive bugfix diffs (many '+' lines, 0 '-' lines)
   that wrap/override broken code instead of deleting the broken lines cleanly.
2. Blind Error Masking: added `except Exception: pass`, bare `except: pass`, or `.catch(() => {})`.
3. Commented-Out Zombie Code: blocks of commented-out old code left in diffs.
4. Orphan Top-Level Imports & Syntax Errors in touched Python source files.
5. Optional Trail CLI check (`trail status` / `trail check`) when `.trail/` is present.
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
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=WIN_NO_WINDOW,
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
    added_code = 0
    deleted_code = 0
    consecutive_zombie = 0
    pending_except_header = False

    def flush_file_stats() -> None:
        nonlocal added_code, deleted_code, consecutive_zombie, pending_except_header
        if current_file and not is_new_file and not _is_test_or_doc_path(current_file) and mode == "bugfix":
            if added_code >= 8 and deleted_code == 0:
                issues.append(
                    {
                        "code": "BAND_AID_STACKING_SUSPECT",
                        "severity": "warning",
                        "file": current_file,
                        "line": 1,
                        "message": (
                            f"Bugfix added {added_code} code lines and deleted 0 old lines in '{current_file}'. "
                            "Verify you deleted broken legacy logic cleanly rather than stacking an override patch underneath."
                        ),
                    }
                )
            elif deleted_code > 0 and added_code > (deleted_code * 3 + 20):
                issues.append(
                    {
                        "code": "CODE_INFLATION_WARNING",
                        "severity": "warning",
                        "file": current_file,
                        "line": 1,
                        "message": (
                            f"Bugfix inflated '{current_file}' (+{added_code} / -{deleted_code} lines). "
                            "Check whether straight-line simplification can replace nested branches."
                        ),
                    }
                )
        added_code = 0
        deleted_code = 0
        consecutive_zombie = 0
        pending_except_header = False

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            flush_file_stats()
            current_file = None
            is_new_file = False
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
                issues.append(
                    {
                        "code": "SWALLOWED_EXCEPTION",
                        "severity": "error",
                        "file": current_file,
                        "line": 1,
                        "message": f"Blind exception swallowing detected in added diff: `{raw_line[1:].strip()}`.",
                    }
                )

            if pending_except_header and re.match(r"^\+\s*(?:pass|\.\.\.)\s*(?:#.*)?$", raw_line):
                issues.append(
                    {
                        "code": "SWALLOWED_EXCEPTION",
                        "severity": "error",
                        "file": current_file,
                        "line": 1,
                        "message": "Multi-line `except ...: pass` bandage detected; fix root cause or handle specific error explicitly.",
                    }
                )
            pending_except_header = bool(
                re.match(
                    r"^\+\s*except(?:\s+\(?[A-Za-z0-9_, ]*(?:Exception|BaseException)[A-Za-z0-9_, ]*\)?)?\s*:\s*(?:#.*)?$",
                    raw_line,
                )
            )

            if COMMENTED_CODE_PY_RE.match(raw_line) or COMMENTED_CODE_JS_RE.match(raw_line):
                consecutive_zombie += 1
                if consecutive_zombie == 2:
                    issues.append(
                        {
                            "code": "COMMENTED_ZOMBIE_CODE",
                            "severity": "error",
                            "file": current_file,
                            "line": 1,
                            "message": "Commented-out legacy code block detected in diff; delete obsolete code cleanly (Git preserves history).",
                        }
                    )
            else:
                consecutive_zombie = 0

        elif raw_line.startswith("-"):
            body = raw_line[1:].strip()
            if body and not body.startswith(("#", "//", "/*", "*")):
                deleted_code += 1
            consecutive_zombie = 0
            pending_except_header = False
        else:
            consecutive_zombie = 0
            pending_except_header = False

    flush_file_stats()
    return issues


def audit_python_source(rel_path: str, text: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError as exc:
        return [
            {
                "code": "SYNTAX_ERROR",
                "severity": "error",
                "file": rel_path,
                "line": exc.lineno or 1,
                "message": f"SyntaxError: {exc.msg}",
            }
        ]

    if Path(rel_path).name == "__init__.py":
        return issues

    imported: list[tuple[str, int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                imported.append((bound, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                imported.append((bound, node.lineno, f"{node.module or ''}.{alias.name}".lstrip(".")))

    if not imported:
        return issues

    used_names: set[str] = set()
    all_dunder_strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used_names.add(node.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            all_dunder_strings.add(elt.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Support string forward type annotations
            for token in re.findall(r"[A-Za-z_]\w*", node.value):
                used_names.add(token)

    for bound, lineno, full_name in imported:
        if bound.startswith("_"):
            continue
        if bound not in used_names and bound not in all_dunder_strings:
            # Check raw line for `# noqa` intentional import
            raw_lines = text.splitlines()
            raw_line = raw_lines[lineno - 1] if 1 <= lineno <= len(raw_lines) else ""
            if "noqa" in raw_line.lower():
                continue
            issues.append(
                {
                    "code": "ORPHAN_IMPORT",
                    "severity": "error",
                    "file": rel_path,
                    "line": lineno,
                    "message": f"Unused top-level import '{bound}' ({full_name}) left behind; remove orphan import cleanly.",
                }
            )
    return issues


def collect_repo_diff_and_files(repo: Path, explicit_files: list[str] | None = None) -> tuple[str, list[Path]]:
    cmd = ["git", "diff", "--no-color", "-U0", "HEAD", "--"]
    if explicit_files:
        cmd.extend(explicit_files)
    res = _run_cmd(cmd, cwd=repo)
    if res.returncode != 0:
        # Fallback for repos with no initial HEAD commit yet
        cmd_no_head = ["git", "diff", "--no-color", "-U0", "--"]
        if explicit_files:
            cmd_no_head.extend(explicit_files)
        res = _run_cmd(cmd_no_head, cwd=repo)
    diff_text = res.stdout or ""

    if explicit_files:
        touched = [(repo / f).resolve() for f in explicit_files if (repo / f).is_file()]
        return diff_text, touched

    status_res = _run_cmd(["git", "status", "--porcelain"], cwd=repo)
    touched = []
    for line in (status_res.stdout or "").splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip().strip('"')
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1].strip()
        candidate = (repo / rel).resolve()
        if candidate.is_file():
            touched.append(candidate)
    return diff_text, touched


def audit_repository(
    repo: Path,
    *,
    files: list[str] | None = None,
    mode: str = "bugfix",
) -> dict[str, Any]:
    repo = repo.resolve()
    diff_text, touched_files = collect_repo_diff_and_files(repo, files)
    issues = audit_diff_text(diff_text, mode=mode)

    for path in touched_files:
        if path.suffix.lower() == ".py":
            rel = path.relative_to(repo).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            issues.extend(audit_python_source(rel, text))

    trail_active = (repo / ".trail").is_dir()
    trail_cli = shutil.which("trail")
    trail_note = "not_indexed"
    if trail_active:
        trail_note = "trail_dir_present (run `trail check` before commit)"
        if trail_cli:
            trail_note = f"trail_cli_detected ({trail_cli})"

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {
        "passed": len(errors) == 0,
        "mode": mode,
        "touched_files": [p.relative_to(repo).as_posix() for p in touched_files],
        "trail_status": trail_note,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit bugfix diff & touched files for Clean-Slate compliance.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Target git repository root.")
    parser.add_argument("--files", nargs="*", default=None, help="Optional subset of relative file paths.")
    parser.add_argument("--mode", choices=("bugfix", "feature"), default="bugfix", help="Audit mode (default: bugfix).")
    parser.add_argument("--strict", action="store_true", help="Treat warnings (e.g. band-aid suspect) as non-zero exit.")
    parser.add_argument("--json", action="store_true", help="Output JSON report.")
    args = parser.parse_args(argv)

    if not args.repo.is_dir():
        print(f"[clean_slate_audit] Repo directory not found: {args.repo}", file=sys.stderr)
        return 2

    report = audit_repository(args.repo, files=args.files, mode=args.mode)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        ok = report["passed"] and (not args.strict or report["warning_count"] == 0)
        label = "PASSED" if ok else "FAILED"
        print(
            f"[clean_slate_audit] {label} ({report['mode']}) — touched {len(report['touched_files'])} file(s) | "
            f"{report['error_count']} error(s), {report['warning_count']} warning(s) | trail={report['trail_status']}"
        )
        for item in report["issues"]:
            print(f"  [{item['severity'].upper()}] {item['code']} @ {item['file']}:{item['line']} — {item['message']}")

    if not report["passed"] or (args.strict and report["warning_count"] > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
