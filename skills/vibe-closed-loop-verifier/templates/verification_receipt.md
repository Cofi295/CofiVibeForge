# Closed-Loop Live Verification Receipt

- **Verdict**: `VERIFIED_GREEN | FAILED_NEEDS_SELF_FIX`
- **Signature (`receipt_id`)**: `<sha256_16_hex>`
- **Verified At (UTC)**: `<YYYY-MM-DDTHH:MM:SSZ>`
- **Target Repo & HEAD**: `<repo>` (`<git_short_sha>`)
- **Touched Files**: `<file_1>`, `<file_2>`
- **Check 1 — Clean-Slate AST & Diff Audit**: `PASSED / FAILED` (errors=`0`, warnings=`0`)
- **Check 2 — Contradiction & Legacy Pattern Audit**: `PASSED / FAILED` (`DUPLICATE_SYMBOL_DEFINITION`, `UNREACHABLE_CODE_AFTER_RETURN`, `CROSS_FILE_CONSTANT_DRIFT`, `FORBIDDEN_LEGACY_PATTERN`)
- **Check 3 — Pytest Regression Suite**: `PASSED / FAILED / SKIPPED`
- **Check 4 — Unmocked Live Probes (`cp1252`)**: `<N>/<N> passed`
- **Check 5 — Real-Workspace Scale Replay**: `<workspace_path | SKIPPED>`
