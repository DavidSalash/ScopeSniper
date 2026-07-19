#!/usr/bin/env python3
"""
Extractor for Bug Bounty & Security Audit Databases (ibb, sbb, cbb, hbb).

This script extracts 'x' number of the smallest (non-outlier) project examples
from each SQLite database, demonstrating the main field structure and table relationships
for projects across all platforms.
"""

import os
import sys
import glob
import json
import sqlite3
import argparse
from typing import Dict, List, Any, Tuple

# Default databases routed dynamically:
if os.path.exists("/app"):
    DB_DIR = "/app/data_store"
else:
    DB_DIR = "C:/users/david"

DEFAULT_DBS = [
    f"{DB_DIR}/cbb.db",
    f"{DB_DIR}/hbb.db",
    f"{DB_DIR}/ibb.db",
    f"{DB_DIR}/sbb.db"
]

def get_database_schema(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, str]]]:
    """Retrieves tables and column information for a database."""
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
    tables = [r['name'] for r in cursor.fetchall()]
    
    schema = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()
        schema[table] = [{'name': c['name'], 'type': c['type'], 'notnull': c['notnull'], 'pk': c['pk']} for c in cols]
    return schema

def fetch_project_full_data(conn: sqlite3.Connection, slug: str) -> Dict[str, Any]:
    """Fetches a project record and all related child table rows by project_slug."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE slug = ?", (slug,))
    p_row = cursor.fetchone()
    if not p_row:
        return {}
    
    project = dict(p_row)
    
    # Fetch child tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name not in ('projects', 'sqlite_sequence')")
    child_tables = [r[0] for r in cursor.fetchall()]
    
    children = {}
    for table in child_tables:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [c[1] for c in cursor.fetchall()]
        if 'project_slug' in cols:
            cursor.execute(f"SELECT * FROM {table} WHERE project_slug = ?", (slug,))
            rows = [dict(r) for r in cursor.fetchall()]
            children[table] = rows
            
    project['children'] = children
    return project

def compute_project_size(project_data: Dict[str, Any]) -> int:
    """Computes total data size in bytes for a project record including child tables."""
    return len(json.dumps(project_data, default=str))

def is_non_outlier_valid(project_data: Dict[str, Any], min_bytes: int = 5000) -> bool:
    """
    Filters out extreme small outliers (broken/empty placeholder stubs).
    A valid project must:
    1. Have a non-empty name/slug.
    2. Have total data size >= min_bytes OR have at least 1 asset/reward/description.
    """
    slug = project_data.get('slug')
    proj_name = project_data.get('project') or slug
    
    if not slug or not proj_name or str(proj_name).strip() == '':
        return False
        
    children = project_data.get('children', {})
    has_assets = len(children.get('assets', [])) > 0
    has_rewards = len(children.get('rewards', [])) > 0
    
    desc = (project_data.get('description') or 
            project_data.get('program_overview') or 
            project_data.get('main_content') or '')
    has_desc = len(str(desc).strip()) >= 50
    
    data_size = compute_project_size(project_data)
    
    # Must meet size cutoff OR have structural content (assets/rewards/desc)
    if data_size < min_bytes and not (has_assets or has_rewards or has_desc):
        return False
        
    return True

def extract_examples(db_path: str, num_examples: int = 3, min_bytes: int = 5000) -> Dict[str, Any]:
    """
    Extracts schema overview and the top 'num_examples' smallest non-outlier projects from a database.
    """
    if not os.path.exists(db_path):
        return {'error': f"Database file '{db_path}' not found."}
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get schema
    schema = get_database_schema(conn)
    
    # Fetch all project slugs
    cursor.execute("SELECT slug FROM projects")
    slug_rows = cursor.fetchall()
    slugs = [r['slug'] for r in slug_rows]
    
    projects_evaluated = []
    for slug in slugs:
        p_data = fetch_project_full_data(conn, slug)
        if not p_data:
            continue
        size = compute_project_size(p_data)
        valid = is_non_outlier_valid(p_data, min_bytes=min_bytes)
        projects_evaluated.append({
            'slug': slug,
            'size_bytes': size,
            'is_valid': valid,
            'data': p_data
        })
        
    conn.close()
    
    # Sort by size ascending
    projects_evaluated.sort(key=lambda x: x['size_bytes'])
    
    # Filter non-outliers
    valid_projects = [p for p in projects_evaluated if p['is_valid']]
    outliers_filtered = [p for p in projects_evaluated if not p['is_valid']]
    
    # Select smallest x valid projects
    selected = valid_projects[:num_examples]
    
    return {
        'database': os.path.basename(db_path),
        'total_projects': len(slugs),
        'valid_projects_count': len(valid_projects),
        'outliers_count': len(outliers_filtered),
        'schema': schema,
        'examples': [
            {
                'slug': p['slug'],
                'size_bytes': p['size_bytes'],
                'project_name': p['data'].get('project') or p['slug'],
                'structure': p['data']
            }
            for p in selected
        ]
    }

def is_html_or_json(key: str, val: Any) -> bool:
    """Determines if a field value represents long HTML or JSON content."""
    if not isinstance(val, str):
        return False
    key_lower = key.lower()
    if 'html' in key_lower or 'json' in key_lower or key_lower in ('main_content', 'raw_json'):
        return True
    val_trimmed = val.strip()
    if val_trimmed.startswith('{') or val_trimmed.startswith('['):
        try:
            json.loads(val_trimmed)
            return True
        except Exception:
            pass
    if val_trimmed.startswith('<') and ('>' in val_trimmed or val_trimmed.endswith('>')):
        return True
    return False

def format_field_value(key: str, val: Any, max_code_len: int = 150) -> Any:
    """
    Formats a field value:
    - Long HTML or JSON content is truncated to prevent clutter.
    - Raw text fields (e.g., description, rules, program overview) are NOT truncated.
    """
    if not isinstance(val, str):
        return val
        
    if is_html_or_json(key, val):
        if max_code_len > 0 and len(val) > max_code_len:
            return val[:max_code_len] + f"... [truncated HTML/JSON ({len(val)} chars)]"
            
    return val

def format_console_output(results: Dict[str, Any], max_code_len: int = 150) -> str:
    """Formats extraction results into a human-readable CLI report."""
    lines = []
    lines.append("=" * 80)
    lines.append(f" DATABASE FIELD STRUCTURE & EXAMPLES REPORT")
    lines.append("=" * 80)
    
    for db_name, res in results.items():
        if 'error' in res:
            lines.append(f"\n[!] Database: {db_name} - ERROR: {res['error']}")
            continue
            
        lines.append(f"\n" + "#" * 80)
        lines.append(f" DATABASE: {res['database']}")
        lines.append(f" Total Projects: {res['total_projects']} | Valid Non-Outliers: {res['valid_projects_count']} | Filtered Outliers: {res['outliers_count']}")
        lines.append("#" * 80)
        
        # Schema Summary
        lines.append("\n--- TABLE SCHEMAS ---")
        for tbl, cols in res['schema'].items():
            col_names = [c['name'] for c in cols]
            lines.append(f"  Table '{tbl}' ({len(cols)} columns): {', '.join(col_names)}")
            
        # Example Projects
        lines.append(f"\n--- SMALLEST NON-OUTLIER EXAMPLES (x = {len(res['examples'])}) ---")
        for idx, ex in enumerate(res['examples'], 1):
            slug = ex['slug']
            name = ex['project_name']
            size = ex['size_bytes']
            p_struct = ex['structure']
            
            lines.append(f"\n  [{idx}] Project: '{name}' (slug: {slug}) - Size: {size:,} bytes")
            lines.append("  " + "-" * 60)
            lines.append("  Main Fields ('projects' table):")
            
            for k, v in p_struct.items():
                if k == 'children':
                    continue
                if v is not None and str(v).strip() != '':
                    disp_v = format_field_value(k, v, max_code_len)
                    lines.append(f"    - {k}: {disp_v}")
                else:
                    lines.append(f"    - {k}: None")
                    
            lines.append("\n  Child Tables & Related Records:")
            children = p_struct.get('children', {})
            for child_tbl, child_rows in children.items():
                lines.append(f"    - Table '{child_tbl}': {len(child_rows)} record(s)")
                for r_idx, row in enumerate(child_rows[:2], 1): # Show up to 2 records per child table
                    formatted_row = {k: format_field_value(k, v, max_code_len) for k, v in row.items()}
                    lines.append(f"        Record #{r_idx}: {formatted_row}")
                if len(child_rows) > 2:
                    lines.append(f"        ... ({len(child_rows) - 2} more record(s) omitted)")
                    
    return "\n".join(lines)

def format_markdown_output(results: Dict[str, Any], max_code_len: int = 150) -> str:
    """Formats extraction results into Markdown format."""
    lines = []
    lines.append("# Database Field Structure & Smallest Non-Outlier Examples\n")
    lines.append("This document shows the field structure and example records for the smallest non-outlier projects across each database.\n")
    
    for db_name, res in results.items():
        if 'error' in res:
            lines.append(f"## Database: {db_name}\n**Error**: {res['error']}\n")
            continue
            
        lines.append(f"## Database: `{res['database']}`\n")
        lines.append(f"- **Total Projects**: {res['total_projects']}")
        lines.append(f"- **Valid Non-Outliers**: {res['valid_projects_count']}")
        lines.append(f"- **Filtered Outliers**: {res['outliers_count']}\n")
        
        lines.append("### Table Schemas\n")
        lines.append("| Table Name | Column Count | Columns |")
        lines.append("| --- | --- | --- |")
        for tbl, cols in res['schema'].items():
            col_names = ", ".join([f"`{c['name']}`" for c in cols])
            lines.append(f"| `{tbl}` | {len(cols)} | {col_names} |")
        lines.append("")
        
        lines.append(f"### Smallest Non-Outlier Projects (x = {len(res['examples'])})\n")
        for idx, ex in enumerate(res['examples'], 1):
            slug = ex['slug']
            name = ex['project_name']
            size = ex['size_bytes']
            p_struct = ex['structure']
            
            lines.append(f"#### Example {idx}: {name} (`{slug}`)\n")
            lines.append(f"- **Data Size**: {size:,} bytes")
            lines.append("\n**Projects Table Structure & Values:**\n")
            lines.append("| Field Name | Value |")
            lines.append("| --- | --- |")
            for k, v in p_struct.items():
                if k == 'children':
                    continue
                val_str = "*(null)*" if v is None or str(v).strip() == '' else str(format_field_value(k, v, max_code_len)).replace("\n", "<br>")
                lines.append(f"| `{k}` | {val_str} |")
            lines.append("")
            
            lines.append("**Child Tables Summary & Sample Records:**\n")
            children = p_struct.get('children', {})
            for child_tbl, child_rows in children.items():
                lines.append(f"- **`{child_tbl}`**: {len(child_rows)} record(s)")
                if child_rows:
                    sample = child_rows[0]
                    sample_fmt = {k: format_field_value(k, v, max_code_len) for k, v in sample.items()}
                    lines.append(f"  - *Sample Record 1*: `{sample_fmt}`")
            lines.append("\n---\n")
            
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(
        description="Extract smallest non-outlier project examples from databases showing field structures."
    )
    parser.add_argument(
        '-n', '--num-examples', type=int, default=3,
        help="Number of smallest non-outlier project examples to extract per database (default: 3)."
    )
    parser.add_argument(
        '--dbs', nargs='+', default=DEFAULT_DBS,
        help=f"Database files to include (default: {' '.join(DEFAULT_DBS)})."
    )
    parser.add_argument(
        '-f', '--format', choices=['text', 'json', 'markdown'], default='text',
        help="Output format: text, json, or markdown (default: text)."
    )
    parser.add_argument(
        '-o', '--output', type=str, default=None,
        help="Optional output filepath to save extracted report."
    )
    parser.add_argument(
        '--min-bytes', type=int, default=5000,
        help="Minimum data size in bytes to filter out empty placeholder outlier stubs (default: 5000)."
    )
    parser.add_argument(
        '--max-code-len', type=int, default=150,
        help="Maximum characters to show per HTML/JSON field (0 for full content). Raw text fields are never truncated. (default: 150)."
    )

    args = parser.parse_args()
    
    # Resolve database paths: support direct paths, simple names (e.g., 'cbb'), or filenames ('cbb.db')
    resolved_dbs = []
    for db in args.dbs:
        if os.path.exists(db):
            resolved_dbs.append(db)
        else:
            base_name = db
            if not base_name.endswith('.db'):
                base_name += '.db'
            possible_path = os.path.join(DB_DIR, base_name)
            if os.path.exists(possible_path):
                resolved_dbs.append(possible_path)
            else:
                resolved_dbs.append(db)  # Fallback so extract_examples reports "file not found"

    all_results = {}
    for db_path in resolved_dbs:
        res = extract_examples(db_path, num_examples=args.num_examples, min_bytes=args.min_bytes)
        all_results[os.path.basename(db_path)] = res
        
    if args.format == 'json':
        output_str = json.dumps(all_results, indent=2, default=str)
    elif args.format == 'markdown':
        output_str = format_markdown_output(all_results, max_code_len=args.max_code_len)
    else:
        output_str = format_console_output(all_results, max_code_len=args.max_code_len)
        
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_str)
        print(f"Extraction complete! Report saved to '{args.output}'.")
    else:
        print(output_str)

if __name__ == '__main__':
    main()
