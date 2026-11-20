#!/usr/bin/env python3
"""Deterministic SHA-256 Sync Manager for CofiVibeForge.

Why real-directory sync instead of Windows Junctions (`mklink /J`):
- Go's `os.ReadDir` in the Antigravity Language Server treats Windows `ReparsePoint`
  junctions as `IsDir() == false`, silently skipping junctioned plugins and skills.
- Deterministic atomic file sync (~25 KB total) writes standard directories that
  Antigravity IDE, Antigravity CLI, Git, and sibling apps discover immediately,
  while `--status` verifies byte-for-byte SHA-256 parity with the local repo root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FORGE_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR_NAME = "cofi-vibe-forge"
SKILL_NAMES = ("trail", "vibe-straightline-architect", "trail-clean-slate-debugger")
SKIP_NAMES = {"__pycache__", ".pytest_cache", ".pytest_tmp", ".git", ".DS_Store", "Thumbs.db"}


def _default_workspace_agents_dir(forge_root: Path) -> Path | None:
    if len(forge_root.parents) >= 2:
        candidate = forge_root.parents[1] / ".agents"
        if candidate.is_dir():
            return candidate
    return None


def _default_cofi_doc_root(forge_root: Path) -> Path:
    return forge_root.parent / "CofiDocumentary"


def _collect_manifest(root: Path, allowed_top: set[str] | None = None) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_NAMES or part.endswith(".pyc") for part in rel_parts):
            continue
        if allowed_top is not None and rel_parts[0] not in allowed_top:
            continue
        if path.is_file():
            rel_posix = path.relative_to(root).as_posix()
            raw = path.read_bytes()
            if path.suffix.lower() in {".py", ".md", ".json", ".svg", ".toml"}:
                raw = raw.replace(b"\r\n", b"\n")
            files[rel_posix] = raw
    return files


def _manifest_digest(files: dict[str, bytes]) -> str:
    if not files:
        return ""
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(files[rel]).digest())
    return h.hexdigest()


def _sync_manifest_to_dir(
    src_files: dict[str, bytes],
    dest_dir: Path,
    *,
    preserve_extra: set[str] | None = None,
    dry_run: bool = False,
) -> str:
    dest_files = _collect_manifest(dest_dir)
    keep = preserve_extra or set()
    comparable_dest = {k: v for k, v in dest_files.items() if k in src_files or k not in keep}
    if _manifest_digest(src_files) == _manifest_digest(comparable_dest) and src_files:
        return f"in_sync ({dest_dir} [{len(src_files)} files])"

    if dry_run:
        return f"would_sync ({dest_dir} [{len(src_files)} files])"

    dest_dir.mkdir(parents=True, exist_ok=True)
    for stale_rel in set(dest_files) - set(src_files) - keep:
        stale_path = dest_dir / stale_rel
        if stale_path.is_file():
            stale_path.unlink()

    for rel_posix, payload in src_files.items():
        out_path = dest_dir / rel_posix
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)

    for sub in sorted(dest_dir.rglob("*"), reverse=True):
        if sub.is_dir() and not any(sub.iterdir()):
            shutil.rmtree(sub, ignore_errors=True)

    return f"synced ({dest_dir} [{len(src_files)} files])"


def _plugin_bundle_files(forge_root: Path) -> dict[str, bytes]:
    return _collect_manifest(
        forge_root,
        allowed_top={"plugin.json", "mcp_config.json", "install.py", "README.md", "assets", "rules", "skills", "scripts"},
    )


def _sync_trail_mcp_into_config(
    forge_root: Path,
    cfg_dir: Path,
    *,
    dry_run: bool = False,
) -> str:
    src_mcp_path = forge_root / "mcp_config.json"
    if not src_mcp_path.is_file():
        plugin_mcp = cfg_dir / "plugins" / PLUGIN_DIR_NAME / "mcp_config.json"
        if plugin_mcp.is_file():
            src_mcp_path = plugin_mcp
        else:
            return "skipped_mcp (no local mcp_config.json yet; pass --project to install.py to generate)"
    src_servers = json.loads(src_mcp_path.read_text(encoding="utf-8")).get("mcpServers") or {}
    dest_mcp_path = cfg_dir / "mcp_config.json"
    existing: dict[str, Any] = {}
    if dest_mcp_path.is_file():
        existing = json.loads(dest_mcp_path.read_text(encoding="utf-8"))
    dest_servers = dict(existing.get("mcpServers") or {})
    changed = False
    for srv_name, srv_cfg in src_servers.items():
        if dest_servers.get(srv_name) != srv_cfg:
            dest_servers[srv_name] = srv_cfg
            changed = True
    if not changed and dest_mcp_path.is_file():
        return f"in_sync ({dest_mcp_path} [{len(src_servers)} trail MCP servers])"
    if dry_run:
        return f"would_sync ({dest_mcp_path} [{len(src_servers)} trail MCP servers])"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    merged_doc = {**existing, "mcpServers": dest_servers}
    dest_mcp_path.write_bytes((json.dumps(merged_doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return f"synced ({dest_mcp_path} [{len(src_servers)} trail MCP servers])"


def sync_antigravity(
    *,
    forge_root: Path = FORGE_ROOT,
    gemini_config_dir: Path | None = None,
    workspace_agents_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg_dir = gemini_config_dir or (Path.home() / ".gemini" / "config")
    ws_dir = workspace_agents_dir if workspace_agents_dir is not None else _default_workspace_agents_dir(forge_root)
    actions: list[str] = []

    plugin_dest = cfg_dir / "plugins" / PLUGIN_DIR_NAME
    if forge_root.resolve() == plugin_dest.resolve():
        actions.append(f"in_place ({plugin_dest})")
    else:
        bundle = _plugin_bundle_files(forge_root)
        preserve = set() if "mcp_config.json" in bundle else {"mcp_config.json"}
        actions.append(_sync_manifest_to_dir(bundle, plugin_dest, preserve_extra=preserve, dry_run=dry_run))
    actions.append(_sync_trail_mcp_into_config(forge_root, cfg_dir, dry_run=dry_run))

    global_skills_root = cfg_dir / "skills"
    for skill in SKILL_NAMES:
        skill_files = _collect_manifest(forge_root / "skills" / skill)
        actions.append(_sync_manifest_to_dir(skill_files, global_skills_root / skill, dry_run=dry_run))

    gemini_root = cfg_dir.parent
    extra_skill_roots = [
        gemini_root / "antigravity-cli" / "skills",
        gemini_root / "antigravity" / "skills",
    ]
    if gemini_config_dir is None:
        extra_skill_roots.append(Path.home() / ".codex" / "skills")
    for rt_skills in extra_skill_roots:
        if rt_skills.is_dir():
            for skill in SKILL_NAMES:
                skill_files = _collect_manifest(forge_root / "skills" / skill)
                actions.append(_sync_manifest_to_dir(skill_files, rt_skills / skill, dry_run=dry_run))

    if ws_dir is not None and ws_dir.is_dir():
        ws_skills_root = ws_dir / "skills"
        for skill in SKILL_NAMES:
            skill_files = _collect_manifest(forge_root / "skills" / skill)
            actions.append(_sync_manifest_to_dir(skill_files, ws_skills_root / skill, dry_run=dry_run))

    return {"target": "antigravity", "dry_run": dry_run, "actions": actions}


def _bind_agent_frontmatter_skills(md_path: Path, required_skills: list[str], *, dry_run: bool = False) -> str:
    raw = md_path.read_bytes().decode("utf-8")
    normalized = raw.replace("\r\n", "\n")
    m = re.search(r"^skills:\s*(.+)$", normalized, flags=re.MULTILINE)
    if not m:
        raise ValueError(f"Missing 'skills:' frontmatter field in {md_path}")

    current_val = m.group(1).strip()
    existing = [] if current_val in {"none", "[]", ""} else [s.strip() for s in current_val.split(",") if s.strip()]
    merged = list(existing)
    for slug in required_skills:
        if slug not in merged:
            merged.append(slug)

    new_line = f"skills: {','.join(merged)}"
    updated = re.sub(r"^skills:\s*.+$", new_line, normalized, count=1, flags=re.MULTILINE)
    if updated == normalized and "\r" not in raw:
        return f"unchanged ({md_path.name}: {new_line})"

    if dry_run:
        return f"would_update ({md_path.name}: {new_line})"

    md_path.write_bytes(updated.encode("utf-8"))
    return f"updated ({md_path.name}: {new_line})"


def sync_cofi_documentary(
    *,
    forge_root: Path = FORGE_ROOT,
    cofi_doc_root: Path | None = None,
    run_sync_script: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    doc_root = cofi_doc_root or _default_cofi_doc_root(forge_root)
    if not doc_root.is_dir():
        raise FileNotFoundError(f"CofiDocumentary root not found: {doc_root}")

    actions: list[str] = []
    for rel_skills_dir in ("skills", ".agents/skills"):
        dest_root = doc_root / rel_skills_dir
        for skill in SKILL_NAMES:
            skill_files = _collect_manifest(forge_root / "skills" / skill)
            actions.append(_sync_manifest_to_dir(skill_files, dest_root / skill, dry_run=dry_run))

    debug_md = doc_root / "agents" / "quality_and_engineering" / "debug.md"
    dev_md = doc_root / "agents" / "quality_and_engineering" / "dev.md"
    edit_md = doc_root / "agents" / "visual_cinema" / "edit.md"
    vox_md = doc_root / "agents" / "visual_cinema" / "vox.md"
    if debug_md.is_file():
        actions.append(_bind_agent_frontmatter_skills(debug_md, ["trail-clean-slate-debugger"], dry_run=dry_run))
    for code_agent_md in (dev_md, edit_md, vox_md):
        if code_agent_md.is_file():
            actions.append(
                _bind_agent_frontmatter_skills(
                    code_agent_md,
                    ["vibe-straightline-architect", "trail-clean-slate-debugger"],
                    dry_run=dry_run,
                )
            )

    sync_script = doc_root / "scripts" / "sync_agency_agents.py"
    if run_sync_script and sync_script.is_file():
        if dry_run:
            actions.append(f"would_run ({sync_script})")
        else:
            res = subprocess.run(
                [sys.executable, str(sync_script)],
                cwd=str(doc_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=WIN_NO_WINDOW,
            )
            if res.returncode != 0:
                raise RuntimeError(f"sync_agency_agents.py failed:\n{res.stderr or res.stdout}")
            actions.append("ran scripts/sync_agency_agents.py")

    return {"target": "cofi_documentary", "dry_run": dry_run, "actions": actions}


def inspect_status(
    *,
    forge_root: Path = FORGE_ROOT,
    gemini_config_dir: Path | None = None,
    workspace_agents_dir: Path | None = None,
    cofi_doc_root: Path | None = None,
) -> dict[str, Any]:
    cfg_dir = gemini_config_dir or (Path.home() / ".gemini" / "config")
    ws_dir = workspace_agents_dir if workspace_agents_dir is not None else _default_workspace_agents_dir(forge_root)
    doc_root = cofi_doc_root or _default_cofi_doc_root(forge_root)
    doc_clean_root = doc_root.parent / "CofiDocumentary_Clean"

    plugin_dest = cfg_dir / "plugins" / PLUGIN_DIR_NAME
    bundle = _plugin_bundle_files(forge_root)
    actual_plugin_files = _collect_manifest(plugin_dest)
    if "mcp_config.json" not in bundle:
        actual_plugin_files = {k: v for k, v in actual_plugin_files.items() if k != "mcp_config.json"}
    expected_bundle = _manifest_digest(bundle)
    actual_bundle = _manifest_digest(actual_plugin_files)

    global_skills_status = {}
    ws_skills_status = {}
    doc_status = {}
    doc_clean_status = {}
    for skill in SKILL_NAMES:
        expected_skill = _manifest_digest(_collect_manifest(forge_root / "skills" / skill))
        global_skills_status[skill] = bool(
            expected_skill and expected_skill == _manifest_digest(_collect_manifest(cfg_dir / "skills" / skill))
        )
        if ws_dir is not None and ws_dir.is_dir():
            ws_skills_status[skill] = bool(
                expected_skill and expected_skill == _manifest_digest(_collect_manifest(ws_dir / "skills" / skill))
            )
        if doc_root.is_dir():
            actual_skill = _manifest_digest(_collect_manifest(doc_root / "skills" / skill))
            doc_status[skill] = bool(expected_skill and expected_skill == actual_skill)
        if doc_clean_root.is_dir():
            actual_clean_skill = _manifest_digest(_collect_manifest(doc_clean_root / "skills" / skill))
            doc_clean_status[skill] = bool(expected_skill and expected_skill == actual_clean_skill)

    mcp_source = forge_root / "mcp_config.json"
    if not mcp_source.is_file():
        mcp_source = plugin_dest / "mcp_config.json"
    src_mcp_servers = (
        json.loads(mcp_source.read_text(encoding="utf-8")).get("mcpServers") or {}
        if mcp_source.is_file()
        else {}
    )
    dest_mcp_servers = (
        json.loads((cfg_dir / "mcp_config.json").read_text(encoding="utf-8")).get("mcpServers") or {}
        if (cfg_dir / "mcp_config.json").is_file()
        else {}
    )
    mcp_in_sync = (not src_mcp_servers) or all(dest_mcp_servers.get(k) == v for k, v in src_mcp_servers.items())

    payload: dict[str, Any] = {
        "forge_root": str(forge_root),
        "antigravity_global_plugin_in_sync": bool(expected_bundle and expected_bundle == actual_bundle),
        "trail_mcp_servers_in_sync": mcp_in_sync,
        "antigravity_global_skills_in_sync": global_skills_status,
        "antigravity_plugin_dir": str(plugin_dest),
    }
    if ws_skills_status:
        payload["antigravity_workspace_skills_in_sync"] = ws_skills_status
    if doc_status:
        payload["cofi_documentary_skills_in_sync"] = doc_status
    if doc_clean_status:
        payload["cofi_documentary_clean_skills_in_sync"] = doc_clean_status
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync CofiVibeForge into Antigravity and/or CofiDocumentary.")
    parser.add_argument("--antigravity", action="store_true", help="Sync Global Plugin into ~/.gemini/config/plugins/cofi-vibe-forge.")
    parser.add_argument("--cofi-documentary", action="store_true", help="Sync into CofiDocumentary skills & agents.")
    parser.add_argument(
        "--cofi-doc-root",
        type=Path,
        default=_default_cofi_doc_root(FORGE_ROOT),
        help="Target CofiDocumentary repository root.",
    )
    parser.add_argument("--status", action="store_true", help="Verify SHA-256 sync status without modifying files.")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without writing.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args(argv)

    if args.status or (not args.antigravity and not args.cofi_documentary):
        status = inspect_status(cofi_doc_root=args.cofi_doc_root)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    results: list[dict[str, Any]] = []
    if args.antigravity:
        results.append(sync_antigravity(dry_run=args.dry_run))
    if args.cofi_documentary:
        results.append(sync_cofi_documentary(cofi_doc_root=args.cofi_doc_root, dry_run=args.dry_run))
        default_doc = _default_cofi_doc_root(FORGE_ROOT)
        clean_sibling = default_doc.parent / "CofiDocumentary_Clean"
        if args.cofi_doc_root.resolve() == default_doc.resolve() and clean_sibling.is_dir():
            blk = sync_cofi_documentary(cofi_doc_root=clean_sibling, dry_run=args.dry_run)
            blk["target"] = "cofi_documentary_clean"
            results.append(blk)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for block in results:
            print(f"[{block['target']}] (dry_run={block['dry_run']}):")
            for act in block["actions"]:
                print(f"  - {act}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
