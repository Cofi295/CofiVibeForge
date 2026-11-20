#!/usr/bin/env python3
"""Universal 1-Command Cross-Platform Installer for CofiVibeForge (Windows / macOS / Linux).

Installs the CofiVibeForge Antigravity Plugin (`plugin.json`, `rules/AGENTS.md`, and all 3 skills:
`trail`, `vibe-straightline-architect`, `trail-clean-slate-debugger`) into `~/.gemini/config/`,
automatically installs `@trailhq/trail-code` via npm when Node.js is available, and optionally
indexes + registers Trail MCP server(s) for any `--project <repo_path>`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

FORGE_ROOT = Path(__file__).resolve().parent
if str(FORGE_ROOT) not in sys.path:
    sys.path.insert(0, str(FORGE_ROOT))

from scripts.sync_integrations import PLUGIN_DIR_NAME, sync_antigravity  # noqa: E402

WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _find_node_binary() -> str | None:
    found = shutil.which("node")
    if found:
        return str(Path(found).resolve())
    candidates = [
        Path("C:/Program Files/nodejs/node.exe"),
        Path("/opt/homebrew/bin/node"),
        Path("/usr/local/bin/node"),
        Path("/usr/bin/node"),
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


def _locate_trail_js() -> str | None:
    roots: list[Path] = []
    npm_bin = shutil.which("npm")
    if npm_bin:
        res = subprocess.run(
            [npm_bin, "root", "-g"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=(os.name == "nt"),
            creationflags=WIN_NO_WINDOW,
        )
        if res.returncode == 0 and res.stdout.strip():
            roots.append(Path(res.stdout.strip()))
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "npm" / "node_modules")
    roots.extend(
        [
            Path("/opt/homebrew/lib/node_modules"),
            Path("/usr/local/lib/node_modules"),
            Path.home() / ".npm-global" / "lib" / "node_modules",
        ]
    )
    for root in roots:
        entry = root / "@trailhq" / "trail-code" / "dist" / "bin" / "trail.js"
        if entry.is_file():
            return str(entry.resolve())
    return None


def _ensure_trail_runtime(*, auto_install_npm: bool, dry_run: bool) -> tuple[str | None, str | None, str]:
    node_bin = _find_node_binary()
    if not node_bin:
        return None, None, "node_not_found (skills & rules installed; install Node.js >=18 to enable Trail MCP)"
    trail_js = _locate_trail_js()
    if trail_js:
        return node_bin, trail_js, f"trail_ready ({trail_js})"
    npm_bin = shutil.which("npm")
    if not auto_install_npm or not npm_bin:
        return node_bin, None, "trail_missing (run: npm install -g @trailhq/trail-code)"
    if dry_run:
        return node_bin, "<dry-run-trail.js>", "would_install_npm (@trailhq/trail-code)"
    res = subprocess.run(
        [npm_bin, "install", "-g", "@trailhq/trail-code"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=(os.name == "nt"),
        creationflags=WIN_NO_WINDOW,
    )
    if res.returncode != 0:
        return node_bin, None, f"npm_install_failed ({(res.stderr or res.stdout).strip()[:160]})"
    trail_js = _locate_trail_js()
    if trail_js:
        return node_bin, trail_js, f"trail_installed ({trail_js})"
    return node_bin, None, "trail_not_located_after_npm_install"


def _parse_project_spec(spec: str, index: int, total: int) -> tuple[str, Path]:
    if "=" in spec:
        raw_name, raw_path = spec.split("=", 1)
        proj_dir = Path(raw_path).expanduser().resolve()
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw_name.strip()).strip("_").lower() or "trail"
        server_name = slug if slug.startswith("trail") else f"trail_{slug}"
        return server_name, proj_dir
    proj_dir = Path(spec).expanduser().resolve()
    if total == 1 and index == 0:
        return "trail", proj_dir
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", proj_dir.name).strip("_").lower() or f"repo_{index + 1}"
    return f"trail_{slug}", proj_dir


def _merge_mcp_file(mcp_path: Path, updates: dict[str, dict[str, Any]], *, dry_run: bool) -> str:
    existing: dict[str, Any] = {}
    if mcp_path.is_file():
        existing = json.loads(mcp_path.read_text(encoding="utf-8"))
    servers = dict(existing.get("mcpServers") or {})
    servers.update(updates)
    if dry_run:
        return f"would_write_mcp ({mcp_path} [{len(updates)} server(s)])"
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**existing, "mcpServers": servers}
    mcp_path.write_bytes((json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return f"wrote_mcp ({mcp_path} [{len(updates)} server(s)])"


def run_installer(
    *,
    forge_root: Path = FORGE_ROOT,
    projects: list[str] | None = None,
    gemini_config_dir: Path | None = None,
    auto_install_npm: bool = True,
    node_bin_override: str | None = None,
    trail_js_override: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg_dir = gemini_config_dir or (Path.home() / ".gemini" / "config")
    sync_res = sync_antigravity(
        forge_root=forge_root,
        gemini_config_dir=cfg_dir,
        workspace_agents_dir=Path("__none__") if gemini_config_dir is not None else None,
        dry_run=dry_run,
    )
    actions = list(sync_res["actions"])

    if node_bin_override and trail_js_override:
        node_bin, trail_js, runtime_note = node_bin_override, trail_js_override, f"trail_override ({trail_js_override})"
    else:
        node_bin, trail_js, runtime_note = _ensure_trail_runtime(auto_install_npm=auto_install_npm, dry_run=dry_run)
    actions.append(runtime_note)

    raw_projects = list(projects or [])
    plugin_dir = cfg_dir / "plugins" / PLUGIN_DIR_NAME
    auto_mcp_script = plugin_dir / "scripts" / "auto_trail_mcp.py"
    registered_servers: dict[str, dict[str, Any]] = {
        "cofi_trail_auto": {
            "command": sys.executable,
            "args": [str(auto_mcp_script)],
            "disabled": False,
        }
    }

    if raw_projects and node_bin and trail_js:
        for idx, spec in enumerate(raw_projects):
            srv_name, proj_dir = _parse_project_spec(spec, idx, len(raw_projects))
            if not proj_dir.is_dir():
                raise FileNotFoundError(f"Project directory does not exist: {proj_dir}")
            if not dry_run and Path(trail_js).is_file():
                build_res = subprocess.run(
                    [node_bin, trail_js, "build", str(proj_dir)],
                    cwd=str(proj_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=WIN_NO_WINDOW,
                )
                actions.append(
                    f"trail_build_ok ({proj_dir})"
                    if build_res.returncode == 0
                    else f"trail_build_warn ({proj_dir}: {(build_res.stderr or build_res.stdout).strip()[:120]})"
                )
            registered_servers[srv_name] = {
                "command": node_bin,
                "args": [trail_js, "mcp", str(proj_dir)],
                "disabled": False,
            }

    plugin_mcp = plugin_dir / "mcp_config.json"
    global_mcp = cfg_dir / "mcp_config.json"
    actions.append(_merge_mcp_file(plugin_mcp, registered_servers, dry_run=dry_run))
    actions.append(_merge_mcp_file(global_mcp, registered_servers, dry_run=dry_run))

    return {
        "installed": True,
        "plugin_dir": str(plugin_dir),
        "registered_mcp_servers": list(registered_servers.keys()),
        "dry_run": dry_run,
        "actions": actions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="1-Command Installer for CofiVibeForge + Trail Graph on Antigravity.")
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Git project path (or alias=/path/to/repo) to index with Trail and register as an MCP server. Repeatable.",
    )
    parser.add_argument("--skip-npm", action="store_true", help="Skip auto-installing @trailhq/trail-code via npm.")
    parser.add_argument("--dry-run", action="store_true", help="Preview installation steps without modifying files.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    args = parser.parse_args(argv)

    result = run_installer(
        projects=args.project,
        auto_install_npm=not args.skip_npm,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("CofiVibeForge v2.1.0 installed into Antigravity (Zero-Config Auto-Trail enabled everywhere)!")
        print(f"  Plugin path : {result['plugin_dir']}")
        if result["registered_mcp_servers"]:
            print(f"  Trail MCP   : {', '.join(result['registered_mcp_servers'])}")
        for act in result["actions"]:
            print(f"  - {act}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
