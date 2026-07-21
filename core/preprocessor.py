import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project workspace root to sys.path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from core.database import get_unified_connection, attach_vulnerabilities_db, DB_LOCK
from core.batch_enricher import _get_active_taxonomy_guide

LOGS_DIR = Path(__file__).parent.parent / "audit_logs"
QUEUE_DISTRIBUTION_FILE = LOGS_DIR / "queue_distribution.json"

# Initialize local tokenizer for offline token counting
TOKENIZER = None
TOKENIZER_TYPE = "fallback"

try:
    import tiktoken
    try:
        TOKENIZER = tiktoken.get_encoding("cl100k_base")
        TOKENIZER_TYPE = "tiktoken_cl100k"
    except Exception:
        TOKENIZER = tiktoken.get_encoding("gpt2")
        TOKENIZER_TYPE = "tiktoken_gpt2"
except ImportError:
    try:
        from transformers import AutoTokenizer
        TOKENIZER = AutoTokenizer.from_pretrained("gpt2")
        TOKENIZER_TYPE = "transformers_gpt2"
    except Exception:
        TOKENIZER = None
        TOKENIZER_TYPE = "character_ratio"

def count_tokens(text: str) -> int:
    """Counts tokens using available local tokenizer or character ratio fallback."""
    if not text:
        return 0
    if TOKENIZER and TOKENIZER_TYPE.startswith("tiktoken"):
        return len(TOKENIZER.encode(text))
    elif TOKENIZER and TOKENIZER_TYPE.startswith("transformers"):
        return len(TOKENIZER.encode(text, add_special_tokens=False))
    else:
        # Fallback estimation (~4 chars per token for English/code mix)
        return len(text) // 4

def get_static_system_prompt(taxonomy_guide: List[Dict[str, str]]) -> str:
    """Pre-formats the static system prompt using taxonomy guide for 100% identical prefix tokens."""
    default_path = taxonomy_guide[0]["path"] if taxonomy_guide else "smart_contract/reentrancy/read_only/view_desync"
    return (
        "You are an expert smart contract security auditor and AI trainer. "
        "Classify the input finding into our vulnerability taxonomy and extract rich structured metadata.\n"
        f"Valid active taxonomy guide: {json.dumps(taxonomy_guide)}\n"
        "IMPORTANT CONSTRAINTS:\n"
        "1. You MUST select a 'taxonomy_path' strictly present in the valid active taxonomy guide above.\n"
        "2. Keep 'thinking_process' concise (1-2 sentences) so output fits within token budget.\n"
        "3. The array fields ('attack_vector_steps', 'preconditions', 'affected_solidity_constructs') MUST ALWAYS be non-empty lists with at least 1 string element.\n\n"
        "Output ONLY a valid JSON object strictly matching this payload schema:\n"
        "{\n"
        '  "thinking_process": "<brief 1-2 sentence step-by-step reasoning about the finding>",\n'
        '  "taxonomy_slug": "view_desync",\n'
        f'  "taxonomy_path": "{default_path}",\n'
        '  "confidence_score": 0.95,\n'
        '  "vulnerability_summary": "<summary>",\n'
        '  "root_cause_explanation": "<root cause>",\n'
        '  "attack_vector_steps": ["step 1", "step 2"],\n'
        '  "preconditions": ["precondition 1"],\n'
        '  "impact_scope": "direct_theft_of_user_funds",\n'
        '  "affected_solidity_constructs": ["view_function", "external_call"],\n'
        '  "remediation_pattern": "<remediation>"\n'
        "}"
    )

def run_offline_queue_preprocessing() -> Dict[str, Any]:
    """
    Offline pre-processor measuring payload token lengths for all unprocessed findings in vuln.normalized_findings.
    Buckets datasets into context window tiers, sorts by sequence length to optimize vLLM continuous batching and APC,
    and exports an telemetry audit log to audit_logs/queue_distribution.json.
    ZERO HTTP requests sent to vLLM endpoint.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_unified_connection()
    attach_vulnerabilities_db(conn)
    cursor = conn.cursor()

    # 1. Fetch unprocessed finding IDs
    cursor.execute("""
    SELECT id, source_pool, protocol_name, source_repo, title, content_markdown, severity
    FROM vuln.normalized_findings
    WHERE id NOT IN (SELECT finding_id FROM vuln.enriched_findings_metadata)
    """)
    unprocessed_findings = [dict(r) for r in cursor.fetchall()]
    
    print(f"[+] Total unprocessed findings fetched: {len(unprocessed_findings)}")

    # 2. Pre-format static system prompt once for APC prefix optimization
    taxonomy_guide = _get_active_taxonomy_guide(conn)
    conn.close()

    static_system_prompt = get_static_system_prompt(taxonomy_guide)
    system_prompt_token_count = count_tokens(static_system_prompt)

    buckets: Dict[str, List[Dict[str, Any]]] = {
        "less_than_1k": [],
        "1k_to_2k": [],
        "2k_to_4k": [],
        "greater_than_4k": []
    }

    # 3. Process each finding: calculate token length & bucket
    ignored_stubs_count = 0
    STUB_PATTERNS = [
        "Duplicate of #"
    ]

    for idx, f in enumerate(unprocessed_findings):
        title = f.get("title", "Vulnerability Finding")
        content = f.get("content_markdown", "") or ""
        content_stripped = content.strip()

        # Pure empty / redirect noise filter criteria
        if len(content_stripped) < 50:
            ignored_stubs_count += 1
            continue

        content_lower = content_stripped.lower()
        if any(pattern.lower() in content_lower for pattern in STUB_PATTERNS):
            ignored_stubs_count += 1
            continue

        severity = f.get("severity", "high")

        user_prompt = f"Finding Title: {title}\nSeverity: {severity}\n\nContent:\n{content}"
        user_prompt_token_count = count_tokens(user_prompt)

        total_tokens = system_prompt_token_count + user_prompt_token_count

        item = {
            "id": f["id"],
            "source_pool": f.get("source_pool", "unknown"),
            "protocol_name": f.get("protocol_name") or f.get("source_repo") or "unknown",
            "title": title,
            "severity": severity,
            "system_prompt_tokens": system_prompt_token_count,
            "user_prompt_tokens": user_prompt_token_count,
            "total_tokens": total_tokens,
            "user_prompt": user_prompt,
            "content_snippet": content[:500]
        }

        # Context tier classification matching prompt_config
        if total_tokens < 1024:
            buckets["less_than_1k"].append(item)
        elif total_tokens < 2048:
            buckets["1k_to_2k"].append(item)
        elif total_tokens <= 4096:
            buckets["2k_to_4k"].append(item)
        else:
            buckets["greater_than_4k"].append(item)

    # 4. Sort sequences within each bucket descending by user prompt token count
    for bucket_name in buckets:
        buckets[bucket_name].sort(key=lambda x: x["user_prompt_tokens"], reverse=True)

    summary_counts = {tier: len(items) for tier, items in buckets.items()}
    total_staged = sum(summary_counts.values())

    report = {
        "timestamp": os.getenv("CURRENT_TIMESTAMP", ""),
        "total_unprocessed_findings": len(unprocessed_findings),
        "ignored_stubs_count": ignored_stubs_count,
        "total_staged": total_staged,
        "tokenizer_used": TOKENIZER_TYPE,
        "system_prompt_static_tokens": system_prompt_token_count,
        "summary_counts": summary_counts,
        "buckets": buckets
    }

    # 5. Export distribution report to audit_logs/queue_distribution.json
    with open(QUEUE_DISTRIBUTION_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"[+] Offline token pre-processing complete.")
    print(f"[+] Total unprocessed findings fetched: {len(unprocessed_findings)}")
    print(f"[+] Ignored low-quality stub entries: {ignored_stubs_count}")
    print(f"[+] Valid substantive findings staged: {total_staged}")
    print(f"[+] Tokenizer used: {TOKENIZER_TYPE}")
    print(f"[+] Bucket breakdown: {json.dumps(summary_counts, indent=2)}")
    print(f"[+] Exported telemetry log to: {QUEUE_DISTRIBUTION_FILE}")

    return {
        "status": "success",
        "total_unprocessed": len(unprocessed_findings),
        "ignored_stubs_count": ignored_stubs_count,
        "total_staged": total_staged,
        "summary_counts": summary_counts,
        "queue_distribution_file": str(QUEUE_DISTRIBUTION_FILE)
    }

if __name__ == "__main__":
    run_offline_queue_preprocessing()
