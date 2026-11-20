#!/usr/bin/env python3
"""Deterministic AST & File-Tree Verifier for Straight-Line Vibe Coding.

Detects LLM over-engineering & scaffolding bloat in <0.2s using pure stdlib:
- Undeclared rogue files or missing planned files against a Blueprint table
- God-files exceeding line budgets & empty/stub micro-files
- Single-method classes that should be plain straight-line functions
- Trivial pass-through wrapper functions
- Hallucinated unused function parameters (`config=None`, `options=None`, etc.)
- Leftover NotImplementedError / TODO / FIXME placeholders
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys
from typing import Any

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".pytest_tmp",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".trail",
    ".agents",
    ".codex",
}
SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs"}
CLASS_EXEMPT_BASES = {
    "Enum",
    "IntEnum",
    "StrEnum",
    "Flag",
    "TypedDict",
    "NamedTuple",
    "Protocol",
    "ABC",
    "BaseModel",
    "Exception",
    "RuntimeError",
    "ValueError",
    "KeyError",
}
CLASS_EXEMPT_DECORATORS = {"dataclass"}
FUNC_PARAM_EXEMPT_DECORATORS = {
    "abstractmethod",
    "override",
    "fixture",
    "validator",
    "field_validator",
    "model_validator",
    "property",
    "cached_property",
}
PLACEHOLDER_RE = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)
BLUEPRINT_ROW_RE = re.compile(r"^\|\s*`?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)`?\s*\|")


def iter_source_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SOURCE_EXTS else []
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix.lower() in SOURCE_EXTS:
            found.append(path)
    return found


def parse_blueprint_paths(blueprint_path: Path) -> set[str]:
    declared: set[str] = set()
    for raw_line in blueprint_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = BLUEPRINT_ROW_RE.match(raw_line.strip())
        if match:
            norm = match.group(1).strip().replace("\\", "/").lstrip("./")
            declared.add(norm)
    return declared


def _decorator_names(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _base_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in node.bases:
        target = base.value if isinstance(base, ast.Subscript) else base
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _is_stub_body(stmts: list[ast.stmt]) -> bool:
    if not stmts:
        return True
    if len(stmts) == 1:
        stmt = stmts[0]
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
            return True
        if isinstance(stmt, ast.Raise):
            return True
    return False


def audit_python_ast(rel_path: str, text: str, is_test_file: bool) -> list[dict[str, Any]]:
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

    for lineno, line in enumerate(text.splitlines(), start=1):
        if PLACEHOLDER_RE.search(line):
            issues.append(
                {
                    "code": "UNFINISHED_PLACEHOLDER",
                    "severity": "warning",
                    "file": rel_path,
                    "line": lineno,
                    "message": "Leftover TODO/FIXME/HACK comment; finish straight-line logic or remove.",
                }
            )

    if is_test_file:
        return issues

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = _base_names(node)
            decs = _decorator_names(node)
            if (bases & CLASS_EXEMPT_BASES) or (decs & CLASS_EXEMPT_DECORATORS) or node.name.endswith(("Error", "Exception", "Config", "Schema", "Model")):
                continue
            methods = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
            public_methods = [m for m in methods if not m.name.startswith("_")]
            class_fields = [item for item in node.body if isinstance(item, (ast.AnnAssign, ast.Assign))]
            if len(public_methods) <= 1 and len(methods) <= 2 and not class_fields and not bases:
                issues.append(
                    {
                        "code": "SINGLE_METHOD_CLASS_BLOAT",
                        "severity": "warning",
                        "file": rel_path,
                        "line": node.lineno,
                        "message": f"Class '{node.name}' has <=1 public method and no state schema; replace with a plain straight-line function.",
                    }
                )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decs = _decorator_names(node)
            stmts = _strip_docstring(node.body)
            if not decs and len(stmts) == 1 and isinstance(stmts[0], ast.Return) and isinstance(stmts[0].value, ast.Call):
                call = stmts[0].value
                declared_args = [a.arg for a in node.args.args if a.arg not in {"self", "cls"}]
                passed_args = [a.id for a in call.args if isinstance(a, ast.Name)]
                if declared_args and declared_args == passed_args and not call.keywords and not node.args.kwonlyargs:
                    issues.append(
                        {
                            "code": "TRIVIAL_PASSTHROUGH_WRAPPER",
                            "severity": "warning",
                            "file": rel_path,
                            "line": node.lineno,
                            "message": f"Function '{node.name}' is a pure pass-through wrapper; call the target function directly.",
                        }
                    )

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decs = _decorator_names(node)
        if decs & FUNC_PARAM_EXEMPT_DECORATORS or node.name.startswith("__"):
            continue
        stmts = _strip_docstring(node.body)
        if _is_stub_body(stmts):
            if len(stmts) == 1 and isinstance(stmts[0], ast.Raise):
                exc_expr = stmts[0].exc
                exc_name = ""
                if isinstance(exc_expr, ast.Name):
                    exc_name = exc_expr.id
                elif isinstance(exc_expr, ast.Call) and isinstance(exc_expr.func, ast.Name):
                    exc_name = exc_expr.func.id
                if exc_name == "NotImplementedError":
                    issues.append(
                        {
                            "code": "UNFINISHED_PLACEHOLDER",
                            "severity": "error",
                            "file": rel_path,
                            "line": node.lineno,
                            "message": f"Function '{node.name}' raises NotImplementedError without @abstractmethod.",
                        }
                    )
            continue

        all_params = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
        candidate_params = [
            p.arg
            for p in all_params
            if p.arg not in {"self", "cls"} and not p.arg.startswith("_")
        ]
        if not candidate_params:
            continue

        used_names: set[str] = set()
        for stmt in stmts:
            for child in ast.walk(stmt):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    used_names.add(child.id)

        for param in candidate_params:
            if param not in used_names:
                issues.append(
                    {
                        "code": "SPECULATIVE_UNUSED_PARAM",
                        "severity": "error",
                        "file": rel_path,
                        "line": node.lineno,
                        "message": f"Parameter '{param}' in '{node.name}()' is never read; remove unused/speculative parameter (or prefix '_' if required by callback signature).",
                    }
                )

    return issues


def audit_target(target: Path, *, blueprint: Path | None = None, max_lines: int = 350) -> dict[str, Any]:
    root = target.resolve()
    base_dir = root if root.is_dir() else root.parent
    files = iter_source_files(root)
    issues: list[dict[str, Any]] = []

    if blueprint is not None:
        declared = parse_blueprint_paths(blueprint.resolve())
        actual_rel = {f.relative_to(base_dir).as_posix() for f in files}
        for rel in sorted(actual_rel - declared):
            if Path(rel).name == "__init__.py":
                continue
            issues.append(
                {
                    "code": "UNDECLARED_FILE",
                    "severity": "error",
                    "file": rel,
                    "line": 1,
                    "message": f"File '{rel}' is not declared in blueprint '{blueprint.name}' (unauthorized file sprawl).",
                }
            )
        for rel in sorted(declared - actual_rel):
            if not (base_dir / rel).exists():
                issues.append(
                    {
                        "code": "MISSING_PLANNED_FILE",
                        "severity": "warning",
                        "file": rel,
                        "line": 1,
                        "message": f"Planned file '{rel}' in blueprint '{blueprint.name}' has not been created yet.",
                    }
                )

    for file_path in files:
        rel = file_path.relative_to(base_dir).as_posix() if root.is_dir() else file_path.name
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        line_count = len(lines)
        is_test = file_path.name.startswith("test_") or file_path.name.endswith(("_test.py", ".test.ts", ".spec.ts")) or "tests/" in f"{rel}/"

        if line_count > max_lines and not is_test:
            issues.append(
                {
                    "code": "GOD_FILE_EXCEEDED",
                    "severity": "warning",
                    "file": rel,
                    "line": max_lines,
                    "message": f"File has {line_count} lines (budget <= {max_lines}); split by cohesive responsibility.",
                }
            )

        meaningful = [
            ln for ln in lines if ln.strip() and not ln.strip().startswith(("#", "//", "/*", "*"))
        ]
        if file_path.name != "__init__.py" and not file_path.name.endswith(".d.ts") and len(meaningful) < 2:
            issues.append(
                {
                    "code": "EMPTY_OR_STUB_FILE",
                    "severity": "error",
                    "file": rel,
                    "line": 1,
                    "message": f"File '{rel}' is empty or near-empty stub ({len(meaningful)} code lines).",
                }
            )

        if file_path.suffix.lower() == ".py":
            issues.extend(audit_python_ast(rel, text, is_test))

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {
        "passed": len(errors) == 0,
        "scanned_files": len(files),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit scaffolded project/module for straight-line YAGNI compliance.")
    parser.add_argument("target", type=Path, help="Target project directory or source file.")
    parser.add_argument("--blueprint", type=Path, default=None, help="Optional project_blueprint.md path.")
    parser.add_argument("--max-lines", type=int, default=350, help="Max lines per non-test source file (default: 350).")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as non-zero exit errors.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    if not args.target.exists():
        print(f"[scaffold_guard] Target does not exist: {args.target}", file=sys.stderr)
        return 2

    report = audit_target(args.target, blueprint=args.blueprint, max_lines=args.max_lines)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASSED" if report["passed"] and (not args.strict or report["warning_count"] == 0) else "FAILED"
        print(
            f"[scaffold_guard] {status} — scanned {report['scanned_files']} file(s) | "
            f"{report['error_count']} error(s), {report['warning_count']} warning(s)"
        )
        for item in report["issues"]:
            tag = item["severity"].upper()
            print(f"  [{tag}] {item['code']} @ {item['file']}:{item['line']} — {item['message']}")

    if not report["passed"] or (args.strict and report["warning_count"] > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
