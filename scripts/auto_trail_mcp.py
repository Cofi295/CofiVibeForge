#!/usr/bin/env python3
"""Zero-Config Dynamic Auto-Trail MCP Server (`cofi_trail_auto`).

Eliminates manual `--project` registration and `.git` requirements:
- Works on ANY directory or standalone code file on disk (with or without Git).
- Automatically resolves the target code directory from `arguments.dir`, an absolute
  `arguments.file` path, MCP `initialize` workspace roots, or `Path.cwd()`.
- Automatically builds the local `.trail`/`graft` AST graph on first touch (`<0.3s`),
  then forwards JSON-RPC `tools/call` to a warm per-directory `trail.js mcp` worker.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import unquote, urlparse

WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_WARM_WORKERS = 6

DIR_PROP_SCHEMA: dict[str, str] = {
    "type": "string",
    "description": (
        "Target code directory (or file path). Optional when workspace root is open or an absolute 'file' "
        "path is passed; required when current workspace is a drive/home root. Auto-indexes on first touch without Git."
    ),
}

TOOLS_MANIFEST: list[dict[str, Any]] = [
    {
        "name": "trail_find_code",
        "description": "Query the code graph in plain words across any folder (auto-indexes on first touch, no Git required). Returns ranked nodes with exact file:line spans and source excerpts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "what you want to understand, in plain words"},
                "dir": DIR_PROP_SCHEMA,
                "limit": {"type": "number", "description": "max results (default 5)"},
                "full": {"type": "boolean", "description": "inline whole definition spans"},
                "in": {"type": "string", "description": "narrow to nodes under this path prefix"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "trail_file_api",
        "description": "Signatures-only view of one file — every definition's signature + StartLine-EndLine span (~10x cheaper than reading whole file; auto-indexes folder on first touch).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "absolute file path or folder-relative file path"},
                "dir": DIR_PROP_SCHEMA,
            },
            "required": ["file"],
        },
    },
    {
        "name": "trail_check_freshness",
        "description": "Report whether the local code graph is in sync with source files.",
        "inputSchema": {"type": "object", "properties": {"dir": DIR_PROP_SCHEMA}},
    },
    {
        "name": "trail_trace_calls",
        "description": "Callers/dependents ('in') or callees/dependencies ('out') for a symbol across the target code folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "function, class, or Class.method name"},
                "dir": DIR_PROP_SCHEMA,
                "direction": {"type": "string", "enum": ["in", "out"], "description": "'in' = callers, 'out' = callees"},
                "depth": {"description": "transitive depth (default 1, or 'all')"},
                "in": {"type": "string", "description": "narrow to path prefix"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "trail_find_all",
        "description": "Exhaustive regex/literal search over indexed code files, grouped by enclosing symbol.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "regex or literal pattern"},
                "dir": DIR_PROP_SCHEMA,
                "in": {"type": "string", "description": "narrow to path prefix"},
                "ignore_case": {"type": "boolean"},
                "fixed": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "trail_repo_map",
        "description": "Token-budgeted architectural map of directory clusters, hubs, and hotspots for any code folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir": DIR_PROP_SCHEMA,
                "max_dirs": {"type": "number", "description": "max directory entries shown (default 16)"},
            },
        },
    },
]


@dataclass
class _WarmWorker:
    proc: subprocess.Popen[str]
    req_seq: int = 10


def _find_node_and_trail() -> tuple[str | None, str | None]:
    node_bin = shutil.which("node")
    if not node_bin:
        for cand in (Path("C:/Program Files/nodejs/node.exe"), Path("/opt/homebrew/bin/node"), Path("/usr/local/bin/node"), Path("/usr/bin/node")):
            if cand.is_file():
                node_bin = str(cand)
                break
    if not node_bin:
        return None, None

    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "npm" / "node_modules")
    roots.extend([Path("/opt/homebrew/lib/node_modules"), Path("/usr/local/lib/node_modules"), Path.home() / ".npm-global" / "lib" / "node_modules"])
    for rt in roots:
        entry = rt / "@trailhq" / "trail-code" / "dist" / "bin" / "trail.js"
        if entry.is_file():
            return str(Path(node_bin).resolve()), str(entry.resolve())
    npm_bin = shutil.which("npm")
    if npm_bin:
        res = subprocess.run([npm_bin, "root", "-g"], capture_output=True, text=True, shell=(os.name == "nt"), creationflags=WIN_NO_WINDOW)
        if res.returncode == 0 and res.stdout.strip():
            entry = Path(res.stdout.strip()) / "@trailhq" / "trail-code" / "dist" / "bin" / "trail.js"
            if entry.is_file():
                return str(Path(node_bin).resolve()), str(entry.resolve())
    return str(Path(node_bin).resolve()), None


def _uri_to_path(uri: str) -> Path | None:
    if not uri:
        return None
    if not uri.startswith("file://"):
        p = Path(uri).expanduser()
        return p.resolve() if p.exists() else None
    parsed = urlparse(uri)
    raw_path = unquote(parsed.path or "")
    if os.name == "nt" and len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
        raw_path = raw_path[1:]
    p = Path(raw_path)
    return p.resolve() if p.exists() else None


def _is_safe_code_dir(d: Path) -> bool:
    resolved = d.resolve()
    if resolved.parent == resolved:
        return False
    if resolved == Path.home().resolve():
        return False
    return resolved.is_dir()


def _nearest_project_or_self(start_dir: Path) -> Path:
    cur = start_dir.resolve()
    for idx, cand in enumerate((cur, *cur.parents)):
        if not _is_safe_code_dir(cand):
            break
        if (cand / ".trail").is_dir() or (cand / "graft").is_dir() or (cand / ".git").exists():
            return cand
        if idx == 0 and any(p.startswith(".") for p in cur.parts):
            break
        if cand.name.startswith("."):
            break
    return cur


def resolve_target_and_clean_args(
    raw_args: dict[str, Any],
    workspace_roots: list[Path],
) -> tuple[Path | None, dict[str, Any], str | None]:
    forward_args = {k: v for k, v in raw_args.items() if k != "dir"}
    explicit_dir = str(raw_args.get("dir") or "").strip()

    target: Path | None = None
    if explicit_dir:
        cand = Path(explicit_dir).expanduser().resolve()
        if cand.is_file():
            cand = cand.parent
        if not cand.exists():
            return None, forward_args, f"Directory not found: {explicit_dir}"
        target = _nearest_project_or_self(cand)
    elif isinstance(forward_args.get("file"), str):
        f_arg = Path(str(forward_args["file"])).expanduser()
        if f_arg.is_absolute() and f_arg.exists():
            base_dir = f_arg.parent if f_arg.is_file() else f_arg
            target = _nearest_project_or_self(base_dir)

    if target is None:
        for root in workspace_roots:
            if _is_safe_code_dir(root):
                target = _nearest_project_or_self(root)
                break
    if target is None and _is_safe_code_dir(Path.cwd()):
        target = _nearest_project_or_self(Path.cwd())

    if target is None or not _is_safe_code_dir(target):
        return (
            None,
            forward_args,
            "Current workspace is a drive or home root; pass 'dir': '<path/to/code_folder>' (or an absolute 'file' path) so Auto-Trail indexes only that folder.",
        )

    if isinstance(forward_args.get("file"), str):
        f_path = Path(str(forward_args["file"])).expanduser()
        if f_path.is_absolute():
            try:
                forward_args["file"] = f_path.resolve().relative_to(target).as_posix()
            except ValueError:
                forward_args["file"] = f_path.name

    return target, forward_args, None


def _ensure_worker(
    target_dir: Path,
    node_bin: str,
    trail_js: str,
    pool: OrderedDict[str, _WarmWorker],
) -> _WarmWorker:
    key = str(target_dir.resolve())
    existing = pool.get(key)
    if existing is not None and existing.proc.poll() is None:
        pool.move_to_end(key)
        return existing

    if not ((target_dir / ".trail" / "cache").is_dir() or (target_dir / "graft" / "cache").is_dir() or (target_dir / "graft").is_dir()):
        subprocess.run(
            [node_bin, trail_js, "build", key],
            cwd=key,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=WIN_NO_WINDOW,
        )

    while len(pool) >= MAX_WARM_WORKERS:
        _, oldest = pool.popitem(last=False)
        if oldest.proc.poll() is None:
            oldest.proc.terminate()

    proc = subprocess.Popen(
        [node_bin, trail_js, "mcp", key],
        cwd=key,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=WIN_NO_WINDOW,
    )
    assert proc.stdin is not None and proc.stdout is not None
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cofi-auto-trail", "version": "2.1.0"}},
    }
    proc.stdin.write(json.dumps(init_req) + "\n")
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()
    proc.stdout.readline()

    worker = _WarmWorker(proc=proc, req_seq=10)
    pool[key] = worker
    return worker


def _call_worker_tool(worker: _WarmWorker, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    assert worker.proc.stdin is not None and worker.proc.stdout is not None
    worker.req_seq += 1
    req_id = worker.req_seq
    payload = {"jsonrpc": "2.0", "id": req_id, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}}
    worker.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    worker.proc.stdin.flush()
    while True:
        line = worker.proc.stdout.readline()
        if not line:
            return {"content": [{"type": "text", "text": "Trail worker closed unexpectedly."}], "isError": True}
        msg = json.loads(line)
        if msg.get("id") == req_id:
            if "error" in msg:
                return {"content": [{"type": "text", "text": str(msg["error"])}], "isError": True}
            return msg.get("result") or {"content": [{"type": "text", "text": ""}]}


def serve_stdio() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            reconf(encoding="utf-8", errors="replace")
    node_bin: str | None = None
    trail_js: str | None = None
    runtime_checked = False
    workspace_roots: list[Path] = []
    pool: OrderedDict[str, _WarmWorker] = OrderedDict()

    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line or line.lower().startswith("content-length:"):
                continue
            msg = json.loads(line)
            method = str(msg.get("method") or "")
            msg_id = msg.get("id")
            params = msg.get("params") or {}

            if method == "initialize":
                workspace_roots.clear()
                for wf in params.get("workspaceFolders") or []:
                    if isinstance(wf, dict):
                        p = _uri_to_path(str(wf.get("uri") or wf.get("path") or ""))
                        if p is not None:
                            workspace_roots.append(p)
                root_uri = _uri_to_path(str(params.get("rootUri") or params.get("rootPath") or ""))
                if root_uri is not None and root_uri not in workspace_roots:
                    workspace_roots.append(root_uri)
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": str(params.get("protocolVersion") or "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "cofi_trail_auto", "version": "2.1.0"},
                        "instructions": (
                            "Dynamic Zero-Config Trail Code-Graph (`cofi_trail_auto`): works automatically on ANY code folder "
                            "or standalone file (with or without Git) and auto-builds the graph on first touch. "
                            "Pass `dir` (or an absolute `file` path) whenever working in a subfolder or drive root."
                        ),
                    },
                }
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            elif method == "tools/list":
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS_MANIFEST}}, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            elif method == "tools/call":
                if not runtime_checked:
                    node_bin, trail_js = _find_node_and_trail()
                    runtime_checked = True
                if not node_bin or not trail_js:
                    err_res = {
                        "content": [{"type": "text", "text": "Trail runtime missing; run: npm install -g @trailhq/trail-code"}],
                        "isError": True,
                    }
                    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": err_res}) + "\n")
                    sys.stdout.flush()
                    continue
                t_name = str(params.get("name") or "")
                raw_args = dict(params.get("arguments") or {})
                target_dir, clean_args, err_note = resolve_target_and_clean_args(raw_args, workspace_roots)
                if err_note or target_dir is None:
                    res_obj = {"content": [{"type": "text", "text": err_note or "Unable to resolve target folder."}], "isError": True}
                else:
                    worker = _ensure_worker(target_dir, node_bin, trail_js, pool)
                    res_obj = _call_worker_tool(worker, t_name, clean_args)
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": res_obj}, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            elif msg_id is not None:
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {}}) + "\n")
                sys.stdout.flush()
    finally:
        for w in pool.values():
            if w.proc.poll() is None:
                w.proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
