---
name: vibe-closed-loop-verifier
description: >-
  Autonomous QA & Closed-Loop Live Execution Verifier (Chuyên Gia Kiểm Định Thực Chiến & Tự Test – Tự Fix Khép Kín): forbids reporting a bugfix or feature as 'done' until verified by unmocked end-to-end execution on real data, Producer-Consumer contract probes, intra/cross-file contradiction audits, Windows cp1252/stdio & process-cleanup checks, and an autonomous Test -> Break -> Fix -> Re-Verify loop emitting a signed VERIFIED_GREEN receipt. Activate after EVERY code edit, bug fix, or feature implementation (kiểm định code, kiểm tra mâu thuẫn, tự test tự fix, test thực chiến, cấm báo xong khi chưa chạy thật).
---

# Vibe Closed-Loop Verifier (Chuyên Gia Kiểm Định Thực Chiến & Tự Test – Tự Fix)

Eliminates the most frustrating AI engineering failure mode:
- **Premature "Done" Reporting**: Editing code, running a tiny mocked unit test (`monkeypatch` / 2-item dummy `tmp_path`), and telling the user *"Đã fix xong và test sâu!"* — only for the real application to crash, drift, or contradict itself minutes later on production data.

---

## Iron Laws of Closed-Loop Verification

1. **ZERO UNVERIFIED "DONE" CLAIMS**:
   - Passing a mocked unit test (`monkeypatch.setattr`) or static syntax check is **NEVER** proof that a fix works.
   - You are **STRICTLY FORBIDDEN** from reporting a bug fix or feature as complete until you have executed the modified code path against **real unmocked inputs / real workspace data / live CLI or API entry points** and obtained a signed **`VERIFIED_GREEN`** receipt.
2. **AUTONOMOUS `TEST -> BREAK -> FIX -> RE-VERIFY` CLOSED LOOP**:
   - Act as an adversarial QA engineer trying to **break your own patch** before the user ever touches it.
   - Whenever a clean-slate check, contradiction audit, live probe, unmocked Producer–Consumer test, or scale replay fails (`FAILED_NEEDS_SELF_FIX`), **DO NOT stop and DO NOT report to the user yet** — immediately loop back into `trail-clean-slate-debugger`, fix the newly exposed root cause cleanly, and re-run the full verification loop until **`VERIFIED_GREEN`**.

---

## Mandatory 5-Vector Live Verification Protocol

### Vector 1 — Unmocked Producer-to-Consumer Pipeline Probe (Zero `monkeypatch` Across Boundaries)
1. Identify the **Producer** (the function/CLI writing files, JSON registries, or state) and the **Consumer / Critic** (the function reading, auditing, or orchestrating that output).
2. Execute the real Producer output directly into the real Consumer/Critic with **zero mocks** between them.
3. Verify 1-to-1 parity across file/directory paths, returned dictionary keys (`PRODUCER_CONSUMER_KEY_DRIFT = 0`), cache version keys, and pass/fail thresholds.

### Vector 2 — Intra-File & Cross-File Contradiction Audit (`--check-contradictions` + `--forbid`)
1. Verify zero duplicate top-level symbol/constant definitions (`DUPLICATE_SYMBOL_DEFINITION`), zero unreachable dead code left after `return`/`raise` (`UNREACHABLE_CODE_AFTER_RETURN`), and zero conflicting constant values across touched files (`CROSS_FILE_CONSTANT_DRIFT`).
2. Whenever replacing a legacy rule/threshold, pass `--forbid "<legacy_regex>"` to prove zero stale occurrences survive in touched files (`FORBIDDEN_LEGACY_PATTERN = 0`).

### Vector 3 — Real Production Data & Full-Scale Replay (`--verify-workspace`)
1. Never stop at 2-row synthetic test fixtures when statistical, concurrency, or batching rules (`>= 5` items, `100+` beats, parallel workers) exist in the consumer.
2. Run the real critic/validator directly against a **real workspace or production dataset on disk** using the full production configuration dictionary.

### Vector 4 — Runtime Environment, Encoding & Process-Tree Hygiene Probe
1. **Windows `cp1252` Stdio Survival**: For any CLI, worker, or MCP server emitting JSON/Unicode (`ensure_ascii=False`), run a live probe under `PYTHONIOENCODING=cp1252` (`--check-cp1252`) to confirm it never crashes with `UnicodeEncodeError`.
2. **Zero Orphan Subprocess Trees**: Verify that any spawned worker (`subprocess.Popen`, persistent CLI session) deterministically terminates its process tree (`.stop()` / `taskkill /T /F`) in a `finally:` block.

### Vector 5 — Automated Closed-Loop Runner & Signed Receipt (`live_verify_loop.py`)
Run the bundled verification runner before declaring any coding or debugging task complete:
```bash
python ~/.gemini/config/plugins/cofi-vibe-forge/skills/vibe-closed-loop-verifier/scripts/live_verify_loop.py \
  --repo <repo_root> \
  --files <touched_file_1> <touched_file_2> \
  --pytest <test_file_1> \
  --probe "<real_unmocked_cli_or_python_one_liner>" \
  --check-cp1252 \
  --check-contradictions \
  --receipt-out <optional_receipt.md>
```
- If `live_verify_loop.py` outputs `FAILED_NEEDS_SELF_FIX`: fix the exact failure immediately in the same turn and re-run `live_verify_loop.py`.
- Only report completion to the user once `live_verify_loop.py` outputs **`[live_verify_loop] VERIFIED_GREEN (sig=...)`**.
