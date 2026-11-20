---
name: trail
description: >-
  Unified Trail Code-Graph & Institutional Learnings skill bundled inside CofiVibeForge. Use on EVERY coding, architecture, or debugging task in indexed repositories before reading or grepping source files: query Trail MCP (`trail_find_code`, `trail_find_all`, `trail_file_api`, `trail_trace_calls`, `trail_repo_map`, `trail_check_freshness`) or CLI (`trail ask`, `trail grep`, `trail skeleton`, `trail callers`, `trail map`, `trail note`, `trail check`), read `.trail/learnings/`, slice only targeted `StartLine..EndLine`, and report `🌱 trail saved ~N tokens this turn`.
---

# Trail Code-Graph & Institutional Memory (Bundled in CofiVibeForge)

## 1. Mandatory Trail-First Discipline
- **Before reading or grepping source files**, query Trail first (`$0`, local SQLite/AST graph in `.trail/cache/` + `.trail/learnings/`, `<1s`).
- **Never run `trail init --no-agents` on Windows**: it strips Gemini/Antigravity MCP registrations. Always refresh indexes safely via `trail build` (or `python ~/.gemini/config/plugins/cofi-vibe-forge/install.py --project <repo_root>`).

## 2. Direct MCP Tool Surface (Zero-Config Dynamic `cofi_trail_auto` + Per-Repo Servers)
Call `call_mcp_tool` directly on `cofi_trail_auto` (works automatically on **ANY** folder or standalone code file on disk — zero `.git` or `--project` setup required, auto-indexes in `<0.3s` on first touch; pass `"dir": "<folder_path>"` when in a drive root or subfolder) or on a dedicated repo server (`trail`, `trail_<project>`, `cofitrail`):
1. `trail_file_api({"file": "/path/to/app.py"})` (or `{"file": "src/service.py", "dir": "/path/to/folder"}`) — full file signatures & `Lstart-Lend` spans (`~10–15x` cheaper than reading whole files).
2. `trail_find_code({"query": "<question or symbol>", "dir": "/path/to/folder", "limit": 5})` — ranked code cruxes + matching `.trail/learnings/`.
3. `trail_find_all({"pattern": "<symbol_or_regex>", "dir": "/path/to/folder"})` — exhaustive symbol-grouped search across all indexed files.
4. `trail_trace_calls({"symbol": "<fn_or_class>", "dir": "/path/to/folder", "direction": "in" | "out", "depth": 2})` — exact call/reference blast radius before editing, renaming, or deleting.
5. `trail_repo_map({"dir": "/path/to/folder"})` — token-budgeted architectural overview of directory clusters and hubs.

## 3. CLI Surface (Fallback)
Run `trail` (or `npx @trailhq/trail-code`) inside the repository root:
- `trail ask "<question>" --source -n 5`
- `trail grep "<pattern>"`
- `trail skeleton <file>`
- `trail callers <symbol> --depth 2`
- `trail map`
- `trail build` (safe incremental graph refresh)

## 4. Institutional Learnings (`trail note` & `trail check`)
- Past decisions and ruled-out approaches live in `.trail/learnings/*.md`. Read matching learnings returned by `trail_find_code` / `trail ask` before exploring.
- When a session uncovers a non-obvious root cause, a dropped approach, or a user correction that code alone cannot tell the next session, record it via `trail note --title "<concise fact>"` with `## Decided` and `## Tried and ruled out` on stdin.
- Run `trail check` before committing when `.trail/learnings/` rules apply.

## 5. Mandatory Token Savings Credit
Every Trail retrieval output starts with `[trail] tokens saved ≈ N`. Sum `N` across all Trail calls in the turn and close your reply with:
`🌱 trail saved ~N tokens this turn`
