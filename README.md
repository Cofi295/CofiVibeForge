# CofiVibeForge (`v2.2.0` — Closed-Loop Verifier + Auto-Trail Edition)

**Unified Antigravity Plugin + Dynamic Auto-Trail Code-Graph + Straight-Line Scaffolding + Clean-Slate Debugging + Closed-Loop Live Verification Suite**

Install **once** with a single command — **zero project paths required, zero `.git` required**. Touching *any* code folder or standalone file anywhere on disk automatically triggers:

1. **`trail` (`cofi_trail_auto` Dynamic MCP)** — Automatically builds & queries the local AST/SQLite code-graph on first touch (`<0.3s`, `$0`, works with or without Git) *before* reading or grepping files (`~80–95%` token & quota savings).
2. **`vibe-straightline-architect`** — Spec-driven directory/file-budget blueprints, linear `A -> B -> C` execution, strict 4-Gate YAGNI filter, and `scaffold_guard.py` bloat detector (zero speculative parameters, zero single-method classes, zero pass-through wrappers).
3. **`trail-clean-slate-debugger`** — Trail blast-radius localization, mandatory reproduction test *before* editing, clean deletion of broken legacy code (zero band-aid stacking), pre-edit self-critique, and `clean_slate_audit.py` AST/diff verification (including Producer–Consumer dict-key symmetry).
4. **`vibe-closed-loop-verifier`** — Mandatory 5-vector verification phase (`live_verify_loop.py`) combining Clean-Slate AST audit, intra/cross-file contradiction & forbidden-pattern audit (`--check-contradictions`, `--forbid`), pytest regression, unmocked live probes + Windows `cp1252` stdio survival (`--check-cp1252`), real-workspace scale replay (`--verify-workspace`), and signed `VERIFIED_GREEN` / `FAILED_NEEDS_SELF_FIX` verification receipts (`--receipt-out`).

---

## 🚀 1-Command Zero-Config Install (Install Once, Auto-Runs Everywhere)

> **Cài đặt 1 chạm duy nhất (Windows / macOS / Linux):** Không cần truyền đường dẫn dự án, không cần tạo Git trước. Cài xong là tự động bật mặc định cho mọi cửa sổ, mọi thư mục và mọi dòng code trên Antigravity!

**Windows (PowerShell):**
```powershell
git clone https://github.com/Cofi295/CofiVibeForge.git; python CofiVibeForge\install.py
```

**macOS / Linux / Git Bash:**
```bash
git clone https://github.com/Cofi295/CofiVibeForge.git && python3 CofiVibeForge/install.py
```

*(Requires Python 3.10+ and Node.js 18+. Automatically installs `@trailhq/trail-code` if missing and registers the universal `cofi_trail_auto` MCP router inside `~/.gemini/config/` — you can even delete the cloned `CofiVibeForge` folder afterward).*

---

## 📦 Repository Layout

```text
CofiVibeForge/
├── install.py                                      # 1-command zero-config installer (Win/macOS/Linux)
├── plugin.json                                     # Antigravity Plugin manifest (v2.2.0, auto-enabled)
├── mcp_config.example.json                         # Generated dynamic Auto-Trail MCP config example
├── assets/logo.svg                                 # Plugin badge
├── rules/AGENTS.md                                 # Always-on straight-line, clean-slate & verification constitution
├── skills/
│   ├── trail/SKILL.md                              # Dynamic Auto-Trail AST/SQLite code-graph skill
│   ├── vibe-straightline-architect/
│   │   ├── SKILL.md
│   │   ├── templates/project_blueprint.md
│   │   └── scripts/scaffold_guard.py               # AST & blueprint bloat detector
│   ├── trail-clean-slate-debugger/
│   │   ├── SKILL.md
│   │   ├── templates/debug_dossier.md
│   │   └── scripts/clean_slate_audit.py            # Git-diff, orphan/zombie-code & Producer-Consumer AST auditor
│   └── vibe-closed-loop-verifier/
│       ├── SKILL.md
│       ├── templates/verification_receipt.md       # Signed VERIFIED_GREEN / FAILED_NEEDS_SELF_FIX receipt template
│       └── scripts/live_verify_loop.py             # 5-vector verification, contradiction check & receipt generator
├── scripts/
│   ├── auto_trail_mcp.py                           # Zero-config dynamic Trail MCP router (any folder, no Git needed)
│   └── sync_integrations.py                        # Deterministic SHA-256 sync & status verifier
└── tests/
    └── test_vibe_forge.py                          # Automated pytest suite (unit + contradiction + live stdio MCP e2e)
```

---

## 🛠 Standalone Verification Guards

```bash
# 1. Audit a new module or project against speculative bloat
python ~/.gemini/config/plugins/cofi-vibe-forge/skills/vibe-straightline-architect/scripts/scaffold_guard.py <target_dir> --max-lines 350

# 2. Audit a bugfix git diff against band-aid stacking, zombie comments, swallowed errors, or key drift
python ~/.gemini/config/plugins/cofi-vibe-forge/skills/trail-clean-slate-debugger/scripts/clean_slate_audit.py --repo <repo_dir> --mode bugfix

# 3. Run full 5-vector closed-loop verification + contradiction audit + signed receipt
python ~/.gemini/config/plugins/cofi-vibe-forge/skills/vibe-closed-loop-verifier/scripts/live_verify_loop.py \
  --repo <repo_dir> --files <file_1> <file_2> --pytest <tests> --probe "<smoke_cmd>" \
  --check-cp1252 --check-contradictions --receipt-out verification_receipt.md

# 4. Run CofiVibeForge's test suite
pytest
```
