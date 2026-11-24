---
name: trail-clean-slate-debugger
description: >-
  Evidence-driven root-cause debugging combining Trail call-graph localization, mandatory direct test reproduction before editing, clean-slate deletion of broken legacy code (zero band-aid stacking), pre-edit adversarial self-critique, and post-fix diff/regression verification. Activate whenever fixing bugs, resolving regressions, eliminating conflicting logic, or debugging errors (sửa lỗi, fix bug không đoán bừa, xóa code cũ sai, phản biện trước khi code, kết hợp trail).
---

# Trail Clean-Slate Debugger

Eliminates the two worst AI debugging failure modes:
1. **Blind Multi-File Guessing**: Reading 10+ files randomly and guessing a cause without running a direct reproduction test.
2. **Band-Aid Stacking (Additive Bloat)**: Leaving broken old logic alive and stacking new `if/else`, `try/except`, or override code underneath to fight the old code's wrong output — causing cascading contradictions and runaway file bloat.

---

## Mandatory 6-Gate Debugging Loop (Never Skip a Gate)

### Gate 1 — Pinpoint via Trail Graph & Past Learnings (Zero Blind Scanning)
1. **Check `.trail/` First**:
   - Via MCP (`trail`, `trail_remotion`, `trail_frames`, `cofitrail`): call `trail_find_code` + `trail_trace_calls` (`direction="in"` for callers, `direction="out"` for callees).
   - Or via CLI: `trail ask "<symptom or symbol>" --source` and `trail callers <symbol>`.
   - Read matching `.trail/learnings/` entries first so previously ruled-out approaches are never repeated.
2. **Fallback (Only When Repo Has No `.trail/`)**: Trace from exact stack-trace `file:line` or targeted symbol search — never read entire large files top-to-bottom.
3. Read **only** the surgical line slices (`StartLine..EndLine`) of the target function and its immediate boundary.

### Gate 2 — Critique the Symptom & Run Direct Reproduction Proof (NO EDITS YET)
**IRON LAW: Zero source-code edits are allowed before runtime proof.**
1. Ask skeptically: *"Is this function actually broken, or is upstream caller data already corrupt, or are two existing code paths mutating the same state in opposite directions?"*
2. Run an existing failing test OR execute a minimal, isolated reproduction command/test targeting the exact function and inputs.
3. Observe the real output:
   - **Confirmed Red Failure / Contradiction**: Record the exact failing input, actual output, and offending `file:StartLine-EndLine`. Proceed to Gate 3.
   - **Passes Cleanly in Isolation**: Do NOT touch this function! Use `trail_trace_calls` to step one hop upstream/downstream and test the real culprit.
4. **3-Strike Escalation Rule**: If 3 hypotheses fail reproduction, stop guessing, summarize verified facts vs ruled-out paths, and check architectural assumptions with the user.

### Gate 3 — Clean-Slate Deletion Plan (Zero Band-Aid Law)
1. List every obsolete, broken, or contradictory block (`file:StartLine-EndLine`) that **MUST BE DELETED OR REPLACED**.
2. **STRICTLY FORBIDDEN**:
   - Keeping broken old calculation/state logic and adding a second pass underneath to overwrite, clamp, or work around its wrong output.
   - Wrapping broken logic in `except Exception: pass` or silent fallback defaults to hide the crash.
   - Commenting out old broken lines (`# old code...`) instead of deleting them cleanly.

### Gate 4 — Adversarial Self-Critique of the Proposed Code (Before `edit_file`)
Draft the exact replacement code mentally/in scratch and run a ruthless 4-point critique **before modifying any source file**:
1. **Blast-Radius Contract Check**: Will every caller and callee from Gate 1 (`trail_trace_calls`) receive the exact types, keys, and invariants it expects?
2. **Zero-Contradiction Check**: After deleting the broken lines in Gate 3, is there any sibling branch, cache, or fallback left in the file/module that contradicts the new logic?
3. **Straight-Line Compression Check**: Is the new code a single clear linear flow without speculative parameters, redundant guards, or single-use helpers?
4. **Edge-Case Check**: How does the draft behave on empty, boundary, or malformed inputs (fail fast vs silent corruption)?
5. **Producer–Consumer Contract Symmetry Check (Zero Mock-Masked Drift)**: Do the producer function (writer/fetcher/renderer) and consumer function (critic/auditor/coordinator) share identical directory paths, JSON keys, cache version prefixes, and pass/fail thresholds without `monkeypatch` hiding a mismatch?
6. **Subprocess & Session Lifecycle Cleanup Check**: Does every spawned worker process or persistent CLI session (`subprocess.Popen` / `GoalSession`) deterministically terminate its process tree (`.stop()` / `taskkill /T /F`) in a `finally:` block when the turn finishes?
*If ANY check fails -> revise the draft before touching the file. Repeat until all 6 pass.*

### Gate 5 — Surgical Edit, Real-Workspace Scale Replay & Clean-Slate Diff Audit
1. Apply the clean replacement (`edit_file`) — deleting the broken legacy lines cleanly.
2. Re-run the Gate 2 reproduction test: confirm deterministic **RED -> GREEN** transition.
3. Run the broader module/regression test suite (`pytest` / `npm test`) until **100% green** (if a test fails, return to Gate 2/4 — never weaken assertions to force green).
4. **Mandatory Real-Workspace Scale Replay**: When fixing pipeline/critic/media gates, never rely solely on 2-clip synthetic unit tests or mocked critics — run the unmocked critic directly against a real multi-act workspace (`100+` beats) with the full job config (`--verify-workspace <workspace_path>`).
5. Run the automated Clean-Slate Diff Auditor before declaring completion:
   ```bash
   python ~/.gemini/config/plugins/cofi-vibe-forge/skills/trail-clean-slate-debugger/scripts/clean_slate_audit.py --repo <repo_root> --mode bugfix --verify-workspace <optional_real_workspace>
   ```
   Resolve any `SWALLOWED_EXCEPTION`, `COMMENTED_ZOMBIE_CODE`, `ORPHAN_IMPORT`, `BAND_AID_STACKING_SUSPECT`, `UNCLOSED_SUBPROCESS_POPEN`, `REAL_WORKSPACE_CONTRACT_FAILURE`, or `SYNTAX_ERROR` findings immediately.

### Gate 6 — Record Institutional Memory (`trail note` / `trail check`)
- If `.trail/` is active in the repository:
  1. When the root cause was non-obvious or a tempting approach failed, save a concise learning (`trail note --title "<fact learned>"`) naming exact files/symbols and why the wrong path was ruled out.
  2. Run `trail check` (or rebuild stale index if structural symbols changed) before committing.
