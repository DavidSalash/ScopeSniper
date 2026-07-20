import re
import sqlite3
from typing import Dict, Any
from core.database import DB_LOCK

def strip_comments_and_strings(code: str) -> str:
    """
    Strips single-line // comments, multi-line /* */ comments,
    and string literals ("..." and '...') from Solidity code.
    Replaces string/comment characters with spaces to preserve line lengths.
    """
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ' ' * len(s)
        else:
            return ' ' * len(s)

    pattern = r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"'
    return re.sub(pattern, replacer, code, flags=re.DOTALL | re.MULTILINE)

def scan_solidity_source_metrics(project_slug: str, asset_identifier: str, source_code: str) -> Dict[str, Any]:
    """
    Scans a raw Solidity source code string to compute key structural metrics:
    - total_functions
    - max_loop_depth
    - external_calls_count
    - state_mutations_count
    """
    clean_code = strip_comments_and_strings(source_code)

    # 1. total_functions: Match function declarations via r"\bfunction\s+(\w+)" or function keyword
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
    # Handle exclude logic cleanly by regex matching comparison operators first or filtering
    mutation_pattern = r"(?:==|>=|<=|!=|=>)|(\+\+|--|\+=|-=|\*=|/=|%=|\|=|&=|\^=|=)"
    mutations_count = 0
    for match in re.finditer(mutation_pattern, clean_code):
        if match.group(1):  # Group 1 matched the mutation operator, not comparison
            mutations_count += 1
    state_mutations_count = mutations_count

    # 4. max_loop_depth: Trace loop patterns and brace depth
    # Loop pattern matches for(...) or while(...) followed by { or opening brace
    # We walk the tokenized/character structure of clean_code
    max_loop_depth = 0
    current_brace_depth = 0
    active_loop_stack = []  # Stack storing the brace depth at which each active loop started

    # We can scan character by character to accurately trace brace weights
    i = 0
    length = len(clean_code)
    
    # Pre-identify loop locations
    loop_regex = re.compile(r"\b(for|while)\b\s*\([^()]*+(?:\([^()]*+\)[^()]*+)*+\)\s*\{|\b(for|while)\b\s*\(")
    
    # Standard character iteration to track braces and loop starts
    # To handle loops with or without braces, or braces on next lines:
    lines = clean_code.split('\n')
    
    # Alternative robust scanner using regex + character scanning:
    # Walk character by character
    i = 0
    active_loops = []  # list of depth integers where loop brace opened
    
    while i < length:
        ch = clean_code[i]
        
        # Check if a loop starts at index i
        # Match loop pattern: \b(for|while)\b
        match_loop = re.match(r"\b(for|while)\b", clean_code[i:])
        if match_loop:
            # Look ahead for opening brace '{'
            brace_pos = clean_code.find('{', i + match_loop.end())
            # Ensure no function or contract keyword comes between loop and '{'
            intervening = clean_code[i + match_loop.end():brace_pos] if brace_pos != -1 else ""
            if brace_pos != -1 and not re.search(r"\b(function|contract|struct|enum|event)\b", intervening):
                # When '{' of this loop is reached, it will open at current_brace_depth + 1
                # Mark this pending loop opening brace position
                pending_loop_brace = brace_pos
            else:
                pending_loop_brace = -1
        else:
            pending_loop_brace = -1

        if ch == '{':
            current_brace_depth += 1
            # Check if this brace belongs to a loop start
            # Check if there was a for/while shortly preceding this '{'
            lookback = clean_code[max(0, i - 200):i]
            if re.search(r"\b(for|while)\b\s*\(.*?\)\s*$", lookback, re.DOTALL):
                active_loops.append(current_brace_depth)
                if len(active_loops) > max_loop_depth:
                    max_loop_depth = len(active_loops)
        elif ch == '}':
            if active_loops and active_loops[-1] == current_brace_depth:
                active_loops.pop()
            current_brace_depth = max(0, current_brace_depth - 1)
            
        i += 1

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
