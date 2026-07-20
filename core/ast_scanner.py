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

import os
from pathlib import Path

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

def run_global_asset_ast_scan(conn: sqlite3.Connection, cache_dir: str = "vulnerability_repos/solidity_cache") -> int:
    """
    Orchestrates global source code harvesting and AST metrics parsing for contract assets.
    Queries unified assets table for solidity/smart_contract types, matches cached source files,
    runs the AST scanner, and persists metrics into ast_metrics.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT project_slug, asset_identifier, url, description 
        FROM assets 
        WHERE LOWER(type) IN ('solidity', 'smart_contract', 'contract')
    """)
    asset_rows = cursor.fetchall()

    cache_path = Path(cache_dir)
    processed_count = 0

    if not cache_path.exists():
        return 0

    for row in asset_rows:
        project_slug = row["project_slug"]
        asset_identifier = row["asset_identifier"] or ""
        description = row["description"] or ""

        # Candidates to look for on disk
        candidates = []
        if asset_identifier:
            # e.g., Pool.sol or path/Pool.sol -> Pool.sol, Pool
            clean_ident = Path(asset_identifier).name
            candidates.append(clean_ident)
            candidates.append(asset_identifier)

        if description:
            clean_desc = Path(description).name
            candidates.append(clean_desc)
            candidates.append(description)

        target_file = None
        for candidate in candidates:
            if not candidate:
                continue
            # Try direct file inside cache_dir
            candidate_path = cache_path / candidate
            if candidate_path.is_file():
                target_file = candidate_path
                break
            
            # Try recursive search if candidate matches filename
            matched_files = list(cache_path.glob(f"**/{candidate}"))
            if matched_files and matched_files[0].is_file():
                target_file = matched_files[0]
                break

        if target_file and target_file.is_file():
            try:
                source_code = target_file.read_text(encoding="utf-8", errors="ignore")
                metrics = scan_solidity_source_metrics(project_slug, asset_identifier, source_code)
                persist_ast_metrics(project_slug, asset_identifier, metrics, conn)
                processed_count += 1
            except Exception as e:
                print(f"[!] Error processing asset {asset_identifier} from {target_file}: {e}")

    return processed_count

