import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

# Add workspace root to system path
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from core.database import get_unified_connection, attach_vulnerabilities_db
from core.batch_enricher import run_enrichment_batch
from core.pipeline import get_prompt_config

def check_vllm_reachability() -> bool:
    """Verifies that the vLLM server on the 5090 is reachable before starting batch."""
    cfg = get_prompt_config()
    endpoint = cfg.get("vllm_endpoint", "http://192.168.1.57:8000/v1/chat/completions")
    base_url = endpoint.replace("/v1/chat/completions", "/v1/models")
    
    try:
        req = urllib.request.Request(base_url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status == 200:
                print(f"[+] vLLM Server Reachable at {base_url}")
                return True
    except Exception as e:
        print(f"[!] CRITICAL: Cannot connect to vLLM server at {base_url}: {e}")
        return False
    return False

import time

async def run_audit_batch_and_export(sample_limit: int = 250, output_filepath: str = "audit_logs/test_batch_9b.json") -> dict:
    if not check_vllm_reachability():
        raise ConnectionError("vLLM server is unreachable at http://192.168.1.57:8000")

    print(f"[+] Starting diverse stratified audit batch across {sample_limit} reports...")
    start_time = time.time()
    
    # 1. Execute live batch enrichment against local 5090 cluster
    batch_res = await run_enrichment_batch(sample_limit=sample_limit)
    results = batch_res.get("results", [])
    
    duration = time.time() - start_time
    throughput = len(results) / duration if duration > 0 else 0.0
    avg_latency = duration / len(results) if results else 0.0
    
    # 2. Export complete raw audit ledger to disk
    output_path = Path(output_filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    print(f"[+] Exported {len(results)} audit records to: {output_path.resolve()}")
    
    # 3. Perform automated verification and metric analysis
    total_audited = len(results)
    passed_records = [r for r in results if r.get("validation_status") == "PASS"]
    failed_records = [r for r in results if r.get("validation_status") == "FAIL"]
    
    pass_rate = (len(passed_records) / total_audited * 100) if total_audited > 0 else 0.0
    
    # Collect pool and author/protocol diversity metrics
    sources = set(r.get("source_pool", "unknown") for r in results)
    protocols = set(r.get("protocol_name", "unknown") for r in results)
    
    print("\n" + "="*50)
    print("DIVERSE BATCH AUDIT VERIFICATION SUMMARY (9B MODEL)")
    print("="*50)
    print(f"Total Audited Reports    : {total_audited}")
    print(f"Passed Schema Validation : {len(passed_records)} ({pass_rate:.2f}%)")
    print(f"Failed Validation        : {len(failed_records)}")
    print(f"Total Processing Time    : {duration:.2f} seconds")
    print(f"Throughput Rate          : {throughput:.2f} reports/sec")
    print(f"Average Latency / Report : {avg_latency:.2f} seconds")
    print(f"Distinct Source Pools    : {len(sources)} ({', '.join(sorted(sources))})")
    print(f"Distinct Protocols/Repos : {len(protocols)}")
    
    if failed_records:
        print("\n[!] Validation Failures Encountered:")
        for fr in failed_records[:5]:
            print(f"  - Finding ID {fr['finding_id']}: {fr.get('validation_errors')}")
        raise ValueError(f"{len(failed_records)} records failed schema validation!")
        
    print("\n[+] All audited records passed validation! Sample audit preview:")
    if results:
        sample = results[0]
        print(f"\n--- Sample Finding: {sample['finding_id']} ({sample['source_pool']} / {sample['protocol_name']}) ---")
        if sample.get("parsed_json_output"):
            print(f"Thinking Process: {sample['parsed_json_output'].get('thinking_process', '')[:100]}...")
            print(f"Taxonomy Path   : {sample['parsed_json_output'].get('taxonomy_path')}")
            print(f"Summary         : {sample['parsed_json_output'].get('vulnerability_summary')}")
            print(f"Attack Steps    : {len(sample['parsed_json_output'].get('attack_vector_steps', []))} steps extracted")
        
    return {
        "total_audited": total_audited,
        "pass_rate": pass_rate,
        "duration_seconds": duration,
        "throughput_reports_per_sec": throughput,
        "distinct_sources": len(sources),
        "distinct_protocols": len(protocols),
        "output_path": str(output_path)
    }

if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else "audit_logs/test_batch_9b.json"
    asyncio.run(run_audit_batch_and_export(sample_limit=250, output_filepath=output_file))

