# Clean-Slate Debug Dossier (6-Gate Checklist)

1. **Gate 1 — Trail Localization**:
   - Target symbol & span: `<file:StartLine-EndLine>`
   - Callers / Callees checked: `<list from trail_trace_calls>`
   - Relevant `.trail/learnings/`: `<none or summary>`
2. **Gate 2 — Direct Reproduction Proof (Pre-Edit)**:
   - Command / Test executed: `<exact command>`
   - Observed failure / contradiction: `<actual vs expected>`
3. **Gate 3 — Broken Legacy Code Slated for Deletion**:
   - Lines to DELETE cleanly: `<file:StartLine-EndLine — why it was wrong/contradictory>`
4. **Gate 4 — Pre-Edit Adversarial Self-Critique**:
   - Caller/callee contract intact? `[x]`
   - Sibling/state contradictions eliminated? `[x]`
   - Straight-line minimal diff (0 speculative bloat)? `[x]`
5. **Gate 5 — Verification & Diff Audit**:
   - Reproducer test: `RED -> GREEN`
   - Regression suite: `<X passed, 0 failed>`
   - `clean_slate_audit.py`: `PASSED`
6. **Gate 6 — Trail Memory**:
   - `trail note` / `trail check`: `<recorded or N/A>`
