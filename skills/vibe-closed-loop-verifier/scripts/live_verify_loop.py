#!/usr/bin/env python3
"""Closed-Loop Live Execution Verifier & Autonomous Test-Fix Runner.

Enforces a 5-stage real-execution verification gate before an agent can claim work is done:
1. Clean-Slate AST & Producer-Consumer Key Drift Audit (`clean_slate_audit.py`)
2. Intra-File & Cross-File Contradiction Audit (`--check-contradictions` + `--forbid`)
3. Automated Pytest Regression Execution (`--pytest`)
4. Unmocked Live Smoke / Real-Data Probes (`--probe`), plus optional Windows `cp1252` check (`--check-cp1252`)
5. Real-Workspace Contract Replay (`--verify-workspace`) & Signed Verification Receipt (`--receipt-out`)
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CONST_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")
SHARED_BENIGN_CONSTANTS = frozenset({
    "WIN_NO_WINDOW", "FORGE_ROOT", "SKIP_NAMES", "PLUGIN_DIR_NAME",
    "DEFAULT_TIMEOUT", "UTF8", "ENCODING", "VERSION",
})


def _load_clean_slate_audit() -> Any:
    audit_path = Path(__file__).resolve().parents[2] / "trail-clean-slate-debugger" / "scripts" / "clean_slate_audit.py"
    spec = importlib.util.spec_from_file_location("clean_slate_audit", audit_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load clean_slate_audit.py at {audit_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["clean_slate_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def _git_head_sha(repo: Path) -> str:
    res = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=10, creationflags=WIN_NO_WINDOW,
    )
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else "no-git"


def _iter_statement_blocks(node: ast.AST) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = []
    for sub in ast.walk(node):
        for attr in ("body", "orelse", "finalbody"):
            seq = getattr(sub, attr, None)
            if isinstance(seq, list) and seq and all(isinstance(s, ast.stmt) for s in seq):
                blocks.append(seq)
    return blocks


def audit_contradictions(
    repo: Path,
    *,
    touched_files: list[Path],
    forbid_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Detect duplicate conflicting definitions, unreachable dead code, cross-file constant drift, and banned legacy patterns."""
    issues: list[dict[str, Any]] = []
    const_registry: dict[str, list[tuple[str, int, Any]]] = {}
    compiled_forbid: list[tuple[str, re.Pattern[str]]] = [
        (pat, re.compile(pat)) for pat in (forbid_patterns or []) if pat.strip()
    ]

    for path in touched_files:
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")

        if compiled_forbid:
            for idx, line in enumerate(text.splitlines(), start=1):
                for raw_pat, rx in compiled_forbid:
                    if rx.search(line):
                        issues.append({
                            "code": "FORBIDDEN_LEGACY_PATTERN",
                            "severity": "error",
                            "file": rel,
                            "line": idx,
                            "message": f"Forbidden legacy pattern `{raw_pat}` still present: `{line.strip()[:120]}`.",
                        })

        if path.suffix.lower() != ".py":
            continue
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue

        seen_top: dict[str, int] = {}
        is_test = Path(rel).name.startswith("test_") or "/tests/" in f"/{rel}/"
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if stmt.name in seen_top:
                    issues.append({
                        "code": "DUPLICATE_SYMBOL_DEFINITION",
                        "severity": "error",
                        "file": rel,
                        "line": stmt.lineno,
                        "message": f"Top-level symbol `{stmt.name}` redefined at line {stmt.lineno} (previous definition at line {seen_top[stmt.name]}).",
                    })
                seen_top[stmt.name] = stmt.lineno
            elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                cname = stmt.targets[0].id
                if CONST_NAME_RE.match(cname):
                    if cname in seen_top:
                        issues.append({
                            "code": "DUPLICATE_SYMBOL_DEFINITION",
                            "severity": "error",
                            "file": rel,
                            "line": stmt.lineno,
                            "message": f"Module constant `{cname}` reassigned at line {stmt.lineno} (previous assignment at line {seen_top[cname]}).",
                        })
                    seen_top[cname] = stmt.lineno
                    if not is_test and len(cname) >= 8 and cname not in SHARED_BENIGN_CONSTANTS and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, (int, float, str, bool)):
                        const_registry.setdefault(cname, []).append((rel, stmt.lineno, stmt.value.value))
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                cname = stmt.target.id
                if CONST_NAME_RE.match(cname):
                    if cname in seen_top:
                        issues.append({
                            "code": "DUPLICATE_SYMBOL_DEFINITION",
                            "severity": "error",
                            "file": rel,
                            "line": stmt.lineno,
                            "message": f"Module constant `{cname}` reassigned at line {stmt.lineno} (previous assignment at line {seen_top[cname]}).",
                        })
                    seen_top[cname] = stmt.lineno
                    if not is_test and len(cname) >= 8 and cname not in SHARED_BENIGN_CONSTANTS and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, (int, float, str, bool)):
                        const_registry.setdefault(cname, []).append((rel, stmt.lineno, stmt.value.value))

        for block in _iter_statement_blocks(tree):
            for idx, st in enumerate(block[:-1]):
                if isinstance(st, (ast.Return, ast.Raise)):
                    nxt = block[idx + 1]
                    issues.append({
                        "code": "UNREACHABLE_CODE_AFTER_RETURN",
                        "severity": "error",
                        "file": rel,
                        "line": getattr(nxt, "lineno", st.lineno + 1),
                        "message": f"Unreachable dead statement after unconditional `{type(st).__name__.lower()}` at line {st.lineno}.",
                    })
                    break

    for cname, entries in sorted(const_registry.items()):
        distinct_vals = {repr(v) for _, _, v in entries}
        if len(entries) >= 2 and len(distinct_vals) >= 2:
            summary = ", ".join(f"{f}:{ln}={v!r}" for f, ln, v in entries)
            issues.append({
                "code": "CROSS_FILE_CONSTANT_DRIFT",
                "severity": "warning",
                "file": entries[0][0],
                "line": entries[0][1],
                "message": f"Constant `{cname}` has conflicting values across touched files: {summary}.",
            })

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {
        "enabled": True,
        "passed": len(errors) == 0,
        "checked_files": [p.relative_to(repo).as_posix() for p in touched_files if p.is_file()],
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
    }


def run_probe_command(command: str, cwd: Path, *, force_cp1252: bool = False, timeout: int = 90) -> dict[str, Any]:
    env = dict(os.environ)
    if force_cp1252:
        env["PYTHONIOENCODING"] = "cp1252"
    t0 = time.monotonic()
    res = subprocess.run(
        command, cwd=str(cwd), shell=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=timeout, creationflags=WIN_NO_WINDOW,
    )
    return {
        "command": command,
        "encoding_mode": "cp1252" if force_cp1252 else "default",
        "returncode": res.returncode,
        "passed": res.returncode == 0,
        "duration_sec": round(time.monotonic() - t0, 3),
        "stdout_excerpt": (res.stdout or "").strip()[-800:],
        "stderr_excerpt": (res.stderr or "").strip()[-800:],
    }


def _sign_receipt(receipt_core: dict[str, Any]) -> str:
    blob = json.dumps(receipt_core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def format_receipt_markdown(receipt: dict[str, Any]) -> str:
    audit = receipt["audit"]
    contra = receipt["contradictions"]
    pyt = receipt["pytest"]
    probes = receipt["probes"]
    lines = [
        "# Closed-Loop Live Verification Receipt",
        "",
        f"- **Verdict**: `{receipt['verdict']}`",
        f"- **Signature (`receipt_id`)**: `{receipt['receipt_id']}`",
        f"- **Verified At (UTC)**: `{receipt['verified_at_utc']}`",
        f"- **Target Repo & HEAD**: `{receipt['repo']}` (`{receipt['git_head']}`)",
        f"- **Touched Files ({len(receipt['touched_files'])})**: {', '.join(f'`{f}`' for f in receipt['touched_files']) or '`none`'}",
        f"- **Check 1 — Clean-Slate AST & Diff Audit**: `{'PASSED' if audit['passed'] else 'FAILED'}` (errors={audit['error_count']}, warnings={audit['warning_count']})",
        f"- **Check 2 — Contradiction & Legacy Pattern Audit**: `{'SKIPPED' if not contra['enabled'] else ('PASSED' if contra['passed'] else 'FAILED')}` (errors={contra['error_count']}, warnings={contra['warning_count']})",
        f"- **Check 3 — Pytest Regression Suite**: `{'SKIPPED' if pyt is None else ('PASSED' if pyt['passed'] else 'FAILED')}`",
        f"- **Check 4 — Unmocked Live Probes (`cp1252={receipt['check_cp1252']}`)**: `{sum(1 for p in probes if p['passed'])}/{len(probes)} passed`",
        f"- **Check 5 — Real-Workspace Scale Replay**: `{receipt['verify_workspace'] or 'SKIPPED'}`",
    ]
    all_issues = [*(audit.get("issues") or []), *(contra.get("issues") or [])]
    if all_issues:
        lines.extend(["", "## Findings"])
        for it in all_issues:
            lines.append(f"- `[{it['severity'].upper()}] {it['code']}` @ `{it['file']}:{it['line']}` — {it['message']}")
    return "\n".join(lines) + "\n"


def run_verification_suite(
    repo: Path,
    *,
    files: list[str] | None = None,
    pytest_targets: list[str] | None = None,
    probes: list[str] | None = None,
    verify_workspace: Path | None = None,
    check_cp1252: bool = False,
    check_contradictions: bool = False,
    forbid_patterns: list[str] | None = None,
    mode: str = "bugfix",
) -> dict[str, Any]:
    repo = repo.resolve()
    csa = _load_clean_slate_audit()
    audit_rep = csa.audit_repository(repo, files=files, mode=mode, verify_workspace=verify_workspace)
    touched_paths = [(repo / rel).resolve() for rel in audit_rep["touched_files"]]

    run_contra = bool(check_contradictions or forbid_patterns)
    contra_rep = (
        audit_contradictions(repo, touched_files=touched_paths, forbid_patterns=forbid_patterns)
        if run_contra
        else {"enabled": False, "passed": True, "checked_files": [], "error_count": 0, "warning_count": 0, "issues": []}
    )

    pytest_result: dict[str, Any] | None = None
    if pytest_targets:
        cmd = " ".join([f'"{sys.executable}"', "-m", "pytest", "-q", *[f'"{t}"' for t in pytest_targets]])
        pytest_result = run_probe_command(cmd, cwd=repo, timeout=180)

    probe_results: list[dict[str, Any]] = []
    for p_cmd in probes or []:
        probe_results.append(run_probe_command(p_cmd, cwd=repo, force_cp1252=False))
        if check_cp1252:
            probe_results.append(run_probe_command(p_cmd, cwd=repo, force_cp1252=True))

    audit_ok = bool(audit_rep["passed"])
    contra_ok = bool(contra_rep["passed"])
    pytest_ok = True if pytest_result is None else bool(pytest_result["passed"])
    all_probes_ok = all(p["passed"] for p in probe_results)
    overall_passed = audit_ok and contra_ok and pytest_ok and all_probes_ok
    verdict = "VERIFIED_GREEN" if overall_passed else "FAILED_NEEDS_SELF_FIX"
    git_head = _git_head_sha(repo)

    sig_core = {
        "verdict": verdict,
        "repo": str(repo),
        "git_head": git_head,
        "touched_files": sorted(audit_rep["touched_files"]),
        "audit_errors": audit_rep["error_count"],
        "contra_errors": contra_rep["error_count"],
        "pytest_ok": pytest_ok,
        "probes_passed": [p["passed"] for p in probe_results],
    }
    return {
        "verdict": verdict,
        "receipt_id": _sign_receipt(sig_core),
        "verified_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passed": overall_passed,
        "repo": str(repo),
        "git_head": git_head,
        "touched_files": audit_rep["touched_files"],
        "check_cp1252": check_cp1252,
        "verify_workspace": str(verify_workspace.resolve()) if verify_workspace else None,
        "audit": {
            "passed": audit_ok,
            "error_count": audit_rep["error_count"],
            "warning_count": audit_rep["warning_count"],
            "issues": audit_rep["issues"],
        },
        "contradictions": contra_rep,
        "pytest": pytest_result,
        "probes": probe_results,
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            reconf(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Run Closed-Loop Live Execution Verification.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Target repository root.")
    parser.add_argument("--files", nargs="*", default=None, help="Touched relative file paths to audit.")
    parser.add_argument("--pytest", nargs="*", default=None, help="Pytest test files or node IDs to run.")
    parser.add_argument("--probe", action="append", default=[], help="Real unmocked smoke/execution command (repeatable).")
    parser.add_argument("--verify-workspace", type=Path, default=None, help="Real workspace path for Producer-Consumer replay.")
    parser.add_argument("--check-cp1252", action="store_true", help="Also run probes under PYTHONIOENCODING=cp1252.")
    parser.add_argument("--check-contradictions", action="store_true", help="Audit duplicate symbols, unreachable code, and cross-file constant drift.")
    parser.add_argument("--forbid", action="append", default=[], help="Banned legacy regex pattern that must have 0 matches in touched files (repeatable).")
    parser.add_argument("--receipt-out", type=Path, default=None, help="Write signed Verification Receipt (.md or .json) to this path.")
    parser.add_argument("--mode", choices=("bugfix", "feature"), default="bugfix", help="Audit mode.")
    parser.add_argument("--json", action="store_true", help="Print JSON verification receipt.")
    args = parser.parse_args(argv)

    if not args.repo.is_dir():
        print(f"[live_verify_loop] Repo directory not found: {args.repo}", file=sys.stderr)
        return 2

    receipt = run_verification_suite(
        args.repo,
        files=args.files,
        pytest_targets=args.pytest,
        probes=args.probe,
        verify_workspace=args.verify_workspace,
        check_cp1252=args.check_cp1252,
        check_contradictions=args.check_contradictions,
        forbid_patterns=args.forbid,
        mode=args.mode,
    )
    if args.receipt_out is not None:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        if args.receipt_out.suffix.lower() == ".json":
            args.receipt_out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            args.receipt_out.write_text(format_receipt_markdown(receipt), encoding="utf-8")

    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        c = receipt["contradictions"]
        c_lbl = "SKIP" if not c["enabled"] else ("OK" if c["passed"] else f"FAIL({c['error_count']})")
        print(
            f"[live_verify_loop] {receipt['verdict']} (sig={receipt['receipt_id']}) | "
            f"audit={'OK' if receipt['audit']['passed'] else 'FAIL'} "
            f"(errors={receipt['audit']['error_count']}, warnings={receipt['audit']['warning_count']}) | "
            f"contradictions={c_lbl} | "
            f"pytest={'SKIP' if receipt['pytest'] is None else ('OK' if receipt['pytest']['passed'] else 'FAIL')} | "
            f"probes={sum(1 for p in receipt['probes'] if p['passed'])}/{len(receipt['probes'])} passed"
        )
        for issue in receipt["audit"]["issues"]:
            print(f"  [AUDIT {issue['severity'].upper()}] {issue['code']} @ {issue['file']}:{issue['line']} — {issue['message']}")
        for issue in c["issues"]:
            print(f"  [CONTRADICTION {issue['severity'].upper()}] {issue['code']} @ {issue['file']}:{issue['line']} — {issue['message']}")
        if receipt["pytest"] and not receipt["pytest"]["passed"]:
            print(f"  [PYTEST FAIL] {receipt['pytest']['stdout_excerpt']}\n{receipt['pytest']['stderr_excerpt']}")
        for pr in receipt["probes"]:
            if not pr["passed"]:
                print(f"  [PROBE FAIL ({pr['encoding_mode']})] {pr['command']} -> rc={pr['returncode']}\n    {pr['stderr_excerpt'] or pr['stdout_excerpt']}")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
