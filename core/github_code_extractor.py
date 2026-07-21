import os
import re
import sys
import json
import asyncio
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Ensure project workspace root is on sys.path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import httpx
from core.database import get_vulnerabilities_connection, DB_LOCK

def load_env() -> None:
    """Reads GITHUB_TOKEN and other vars from .env into os.environ if present."""
    env_path = WORKSPACE_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key not in os.environ:
                        os.environ[key] = val

def init_cache_table(conn: sqlite3.Connection) -> None:
    """Ensures the local github_file_cache table exists in vulnerabilities database."""
    with DB_LOCK:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS github_file_cache (
                cache_key TEXT PRIMARY KEY,
                file_content TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

# Regex GitHub Permalink Parsing
PERMALINK_REGEX = re.compile(
    r"https://github\.com/([^/]+)/([^/]+)/blob/([a-f0-9]+|[^/]+)/([^#\s]+)(?:#L(\d+)(?:-L(\d+))?)?",
    re.IGNORECASE
)

def parse_permalinks(content_markdown: str) -> List[Dict[str, Any]]:
    """
    Parses content_markdown for GitHub permalink URLs.
    Extracts owner, repo, commit_or_branch, file_path, start_line, end_line.
    """
    if not content_markdown or "github.com" not in content_markdown:
        return []

    matches = PERMALINK_REGEX.findall(content_markdown)
    results = []
    seen = set()

    for m in matches:
        owner, repo, commit_or_branch, file_path, start_str, end_str = m

        # Clean trailing markdown syntax, parentheses, or brackets from file_path
        file_path = file_path.rstrip(")]>\"';,.")
        if not file_path:
            continue

        start_line = int(start_str) if start_str else None
        end_line = int(end_str) if end_str else start_line

        cache_key = f"{owner}/{repo}/{commit_or_branch}/{file_path}"
        dedup_key = (cache_key, start_line, end_line)

        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        results.append({
            "owner": owner,
            "repo": repo,
            "commit_or_branch": commit_or_branch,
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "cache_key": cache_key
        })

    return results

async def fetch_github_file(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    owner: str,
    repo: str,
    commit_or_branch: str,
    file_path: str,
    github_token: Optional[str]
) -> Tuple[str, Optional[str]]:
    """
    Fetches raw file content from GitHub with concurrency limit and token authentication.
    Returns (cache_key, content_str_or_None).
    """
    cache_key = f"{owner}/{repo}/{commit_or_branch}/{file_path}"
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_or_branch}/{file_path}"

    headers = {"User-Agent": "ProfitBounty-Extractor"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    async with semaphore:
        try:
            resp = await client.get(raw_url, headers=headers, timeout=10.0, follow_redirects=True)
            if resp.status_code == 200:
                return (cache_key, resp.text)
            
            # Fallback to GitHub API endpoint if raw URL fails
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={commit_or_branch}"
            resp_api = await client.get(api_url, headers=headers, timeout=10.0, follow_redirects=True)
            if resp_api.status_code == 200:
                data = resp_api.json()
                if isinstance(data, dict) and "content" in data:
                    import base64
                    decoded = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
                    return (cache_key, decoded)

            return (cache_key, None)
        except Exception as e:
            return (cache_key, None)

def extract_lines(file_content: str, start_line: Optional[int], end_line: Optional[int]) -> str:
    """Extracts specified 1-indexed line range from file_content."""
    lines = file_content.splitlines()
    if not lines:
        return ""

    if start_line is None:
        # Default to first 200 lines if no range specified
        snippet_lines = lines[:200]
    else:
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line) if end_line else start_idx + 1
        if start_idx >= len(lines):
            snippet_lines = []
        else:
            snippet_lines = lines[start_idx:end_idx]

    return "\n".join(snippet_lines)

async def fetch_and_inline_github_code() -> Dict[str, Any]:
    """
    High-concurrency extractor that loads env credentials, parses permalinks,
    fetches contract code in parallel using SQLite cache, inlines Solidity code,
    and batch updates vuln.normalized_findings in 100-record transactions.
    """
    load_env()
    github_token = os.environ.get("GITHUB_TOKEN")
    print(f"[+] Loaded GITHUB_TOKEN: {'[PRESENT]' if github_token else '[MISSING/NONE]'}")

    conn = get_vulnerabilities_connection()
    init_cache_table(conn)

    # 1. Fetch all findings with github permalinks
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, content_markdown
        FROM normalized_findings
        WHERE content_markdown LIKE '%github.com%blob%'
    """)
    rows = cursor.fetchall()
    print(f"[+] Total findings matching github permalinks: {len(rows)}")

    # 2. Extract permalink metadata for all findings
    finding_permalinks: Dict[str, List[Dict[str, Any]]] = {}
    needed_cache_keys: set = set()
    cache_key_info: Dict[str, Tuple[str, str, str, str]] = {}

    for row in rows:
        fid = row["id"]
        content = row["content_markdown"] or ""
        parsed = parse_permalinks(content)
        if parsed:
            finding_permalinks[fid] = parsed
            for item in parsed:
                ckey = item["cache_key"]
                needed_cache_keys.add(ckey)
                cache_key_info[ckey] = (item["owner"], item["repo"], item["commit_or_branch"], item["file_path"])

    print(f"[+] Parsed {len(finding_permalinks)} findings referencing {len(needed_cache_keys)} unique files.")

    # 3. Load existing file cache from SQLite
    file_cache: Dict[str, str] = {}
    if needed_cache_keys:
        cursor.execute("SELECT cache_key, file_content FROM github_file_cache")
        for crow in cursor.fetchall():
            if crow["file_content"] is not None:
                file_cache[crow["cache_key"]] = crow["file_content"]

    print(f"[+] Cache hit for {len(file_cache)} files. {len(needed_cache_keys - set(file_cache.keys()))} files to download.")

    # 4. Fetch missing files in parallel with 100 concurrency slots
    missing_keys = [k for k in needed_cache_keys if k not in file_cache]
    if missing_keys:
        concurrency_slots = 100
        semaphore = asyncio.Semaphore(concurrency_slots)

        async with httpx.AsyncClient() as client:
            tasks = []
            for ckey in missing_keys:
                owner, repo, commit_or_branch, file_path = cache_key_info[ckey]
                tasks.append(
                    fetch_github_file(
                        client=client,
                        semaphore=semaphore,
                        owner=owner,
                        repo=repo,
                        commit_or_branch=commit_or_branch,
                        file_path=file_path,
                        github_token=github_token
                    )
                )

            print(f"[+] Launching {len(tasks)} async fetch tasks across {concurrency_slots} workers...")
            fetch_results = await asyncio.gather(*tasks)

            # Insert newly fetched files into github_file_cache table
            cache_inserts = []
            for ckey, content_str in fetch_results:
                if content_str is not None:
                    file_cache[ckey] = content_str
                    cache_inserts.append((ckey, content_str))

            if cache_inserts:
                with DB_LOCK:
                    with conn:
                        conn.executemany("""
                            INSERT OR REPLACE INTO github_file_cache (cache_key, file_content)
                            VALUES (?, ?)
                        """, cache_inserts)
                print(f"[+] Successfully cached {len(cache_inserts)} newly fetched files into github_file_cache.")

    # 5. Inline code snippets into content_markdown and prepare batch updates
    pending_updates: List[Tuple[str, str]] = []
    updated_findings_count = 0

    for row in rows:
        fid = row["id"]
        content_markdown = row["content_markdown"] or ""
        permalinks = finding_permalinks.get(fid, [])
        if not permalinks:
            continue

        snippets_to_append = []
        for p in permalinks:
            ckey = p["cache_key"]
            file_content = file_cache.get(ckey)
            if not file_content:
                continue

            start_line = p["start_line"]
            end_line = p["end_line"]
            file_path = p["file_path"]

            # Line reference formatting
            if start_line and end_line and start_line != end_line:
                line_ref = f"#L{start_line}-L{end_line}"
            elif start_line:
                line_ref = f"#L{start_line}"
            else:
                line_ref = ""

            header_marker = f"### Extracted Referenced Code Snippet ({file_path}{line_ref})"
            if header_marker in content_markdown:
                continue

            extracted_code = extract_lines(file_content, start_line, end_line)
            if not extracted_code.strip():
                continue

            lang = "solidity" if file_path.endswith(".sol") else ""
            snippet_block = (
                f"\n\n### Extracted Referenced Code Snippet ({file_path}{line_ref}):\n"
                f"```{lang}\n"
                f"{extracted_code}\n"
                f"```"
            )
            snippets_to_append.append(snippet_block)

        if snippets_to_append:
            new_content = content_markdown + "".join(snippets_to_append)
            pending_updates.append((new_content, fid))

    # 6. Batch update database in 100-record transactions under DB_LOCK
    print(f"[+] Prepared {len(pending_updates)} findings for inlined database updates.")
    batch_size = 100
    for i in range(0, len(pending_updates), batch_size):
        batch = pending_updates[i:i + batch_size]
        with DB_LOCK:
            with conn:
                conn.executemany("""
                    UPDATE normalized_findings
                    SET content_markdown = ?
                    WHERE id = ?
                """, batch)
        updated_findings_count += len(batch)

    conn.close()

    summary = {
        "status": "success",
        "total_permalinks_matched": len(rows),
        "total_unique_files_needed": len(needed_cache_keys),
        "total_files_cached": len(file_cache),
        "total_findings_updated": updated_findings_count
    }

    print(f"[+] GitHub Code Extractor completed successfully:")
    print(f"    - Findings matched: {summary['total_permalinks_matched']}")
    print(f"    - Unique files cached: {summary['total_files_cached']}")
    print(f"    - Findings updated: {summary['total_findings_updated']}")

    return summary

if __name__ == "__main__":
    asyncio.run(fetch_and_inline_github_code())
