import re
import sqlite3
from typing import Dict, Any
from core.database import DB_LOCK

def strip_comments_and_strings(code: str) -> str:
    """
    Strips single-line // comments, multi-line /* */ comments,
    and string literals ("..." and '...') from Solidity code.
    Replaces string/comment characters with spaces to preserve character index offsets.
    """
    pattern = r'//[^\n]*|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"'
    return re.sub(pattern, lambda m: ' ' * len(m.group(0)), code, flags=re.DOTALL | re.MULTILINE)

def scan_solidity_source_metrics(project_slug: str, asset_identifier: str, source_code: str) -> Dict[str, Any]:
    """
    Scans a raw Solidity source code string to compute key structural metrics:
    - total_functions
    - max_loop_depth
    - external_calls_count
    - state_mutations_count
    """
    clean_code = strip_comments_and_strings(source_code)

    # 1. total_functions: Match function declarations via r"\bfunction\s+(\w+)"
    func_pattern = r"\bfunction\s+(\w+)"
    functions = re.findall(func_pattern, clean_code)
    total_functions = len(functions)

    # 2. external_calls_count: Match outbound execution patterns via r"\.(call|delegatecall|staticcall|transfer|send)\b"
    ext_call_pattern = r"\.(call|delegatecall|staticcall|transfer|send)\b"
    external_calls = re.findall(ext_call_pattern, clean_code)
    external_calls_count = len(external_calls)

    # 3. state_mutations_count: Match assignment / mutation operators
    # Exclude comparison operators (==, >=, <=, !=, =>)
    # Match =, +=, -=, *=, /=, %=, |=, &=, ^=, ++, --
    mutation_pattern = r"(?:==|>=|<=|!=|=>)|(\+\+|--|\+=|-=|\*=|/=|%=|\|=|&=|\^=|=)"
    mutations_count = 0
    for match in re.finditer(mutation_pattern, clean_code):
        if match.group(1):  # Group 1 matched mutation operator
            mutations_count += 1
    state_mutations_count = mutations_count

    # 4. max_loop_depth: Trace loop patterns and brace depth with balanced paren matching
    loop_brace_positions = set()
    has_braceless_loop = False

    for loop_match in re.finditer(r"\b(for|while)\b", clean_code):
        start_idx = loop_match.end()
        # Find opening '(' of loop header
        open_paren_idx = clean_code.find('(', start_idx)
        if open_paren_idx != -1 and open_paren_idx - start_idx < 10:
            # Walk balanced parentheses to handle nested calls e.g. for(uint i=0; i<max(10, total); i++)
            paren_depth = 1
            idx = open_paren_idx + 1
            length = len(clean_code)
            while idx < length and paren_depth > 0:
                if clean_code[idx] == '(':
                    paren_depth += 1
                elif clean_code[idx] == ')':
                    paren_depth -= 1
                idx += 1

            if paren_depth == 0:
                # Look ahead past whitespace for opening brace '{'
                remainder = clean_code[idx:]
                next_non_space = re.search(r"\S", remainder)
                if next_non_space and next_non_space.group(0) == '{':
                    brace_pos = idx + next_non_space.start()
                    loop_brace_positions.add(brace_pos)
                else:
                    has_braceless_loop = True

    max_loop_depth = 0
    current_brace_depth = 0
    active_loops = []  # Stack of brace depths at which loop braces were opened

    for i, ch in enumerate(clean_code):
        if ch == '{':
            current_brace_depth += 1
            if i in loop_brace_positions:
                active_loops.append(current_brace_depth)
                if len(active_loops) > max_loop_depth:
                    max_loop_depth = len(active_loops)
        elif ch == '}':
            if active_loops and active_loops[-1] == current_brace_depth:
                active_loops.pop()
            current_brace_depth = max(0, current_brace_depth - 1)

    if max_loop_depth == 0 and has_braceless_loop:
        max_loop_depth = 1

    return {
        "project_slug": project_slug,
        "asset_identifier": asset_identifier,
        "total_functions": total_functions,
        "max_loop_depth": max_loop_depth,
        "external_calls_count": external_calls_count,
        "state_mutations_count": state_mutations_count
    }

def persist_ast_metrics(project_slug: str, asset_identifier: str, metrics: dict, conn: sqlite3.Connection):
    """
    Persists extracted AST metrics to the database inside DB_LOCK context.
    """
    with DB_LOCK:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO ast_metrics (
                project_slug, asset_identifier, total_functions,
                max_loop_depth, external_calls_count, state_mutations_count, scanned_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                project_slug,
                asset_identifier,
                metrics.get("total_functions", 0),
                metrics.get("max_loop_depth", 0),
                metrics.get("external_calls_count", 0),
                metrics.get("state_mutations_count", 0)
            ))
