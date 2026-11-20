# COFI VIBE FORGE — STRAIGHT-LINE & CLEAN-SLATE ENGINEERING CONSTITUTION

These laws govern project scaffolding, feature implementation, and debugging across all sessions while `cofi-vibe-forge` is active.

## 1. Straight-Line Coding & Anti-Hallucination Law (Zero Speculative Bloat)
- **Blueprint Before Scaffolding**: When creating a new project or multi-file module, activate `vibe-straightline-architect` FIRST. Lock the directory tree, single responsibility per file, and explicit I/O contracts before writing implementation code.
- **Straight-Line Execution (`A -> B -> C`)**: If 40 lines of direct sequential code solve the exact requirement, NEVER write 150 lines of classes, factories, registries, or adapters.
- **Strict YAGNI Ban**: NEVER invent unrequested config flags, unused optional parameters, single-call wrapper functions, single-method classes, or speculative "future-proof" fallback branches.
- **No Drive-By Edits**: Touch only the files and symbols required by the task. Never reformat or refactor unrelated neighbors.

## 2. Trail-First Surgical Localization (Zero Blind File Scanning)
- When `.trail/` or a Trail MCP server (`trail`, `trail_remotion`, `trail_frames`, `cofitrail`) is present in the target workspace, ALWAYS query Trail (`ask` / `trail_find_code`, `callers` / `trail_trace_calls`, and `.trail/learnings/`) BEFORE grepping or reading source files broadly.
- Read only targeted line slices (`StartLine..EndLine`) around the identified symbols.

## 3. Clean-Slate Debugging & Self-Critique Law (Zero Band-Aid Stacking)
When fixing any bug, regression, or contradiction, activate `trail-clean-slate-debugger` and obey this strict sequence:
1. **Prove Bug Before Editing**: Run an isolated test or minimal reproducer command against the suspected code FIRST to confirm whether it actually fails or whether upstream data / conflicting logic is the real culprit. Never guess from static reading alone.
2. **Delete Broken Old Code Cleanly**: Identify the exact broken or contradictory legacy lines and **DELETE/REPLACE them**. NEVER leave broken old code alive and stack new `if/else`, `try/except`, or override patches underneath to fight its output. Never leave commented-out zombie code.
3. **Adversarial Self-Critique Before `edit_file`**: Critique your own proposed patch against callers/callees, hidden state conflicts, and line-count simplicity until the draft is contradiction-free, then apply it.
4. **Test Loop + Diff Audit Until 100% Clean**: Re-run the reproducer test, sibling regression tests, and `clean_slate_audit.py` until green with zero orphan imports or band-aid bloat.
