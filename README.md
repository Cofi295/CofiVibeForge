# CofiVibeForge (`v2.0.0`)

**Unified Antigravity Plugin + Trail Code-Graph + Straight-Line Scaffolding + Clean-Slate Debugging Suite**

Bundles three engineering skills, an always-on engineering constitution (`rules/AGENTS.md`), and AST/diff auditors into a single auto-enabled Antigravity plugin:

1. **`trail`** — Queries local AST/SQLite code-graph & institutional memory (`.trail/learnings/`) *before* reading or grepping files (`~80–95%` token savings).
2. **`vibe-straightline-architect`** — Spec-driven directory/file-budget blueprints, linear `A -> B -> C` execution, strict 4-Gate YAGNI filter, and `scaffold_guard.py` bloat detector (zero speculative parameters, zero single-method classes, zero pass-through wrappers).
3. **`trail-clean-slate-debugger`** — Trail blast-radius localization, mandatory reproduction test *before* editing, clean deletion of broken legacy code (zero band-aid stacking), pre-edit self-critique, and `clean_slate_audit.py` diff verification.

---

## 🚀 1-Command Install (Auto-Enabled in Antigravity)

> **Cài đặt 1 chạm (Windows / macOS / Linux):** Plugin nằm trong `~/.gemini/config/plugins/cofi-vibe-forge` sẽ **tự động bật mặc định** cho mọi cửa sổ và mọi phiên chat Antigravity mà không cần cấu hình thủ công.

### Option A — Full Install (Plugin + Rules + 3 Skills + Auto Trail MCP for Your Repo)

**macOS / Linux / Git Bash:**
```bash
git clone https://github.com/Cofi295/CofiVibeForge.git && python3 CofiVibeForge/install.py --project /path/to/your-project
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/Cofi295/CofiVibeForge.git; python CofiVibeForge\install.py --project D:\path\to\your-project
```
*(You can pass `--project` multiple times for multiple repositories, e.g. `--project app=/path/to/app --project web=/path/to/web`. Requires Python 3.10+ and Node.js 18+ for `@trailhq/trail-code` MCP).*

### Option B — Instant Zero-Script Clone (Rules + Skills Only in 3 Seconds)

**macOS / Linux:**
```bash
git clone https://github.com/Cofi295/CofiVibeForge.git ~/.gemini/config/plugins/cofi-vibe-forge
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/Cofi295/CofiVibeForge.git "$HOME\.gemini\config\plugins\cofi-vibe-forge"
```
*(Reload or open a new Antigravity window — active immediately on every chat turn. You can bind Trail MCP repos anytime later via `python ~/.gemini/config/plugins/cofi-vibe-forge/install.py --project <repo_dir>`).*

---

## 📦 Repository Layout

```text
CofiVibeForge/
├── install.py                                      # 1-command cross-platform installer (Win/macOS/Linux)
├── plugin.json                                     # Antigravity Plugin manifest (auto-enabled)
├── mcp_config.example.json                         # Example Trail MCP server config (generated per machine)
├── assets/logo.svg                                 # Plugin badge
├── rules/AGENTS.md                                 # Always-on straight-line & clean-slate constitution
├── skills/
│   ├── trail/SKILL.md                              # Trail AST/SQLite code-graph & learnings skill
│   ├── vibe-straightline-architect/
│   │   ├── SKILL.md
│   │   ├── templates/project_blueprint.md
│   │   └── scripts/scaffold_guard.py               # AST & blueprint bloat detector
│   └── trail-clean-slate-debugger/
│       ├── SKILL.md
│       ├── templates/debug_dossier.md
│       └── scripts/clean_slate_audit.py            # Git-diff & orphan/zombie-code auditor
├── scripts/
│   └── sync_integrations.py                        # Deterministic SHA-256 sync & status verifier
└── tests/
    └── test_vibe_forge.py                          # Automated pytest suite
```

---

## 🛠 Standalone Verification Guards

```bash
# 1. Audit a new module or project against speculative bloat
python ~/.gemini/config/plugins/cofi-vibe-forge/skills/vibe-straightline-architect/scripts/scaffold_guard.py <target_dir> --max-lines 350

# 2. Audit a bugfix git diff against band-aid stacking, zombie comments, or swallowed errors
python ~/.gemini/config/plugins/cofi-vibe-forge/skills/trail-clean-slate-debugger/scripts/clean_slate_audit.py --repo <repo_dir> --mode bugfix

# 3. Run CofiVibeForge's own test suite
pytest
```
