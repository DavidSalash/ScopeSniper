# Static Solidity AST Metric Scanner & Dynamic Complexity Index Specification

## Architectural Overview

The Static Solidity AST Metric Scanner Subsystem (`core/ast_scanner.py`) introduces automated code complexity extraction across targeted Solidity smart contracts. It extracts structural metrics from raw Solidity source strings, persists them into SQLite schema (`ast_metrics`), and dynamically calculates the time complexity index ($T$) in the target profitability engine (`core/math_engine.py`).

---

## 1. Metric Extraction Algorithms & Regular Expressions

The metric scanner processes Solidity code strings in four distinct analytical phases:

### A. Code Sanitization
Before metric extraction, single-line comments (`//...`), multi-line comments (`/* ... */`), and string literals (`"..."` / `'...'`) are replaced with empty spaces to avoid false positive matches while preserving original character offsets.

### B. Structural Metrics

1. **Total Functions (`total_functions`)**
   - **Pattern**: `\bfunction\s+(\w+)`
   - **Description**: Identifies all function declarations in the target Solidity file.

2. **External Calls (`external_calls_count`)**
   - **Pattern**: `\.(call|delegatecall|staticcall|transfer|send)\b`
   - **Description**: Traces outbound transfer and execution hooks to measure external contract interaction density.

3. **State Mutations (`state_mutations_count`)**
   - **Pattern**: `(?:==|>=|<=|!=|=>)|(\+\+|--|\+=|-=|\*=|/=|%=|\|=|&=|\^=|=)`
   - **Description**: Counts state mutations and assignment operations while explicitly ignoring boolean comparison operators.

4. **Max Loop Nesting Depth (`max_loop_depth`)**
   - **Pattern**: `\b(for|while)\b\s*\(.*?\)\s*$`
   - **Algorithm**: Walks through cleaned tokens character-by-character while maintaining a stack tracker of brace levels. Whenever a `for` or `while` loop pattern is detected immediately preceding an opening brace `{`, the stack depth is incremented and maximum achieved depth is recorded.

---

## 2. Dynamic Time Complexity Index ($T$) Formula

The legacy static multiplier model has been refactored in `core/math_engine.py` to use dynamic, data-driven parameters:

$$T = \text{Files Count} \times \text{Depth Factor} \times \text{Call Factor} \times (1.5 \text{ if KYC required else } 1.0)$$

Where:
- **Files Count**: Sourced from total scope assets linked to the `project_slug` (fallback: 5 if 0).
- **Depth Factor**: $1.0 + (0.15 \times \text{max\_loop\_depth})$ (fallback `max_loop` default: 1).
- **Call Factor**: $1.0 + (0.02 \times \text{external\_calls\_count})$ (fallback `total_calls` default: 2).
- **KYC Multiplier**: $1.5$ if identity verification is mandated, otherwise $1.0$.

---

## 3. Pre-Compiled Global Cache Lookup Architecture

To prevent $O(N \times M)$ query bottlenecks during yield ranking calculations, `get_target_profitability_matrix(conn)` executes a single pre-compiled aggregation query prior to iteration:

```sql
SELECT project_slug, 
       SUM(total_functions) as total_funcs,
       MAX(max_loop_depth) as max_loop,
       SUM(external_calls_count) as total_calls,
       SUM(state_mutations_count) as total_muts
FROM ast_metrics GROUP BY project_slug;
```

This map is indexed in memory by `project_slug` for $O(1)$ constant-time metric retrieval during profitability ranking.
