---
name: vibe-straightline-architect
description: >-
  Spec-driven project scaffolding, directory tree & file-splitting discipline, and straight-line YAGNI implementation with zero hallucinated code. Activate whenever creating a new project, designing folder structures, splitting large modules into clean files, or implementing features where the user wants direct, linear, contradiction-free code (tạo project mới, chia file, cây thư mục chuẩn, code thẳng một mạch, cấm tự bịa code rác).
---

# Vibe Straight-Line Architect

Synthesizes **Spec-Driven Scaffolding** (`spec-kit` / `OpenSpec`), **Karpathy's Simplicity & Surgical Guidelines**, and **Boring Engineering's 4-Gate YAGNI Filter** into one strict workflow.

## Core Iron Law

**Never write speculative code, imaginary options, or multi-layer indirection when straight-line sequential logic (`A -> B -> C`) solves the requirement.**

---

## Mandatory 4-Phase Execution Protocol

### Phase 1 — Clarify & Lock the Project Blueprint (Before Creating Source Files)
1. **Think Before Coding**: State assumptions explicitly. If core inputs, outputs, or stack choices are ambiguous, ask concise clarifying questions instead of silently guessing.
2. **Existing Codebase Check**: If working inside an existing repository with `.trail/`, query Trail (`ask` / `trail_find_code` + `trail_repo_map`) first so new files reuse existing utilities and never duplicate what already exists.
3. **Emit Blueprint Contract**: For any new project or multi-file feature (`>= 2` new files), draft the file tree and single-responsibility table following [project_blueprint.md](./templates/project_blueprint.md):
   - Every file MUST have **one clear responsibility** and explicit **inputs -> outputs**.
   - **Right-sized file splitting**: Neither dump everything into a 1,500-line god-file nor shatter 60 lines of straight-line logic across 6 tiny wrapper files. Target `40–300` lines per cohesive module.
   - List **Explicit Non-Goals** (features/abstractions intentionally excluded).

### Phase 2 — The 4-Gate Pre-Code YAGNI Filter
Before creating any file, class, function, or parameter, pass all 4 gates:
1. **Requirement Filter (YAGNI)**: Did the user or runtime contract explicitly require this? If it is "just in case for the future", **drop it**.
2. **Reuse Check**: Does the standard library or current repo already provide this? Reuse it instead of reinventing a helper.
3. **Straight-Line Simplicity Check (KISS)**: Can this execute top-to-bottom as plain functions and plain data structures (`dict` / `dataclass` / typed interface)?
   - **BANNED**: Single-method classes/factories (`FooManager`, `BarService` with only `.run()`), single-call pass-through wrapper functions, unused optional parameters (`options=None`, `config=None`, `strict=False`), and silent fallback branches that invent fake default data when inputs are invalid.
4. **Rule-of-Three Abstraction Gate**: Never extract a generic base class, plugin registry, or strategy pattern until **3 concrete, distinct call sites** exist right now.

### Phase 3 — Sequential File-by-File Implementation
1. Implement strictly in dependency order: **Data Contracts / Schemas -> Pure Core Logic -> I/O Entrypoint -> Automated Tests**.
2. Keep data flow **unidirectional** (`Entrypoint -> Core -> Leaf Helpers`). Never create circular imports or two files mutating the same state in contradictory ways.
3. Fail fast with clear errors on invalid inputs instead of masking bugs behind speculative fallback defaults.

### Phase 4 — Automated Scaffold Guard + Test & Trail Indexing
1. Run the deterministic AST & blueprint verifier:
   ```bash
   python ~/.gemini/config/plugins/cofi-vibe-forge/skills/vibe-straightline-architect/scripts/scaffold_guard.py <target_dir> --max-lines 350
   ```
   *(Pass `--blueprint <path/to/blueprint.md>` whenever a blueprint file exists.)*
2. Resolve every reported violation (`GOD_FILE_EXCEEDED`, `SINGLE_METHOD_CLASS_BLOAT`, `TRIVIAL_PASSTHROUGH_WRAPPER`, `SPECULATIVE_UNUSED_PARAM`, `UNDECLARED_FILE`) by **simplifying or deleting** excess code.
3. Run the project's test suite (`pytest` / `npm test`) to confirm 100% green execution on real inputs.
4. If creating a brand-new Git repository and `trail` CLI is installed (`trail --version`), build code-graph indexing safely (`trail build`) so future debugging has instant `file:line` call graphs.
