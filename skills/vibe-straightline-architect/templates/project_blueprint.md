# Project / Feature Blueprint Contract

## 1. Goal & Straight-Line Data Flow
- **Objective**: `<One-sentence statement of exact problem solved>`
- **Linear Pipeline (`A -> B -> C`)**: `<Input> -> <Step 1> -> <Step 2> -> <Output>`
- **Explicit Non-Goals (Banned Bloat)**:
  - No unrequested config loaders, plugin registries, or speculative flags.
  - No single-use wrapper classes or fallback mock data.

## 2. Approved Directory Tree & File Budget
<!-- scaffold_guard.py parses the markdown table below when --blueprint is supplied -->

| File Path | Single Responsibility | Max Lines | Allowed Imports (Internal) |
| :--- | :--- | :--- | :--- |
| `src/models.py` | Pure data schemas & validation contracts | 120 | `(none)` |
| `src/core.py` | Straight-line domain transformation logic | 220 | `src.models` |
| `src/cli.py` | Thin CLI / API entrypoint & I/O wiring | 120 | `src.models`, `src.core` |
| `tests/test_core.py` | Deterministic end-to-end & edge-case tests | 200 | `src.*` |

## 3. Core Signatures & Contracts
- `<function_name>(<required_inputs>) -> <exact_return_type>`: `<behavior & fail-fast error contract>`
