import asyncio
import re
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Any

from core.database import get_vulnerabilities_connection, init_vulnerabilities_db, DB_LOCK

SECURITY_PATCH_PATTERN = r"(?i)(fix|bug|vuln|security|exploit|bypass|leak|overflow|reentrancy|attack|patch)"
TARGET_EXTENSIONS = (".sol", ".vy", ".rs")

ALLOWED_TAXONOMY_ENUMS = {
    'reentrancy',
    'access_control',
    'overflow_underflow',
    'oracle_manipulation',
    'arbitrary_external_call',
    'signature_malleability',
    'logic_defect'
}

def sanitize_tag(raw_tag: str) -> str:
    """
    Post-processing sanitizer: lowercases, strips whitespace, replaces dashes/spaces with underscores,
    and validates against the allowed taxonomy enums.
    """
    if not raw_tag:
        return 'logic_defect'
    
    cleaned = raw_tag.strip().lower()
    cleaned = re.sub(r'[\s\-]+', '_', cleaned)
    # Remove non-alphanumeric chars except underscore
    cleaned = re.sub(r'[^a-z0-9_]', '', cleaned)
    
    if cleaned in ALLOWED_TAXONOMY_ENUMS:
        return cleaned
    
    # Keyword fallback matching if non-exact match string was returned
    for tag in ALLOWED_TAXONOMY_ENUMS:
        if tag in cleaned:
            return tag
            
    return 'logic_defect'

def classify_tag_heuristic(commit_msg: str, diff_text: str) -> str:
    """Deterministic local fallback classifier when LLM cluster is unavailable."""
    combined = (commit_msg + "\n" + diff_text).lower()
    if "reentran" in combined:
        return "reentrancy"
    elif any(k in combined for k in ["access", "onlyowner", "role", "auth", "permission", "privilege"]):
        return "access_control"
    elif any(k in combined for k in ["overflow", "underflow", "safemath", "math"]):
        return "overflow_underflow"
    elif any(k in combined for k in ["oracle", "twap", "spot_price", "price_manipulation"]):
        return "oracle_manipulation"
    elif any(k in combined for k in ["delegatecall", "arbitrary_call", "raw_call", "external_call"]):
        return "arbitrary_external_call"
    elif any(k in combined for k in ["signature", "ecrecover", "s_value", "malleab"]):
        return "signature_malleability"
    else:
        return "logic_defect"

async def classify_with_llm(raw_diff_text: str, commit_msg: str) -> str:
    """
    Sends contract diff and commit details to Qwen 27B LLM cluster instance.
    Falls back gracefully to deterministic heuristic on timeout or network drop.
    """
    url = "http://192.168.1.57:8000/v1/chat/completions"
    prompt_payload = {
        "model": "Qwen/Qwen2.5-27B-Instruct",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a smart contract security analysis classifier. "
                    "Analyze the given git diff and commit message, then output a JSON object specifying "
                    "the single exact technical root cause tag from this enum list: "
                    "['reentrancy', 'access_control', 'overflow_underflow', 'oracle_manipulation', "
                    "'arbitrary_external_call', 'signature_malleability', 'logic_defect']. "
                    "Format: {\"tag\": \"<ENUM_VALUE>\"}"
                )
            },
            {
                "role": "user",
                "content": f"Commit Message: {commit_msg}\n\nDiff Payload:\n{raw_diff_text[:3000]}"
            }
        ],
        "temperature": 0.1
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(prompt_payload).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        loop = asyncio.get_event_loop()
        def _make_req():
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                if resp.status == 200:
                    res_body = json.loads(resp.read().decode('utf-8'))
                    content = res_body['choices'][0]['message']['content']
                    match = re.search(r'\{\s*"tag"\s*:\s*"([^"]+)"\s*\}', content)
                    if match:
                        return match.group(1)
                    return content
                return None
                
        raw_res = await loop.run_in_executor(None, _make_req)
        if raw_res:
            return sanitize_tag(raw_res)
    except Exception:
        # LLM cluster unreachable or timed out - use local fallback classifier
        pass

    return sanitize_tag(classify_tag_heuristic(commit_msg, raw_diff_text))

async def mine_repository_security_history(repo_path: str, protocol_name: str) -> int:
    """
    Recursively scans target git repository log history for security fix commits,
    extracts contract diffs, classifies vulnerability taxonomy, and persists findings to vulnerabilities.db.
    """
    init_vulnerabilities_db()
    repo_dir = Path(repo_path).resolve()
    if not repo_dir.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

    # 1. Execute git log via non-blocking async subprocess pool
    cmd = ["git", "log", "--pretty=format:%H|%ai|%s", "--name-only", "--reverse"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(repo_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_msg = stderr.decode('utf-8', errors='replace')
        raise RuntimeError(f"Git log execution failed: {err_msg}")

    log_output = stdout.decode('utf-8', errors='replace')
    if not log_output.strip():
        return 0

    matching_commits = []
    security_regex = re.compile(SECURITY_PATCH_PATTERN)

    current_commit = None
    for line in log_output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line and len(line.split("|")[0]) == 40:
            parts = line.split("|", 2)
            commit_hash = parts[0]
            timestamp = parts[1]
            subject = parts[2] if len(parts) > 2 else ""
            
            if security_regex.search(subject):
                current_commit = {
                    "commit_hash": commit_hash,
                    "author_timestamp": timestamp,
                    "commit_msg": subject,
                    "files": []
                }
                matching_commits.append(current_commit)
            else:
                current_commit = None
        elif current_commit:
            if any(line.endswith(ext) for ext in TARGET_EXTENSIONS):
                current_commit["files"].append(line)

    inserted_count = 0

    # 2. For each matched security commit, fetch diff safely with deadlock prevention
    for commit in matching_commits:
        chash = commit["commit_hash"]
        
        show_proc = await asyncio.create_subprocess_exec(
            "git", "show", chash,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Deadlock prevention: Drains system stdout/stderr buffers completely
        show_stdout, _ = await show_proc.communicate()
        raw_diff_text = show_stdout.decode('utf-8', errors='replace')

        modified_contracts = [f for f in commit["files"] if any(f.endswith(ext) for ext in TARGET_EXTENSIONS)]
        
        if not modified_contracts:
            for ext in TARGET_EXTENSIONS:
                matches = re.findall(rf"--- a/(\S+{re.escape(ext)})", raw_diff_text)
                matches += re.findall(rf"\+\+\+ b/(\S+{re.escape(ext)})", raw_diff_text)
                modified_contracts.extend(matches)
            modified_contracts = list(set(modified_contracts))

        if not modified_contracts:
            continue

        # 3. Dynamic Taxonomy Classification
        classified_tag = await classify_with_llm(raw_diff_text, commit["commit_msg"])

        # 4. Thread-safe Transaction Write Pass to vulnerabilities.db
        finding_id = f"git_{protocol_name}_{chash[:12]}"
        impacted_files_json = json.dumps(modified_contracts)

        with DB_LOCK:
            conn = get_vulnerabilities_connection()
            cursor = conn.cursor()
            with conn:
                cursor.execute("""
                INSERT OR REPLACE INTO normalized_findings (
                    id, source_pool, protocol_name, title, content_markdown,
                    severity, fix_commit, file_paths
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    finding_id,
                    protocol_name,
                    protocol_name,
                    commit["commit_msg"],
                    raw_diff_text,
                    "high",
                    chash,
                    impacted_files_json
                ))

                cursor.execute("""
                INSERT OR REPLACE INTO vulnerability_tags_index (
                    finding_id, source_pool, tag
                ) VALUES (?, ?, ?)
                """, (
                    finding_id,
                    protocol_name,
                    classified_tag
                ))
            conn.close()

        inserted_count += 1

    return inserted_count
