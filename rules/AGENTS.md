# COFI VIBE FORGE — STRAIGHT-LINE & CLEAN-SLATE ENGINEERING CONSTITUTION

These laws govern project scaffolding, feature implementation, and debugging across all sessions while `cofi-vibe-forge` is active.

## 1. Straight-Line Coding & Anti-Hallucination Law (Zero Speculative Bloat)
- **Blueprint Before Scaffolding**: When creating a new project or multi-file module, activate `vibe-straightline-architect` FIRST. Lock the directory tree, single responsibility per file, and explicit I/O contracts before writing implementation code.
- **Straight-Line Execution (`A -> B -> C`)**: If 40 lines of direct sequential code solve the exact requirement, NEVER write 150 lines of classes, factories, registries, or adapters.
- **Strict YAGNI Ban**: NEVER invent unrequested config flags, unused optional parameters, single-call wrapper functions, single-method classes, or speculative "future-proof" fallback branches.
- **No Drive-By Edits**: Touch only the files and symbols required by the task. Never reformat or refactor unrelated neighbors.

## 2. Zero-Config Trail-First Surgical Localization (Works On ANY Code Folder Without Git)
- Whenever touching ANY code file or folder, ALWAYS query Trail FIRST (`cofi_trail_auto` — or any dedicated repo Trail MCP server such as `trail`, `trail_remotion`, `trail_frames`) BEFORE grepping or reading whole files.
- `cofi_trail_auto` works on ANY folder or standalone script even without `.git` or pre-registration (auto-builds the AST graph in `<0.3s` on first touch): pass `"dir": "<target_code_folder>"` (or an absolute `"file"` path in `trail_file_api`) whenever working in a subfolder or drive root.
- Read only targeted line slices (`StartLine..EndLine`) around the identified symbols.

## 3. Clean-Slate Debugging & Self-Critique Law (Zero Band-Aid Stacking)
When fixing any bug, regression, or contradiction, activate `trail-clean-slate-debugger` and obey this strict sequence:
1. **Prove Bug Before Editing**: Run an isolated test or minimal reproducer command against the suspected code FIRST to confirm whether it actually fails or whether upstream data / conflicting logic is the real culprit. Never guess from static reading alone.
2. **Delete Broken Old Code Cleanly**: Identify the exact broken or contradictory legacy lines and **DELETE/REPLACE them**. NEVER leave broken old code alive and stack new `if/else`, `try/except`, or override patches underneath to fight its output. Never leave commented-out zombie code.
3. **Adversarial Self-Critique Before `edit_file`**: Critique your own proposed patch against callers/callees, hidden state conflicts, and line-count simplicity until the draft is contradiction-free, then apply it.
4. **Test Loop + Diff Audit Until 100% Clean**: Re-run the reproducer test, sibling regression tests, and `clean_slate_audit.py` until green with zero orphan imports or band-aid bloat.
