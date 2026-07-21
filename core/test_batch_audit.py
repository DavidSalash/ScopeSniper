import asyncio
import json
import os
import sys
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_unified_connection, attach_vulnerabilities_db
from core.pipeline import get_prompt_config
from core.batch_enricher import (
    _get_stratified_samples,
    _get_active_taxonomy_guide,
    _get_active_taxonomy_paths,
    process_single_finding_enrichment,
)

import urllib.request

def _check_vllm_reachability(models_url: str = "http://192.168.1.57:8000/v1/models", timeout: float = 5.0) -> bool:
    try:
        req = urllib.request.Request(models_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False

async def run_audit_batch_and_export(
    output_filepath: str = "audit_logs/test_batch_inspection.json",
    sample_limit: Optional[int] = 32
) -> Dict[str, Any]:
    """
    Executes stratified audit batch across vulnerability database reports,
    captures exact prompt payloads and raw vLLM outputs, exports audit ledger to disk,
    and programmatically verifies schema fidelity.
    """
    if not _check_vllm_reachability():
        print("CRITICAL: Cannot connect to vLLM server at http://192.168.1.57:8000.")
        sys.exit(1)

    conn = get_unified_connection()
    attach_vulnerabilities_db(conn)

    samples = _get_stratified_samples(conn, sample_limit=sample_limit)
    taxonomy_guide = _get_active_taxonomy_guide(conn)
    valid_paths_set = set(_get_active_taxonomy_paths(conn))
    cfg = get_prompt_config()
    concurrency_slots = int(cfg.get("concurrency_slots", 16))

    print(f"[+] Starting stratified audit batch. Total sampled reports: {len(samples)}")
    print(f"[+] Loaded active taxonomy guide entries: {len(taxonomy_guide)}")

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_slots) as executor:
        futures = [
            loop.run_in_executor(executor, process_single_finding_enrichment, finding, taxonomy_guide, cfg)
            for finding in samples
        ]
        results = await asyncio.gather(*futures)

    # Format audit ledger records
    audit_entries = []
    for r in results:
        entry = {
            "finding_id": r["finding_id"],
            "source_pool": r["source_pool"],
            "protocol_name": r.get("protocol_name", "unknown"),
            "raw_input_prompt": r["raw_input_prompt"],
            "raw_vllm_response": r["raw_vllm_response"],
            "parsed_json_output": r["parsed_json_output"],
            "validation_status": r["validation_status"],
            "validation_errors": r["validation_errors"],
        }
        audit_entries.append(entry)

    # Write complete audit array to output_filepath
    out_path = Path(output_filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(audit_entries, f, indent=2, ensure_ascii=False)

    print(f"[+] Audit ledger exported to: {out_path.resolve()}")

    # Perform Verification Pass
    with open(out_path, "r", encoding="utf-8") as f:
        verified_ledger = json.load(f)

    total_records = len(verified_ledger)
    pass_count = sum(1 for item in verified_ledger if item["validation_status"] == "PASS")
    pass_rate = (pass_count / total_records) * 100 if total_records > 0 else 0

    print(f"[+] Verification Pass Summary:")
    print(f"    - Total Audited Records: {total_records}")
    print(f"    - Validation Pass Rate: {pass_rate:.2f}% ({pass_count}/{total_records})")

    # Assertions
    assert total_records > 0, f"Assertion Failed: Expected total audited records > 0, got {total_records}"
    assert pass_rate == 100.0, f"Assertion Failed: Expected 100% PASS rate, got {pass_rate:.2f}%"

    for idx, item in enumerate(verified_ledger):
        parsed = item["parsed_json_output"]
        assert isinstance(parsed, dict), f"Item #{idx} parsed_json_output is not a dict"
        
        # Check non-empty lists
        for field in ["attack_vector_steps", "preconditions", "affected_solidity_constructs"]:
            lst = parsed.get(field)
            assert isinstance(lst, list) and len(lst) > 0, (
                f"Item #{idx} ({item['finding_id']}) field '{field}' must deserialize into non-empty list, got: {lst}"
            )
        
        # Check taxonomy path in database
        tax_path = parsed.get("taxonomy_path")
        assert tax_path in valid_paths_set, (
            f"Item #{idx} ({item['finding_id']}) taxonomy_path '{tax_path}' not found in vulnerability_taxonomy"
        )

    print("[+] All verification assertions PASSED with 0 errors!")

    # Print 3 sample entries to console for human inspection
    print("\n" + "="*80)
    print("INSPECTION SAMPLE ENTRIES (3 Concrete Audit Findings):")
    print("="*80)

    for i, sample in enumerate(verified_ledger[:3], 1):
        print(f"\n--- SAMPLE #{i} ---")
        print(f"Finding ID    : {sample['finding_id']}")
        print(f"Source Pool   : {sample['source_pool']}")
        print(f"Protocol Name : {sample['protocol_name']}")
        print(f"Status        : {sample['validation_status']}")
        print(f"Raw Input Prompt Excerpt (first 300 chars):")
        print("-" * 50)
        print(sample['raw_input_prompt'][:300] + "...")
        print("-" * 50)
        print("Parsed JSON Output:")
        print(json.dumps(sample['parsed_json_output'], indent=2))

    conn.close()
    return {
        "total_records": total_records,
        "pass_count": pass_count,
        "output_filepath": str(out_path.resolve())
    }

if __name__ == "__main__":
    asyncio.run(run_audit_batch_and_export(sample_limit=32))
