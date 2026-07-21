import argparse
import asyncio
import concurrent.futures
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

# Add project workspace root to sys.path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from typing import Dict, Any, List, Optional
from core.database import get_unified_connection, attach_vulnerabilities_db, DB_LOCK
from core.batch_enricher import _get_active_taxonomy_guide, process_single_finding_enrichment
from core.pipeline import get_prompt_config
from core.preprocessor import QUEUE_DISTRIBUTION_FILE, run_offline_queue_preprocessing

async def run_production_78k_enrichment(limit: Optional[int] = None, run_inference: bool = False) -> Dict[str, Any]:
    """
    Production batch worker running Qwen3.5-9B enrichment over the pre-processed finding queue.
    Requires run_inference=True (or --run-inference flag) to execute HTTP requests against http://192.168.1.57:8000.
    Consumes sorted sequence buckets, dispatches with 240 concurrency slots, and commits in 100-record chunks.
    """
    if not run_inference:
        print("[-] Notice: Safety guard active. '--run-inference' flag is REQUIRED to send HTTP completion requests to vLLM.")
        print("[+] To perform offline pre-processing, run: python core/preprocessor.py")
        print("[+] To execute live inference, run: python core/production_batch_enricher.py --run-inference")
        return {"status": "aborted", "reason": "Missing --run-inference flag"}

    # 1. Load or run offline queue pre-processing
    if not QUEUE_DISTRIBUTION_FILE.exists():
        print("[+] Pre-processed queue file not found. Launching offline pre-processor...")
        run_offline_queue_preprocessing()

    with open(QUEUE_DISTRIBUTION_FILE, "r", encoding="utf-8") as f:
        queue_data = json.load(f)

    conn = get_unified_connection()
    attach_vulnerabilities_db(conn)
    cursor = conn.cursor()

    # 2. Resumability check: get completed finding IDs
    cursor.execute("SELECT finding_id FROM vuln.enriched_findings_metadata")
    completed_ids = set(r[0] for r in cursor.fetchall())
    print(f"[+] Clean startup: {len(completed_ids)} findings already enriched in database.")

    # 3. Load findings details and filter out completed
    cursor.execute("SELECT id, source_pool, protocol_name, source_repo, title, content_markdown, severity FROM vuln.normalized_findings")
    all_findings_map = {r["id"]: dict(r) for r in cursor.fetchall()}

    buckets = queue_data.get("buckets", {})
    staged_items: List[Dict[str, Any]] = []

    # Flatten bucket queues in tier order: less_than_1k -> 1k_to_2k -> 2k_to_4k -> greater_than_4k
    tier_order = ["less_than_1k", "1k_to_2k", "2k_to_4k", "greater_than_4k"]
    for tier in tier_order:
        tier_items = buckets.get(tier, [])
        for item in tier_items:
            fid = item["id"]
            if fid not in completed_ids and fid in all_findings_map:
                staged_items.append(all_findings_map[fid])

    total_target = len(staged_items)
    if limit and limit > 0:
        staged_items = staged_items[:limit]
        total_target = len(staged_items)

    print(f"[+] Total target findings staged for inference run: {total_target}")
    if total_target == 0:
        print("[+] All findings are already enriched! Nothing to process.")
        conn.close()
        return {"status": "success", "processed": 0, "total": 0}

    taxonomy_guide = _get_active_taxonomy_guide(conn)
    cfg = get_prompt_config()
    cfg["vllm_endpoint"] = cfg.get("vllm_endpoint", "http://192.168.1.57:8000/v1/chat/completions")
    cfg["model_name"] = cfg.get("model_name", "Kbenkhaled/Qwen3.5-9B-NVFP4")

    concurrency_slots = 240
    processed_count = 0
    start_time = time.time()

    print(f"[+] Launching continuous worker pool with EXACTLY {concurrency_slots} parallel requests ACTIVE ALL THE TIME...")
    print(f"[+] Target endpoint: {cfg['vllm_endpoint']} | Model: {cfg['model_name']}")

    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    for item in staged_items:
        queue.put_nowait(item)

    db_lock = asyncio.Lock()
    pending_commit = []

    async def commit_records(records: List[Dict[str, Any]]):
        nonlocal processed_count
        if not records:
            return
        with DB_LOCK:
            with conn:
                for r in records:
                    data = r["payload"]
                    finding_id = r["finding_id"]
                    source_pool = r["source_pool"]
                    tax_path = data.get("taxonomy_path", "smart_contract/reentrancy/read_only/view_desync")
                    summary = data.get("vulnerability_summary", "")
                    root_cause = data.get("root_cause_explanation", "")
                    attack_steps_json = json.dumps(data.get("attack_vector_steps", []))
                    preconditions_json = json.dumps(data.get("preconditions", []))
                    impact_scope = data.get("impact_scope", "direct_theft_of_user_funds")
                    affected_constructs_json = json.dumps(data.get("affected_solidity_constructs", []))
                    remediation = data.get("remediation_pattern", "")
                    slug = data.get("taxonomy_slug", tax_path.split("/")[-1])
                    try:
                        suitability_score = float(data.get("training_suitability_score", 1.0))
                    except (ValueError, TypeError):
                        suitability_score = 1.0
                    suitability_reason = str(data.get("training_suitability_reason") or "")

                    cursor.execute("""
                    INSERT OR REPLACE INTO vuln.enriched_findings_metadata (
                        finding_id, taxonomy_path, vulnerability_summary, root_cause_explanation,
                        attack_vector_steps_json, preconditions_json, impact_scope,
                        affected_constructs_json, remediation_pattern,
                        training_suitability_score, training_suitability_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        finding_id, tax_path, summary, root_cause,
                        attack_steps_json, preconditions_json, impact_scope,
                        affected_constructs_json, remediation,
                        suitability_score, suitability_reason
                    ))

                    cursor.execute("""
                    INSERT OR IGNORE INTO vuln.vulnerability_tags_index (finding_id, source_pool, tag)
                    VALUES (?, ?, ?)
                    """, (finding_id, source_pool, slug))

                    processed_count += 1

        elapsed_sec = time.time() - start_time
        speed = processed_count / elapsed_sec if elapsed_sec > 0 else 0.0
        remaining_items = total_target - processed_count
        eta_min = (remaining_items / speed) / 60.0 if speed > 0 else 0.0
        elapsed_min = elapsed_sec / 60.0
        print(f"[Processed: {processed_count} / {total_target} | Speed: {speed:.2f} items/sec | Elapsed: {elapsed_min:.2f} min | ETA: {eta_min:.2f} min]")

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_slots) as executor:
        async def worker():
            while True:
                try:
                    finding = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                res = await loop.run_in_executor(executor, process_single_finding_enrichment, finding, taxonomy_guide, cfg)
                if res and res.get("validation_status") == "PASS" and res.get("payload"):
                    records_to_commit = None
                    async with db_lock:
                        pending_commit.append(res)
                        if len(pending_commit) >= 10:
                            records_to_commit = list(pending_commit)
                            pending_commit.clear()

                    if records_to_commit:
                        await commit_records(records_to_commit)

                queue.task_done()

        # Launch 240 worker tasks simultaneously (100% saturation at all times)
        workers = [asyncio.create_task(worker()) for _ in range(concurrency_slots)]
        await asyncio.gather(*workers)

        if pending_commit:
            await commit_records(pending_commit)
            pending_commit.clear()

    conn.close()
    return {
        "status": "completed",
        "processed_count": processed_count,
        "total_target": total_target,
        "elapsed_seconds": round(time.time() - start_time, 2)
    }

def main():
    parser = argparse.ArgumentParser(description="Production Batch Enricher Runner for 78k Dataset")
    parser.add_argument("--run-inference", action="store_true", help="Explicitly enable sending HTTP completion requests to vLLM endpoint.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to process for pre-flight testing.")
    args = parser.parse_args()

    asyncio.run(run_production_78k_enrichment(limit=args.limit, run_inference=args.run_inference))

if __name__ == "__main__":
    main()
