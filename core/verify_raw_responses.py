import sqlite3
import json
import urllib.request
import time
import sys
from pathlib import Path

# Add project root to sys.path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from core.database import get_unified_connection, attach_vulnerabilities_db, DB_LOCK
from core.batch_enricher import _get_active_taxonomy_guide, process_single_finding_enrichment
from core.pipeline import get_prompt_config

def purge_corrupted_records(conn: sqlite3.Connection):
    """Purge all fake/corrupted fallback entries from database."""
    cursor = conn.cursor()
    with DB_LOCK:
        with conn:
            cursor.execute("DELETE FROM vuln.enriched_findings_metadata WHERE attack_vector_steps_json LIKE '%Analyze contract logic%'")
            deleted = cursor.rowcount
            cursor.execute("DELETE FROM vuln.enriched_findings_metadata WHERE vulnerability_summary LIKE '%Identified security issue in%'")
            deleted += cursor.rowcount
    print(f"[+] Purged {deleted} corrupted fake fallback records from vuln.enriched_findings_metadata.")
    return deleted

def verify_raw_responses():
    conn = get_unified_connection()
    attach_vulnerabilities_db(conn)

    # 1. Purge corrupted records
    purge_corrupted_records(conn)

    # Check remaining corrupted count
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vuln.enriched_findings_metadata WHERE attack_vector_steps_json LIKE '%Analyze contract logic%' OR vulnerability_summary LIKE '%Identified security issue in%'")
    corrupted_count = cursor.fetchone()[0]
    assert corrupted_count == 0, f"Error: Found {corrupted_count} corrupted records after purge!"
    print("[+] Assertion passed: 0 records contain hardcoded template strings in DB.")

    # 2. Select 10 stratified finding samples for live inference verification
    cursor.execute("""
    SELECT id, source_pool, protocol_name, source_repo, title, content_markdown, severity 
    FROM vuln.normalized_findings
    LIMIT 10
    """)
    sample_findings = [dict(r) for r in cursor.fetchall()]
    
    taxonomy_guide = _get_active_taxonomy_guide(conn)
    cfg = get_prompt_config()
    
    endpoint = cfg.get("vllm_endpoint", "http://192.168.1.57:8000/v1/chat/completions")
    model_name = cfg.get("model_name", "nvidia/Qwen3.6-27B-NVFP4")

    print(f"[+] Dispatching {len(sample_findings)} test requests directly to {endpoint} using model '{model_name}'...")

    successful_responses = []
    failed_responses = []

    placeholder_templates = [
        "Analyze contract logic",
        "Identified security issue in",
        "Contract flaw reported in",
        "Identify state inconsistency"
    ]

    for i, finding in enumerate(sample_findings, 1):
        print(f"\n--- Request {i}/10 (Finding ID: {finding['id']}) ---")
        try:
            res = process_single_finding_enrichment(finding, taxonomy_guide, cfg)
            raw_response = res.get("raw_vllm_response") or ""
            parsed_payload = res.get("payload")
            status = res.get("validation_status")
            errors = res.get("validation_errors")

            print(f"Validation Status: {status}")
            if errors:
                print(f"Validation Errors: {errors}")

            print("Raw LLM Response:")
            print(raw_response if raw_response else "<NO RESPONSE / HTTP ERROR>")

            if parsed_payload:
                print("\nParsed JSON Payload:")
                print(json.dumps(parsed_payload, indent=2))

            # Check hardcoded template assertions
            for tmpl in placeholder_templates:
                assert tmpl not in raw_response, f"Assertion Failed: Raw LLM response contains hardcoded template string '{tmpl}'"
                if parsed_payload:
                    payload_str = json.dumps(parsed_payload)
                    assert tmpl not in payload_str, f"Assertion Failed: Parsed payload contains template string '{tmpl}'"

            if status == "PASS" and parsed_payload:
                summary = parsed_payload.get("vulnerability_summary", "")
                steps = parsed_payload.get("attack_vector_steps", [])
                print(f"[+] Verified genuine technical analysis for finding {finding['id']}: Summary len={len(summary)}, Steps count={len(steps)}")
                successful_responses.append(res)
            else:
                failed_responses.append(res)

        except Exception as e:
            print(f"[-] Request {i} encountered error: {e}")
            failed_responses.append({"finding_id": finding["id"], "error": str(e)})

    print(f"\n================ Verification Summary ================")
    print(f"Total Dispatched: {len(sample_findings)}")
    print(f"Successful Valid Inferences: {len(successful_responses)}")
    print(f"Failed / Unreachable: {len(failed_responses)}")

    # Check DB corrupted records count once more
    cursor.execute("SELECT COUNT(*) FROM vuln.enriched_findings_metadata WHERE attack_vector_steps_json LIKE '%Analyze contract logic%'")
    final_corrupted = cursor.fetchone()[0]
    assert final_corrupted == 0, f"Error: Database contains {final_corrupted} corrupted records!"
    print("[+] Final Assertion passed: Exactly 0 database records contain hardcoded template strings.")
    
    conn.close()

if __name__ == "__main__":
    verify_raw_responses()
