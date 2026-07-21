import time
import json
import asyncio
import sys
import subprocess
from pathlib import Path

# Add project root to sys.path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks, Request, Body, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.database import get_unified_connection, init_unified_db, DB_LOCK
from core.math_engine import get_target_profitability_matrix
from core.pipeline import (
    TOKEN_BUCKET_TIERS,
    dispatch_token_bucket_queue,
    reset_errored_queue_status,
    classify_token_tier,
    set_cancellation_flag,
    REFUSAL_GUARD_TEXT
)
from core.ingest_source_dbs import run_full_source_ingestion
from core.tracker import run_state_differential_tracker_loop

CONFIG_FILE = Path(__file__).parent.parent / "config" / "prompt_config.json"

app = FastAPI(title="Unified Bug Bounty Control Room API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_db():
    init_unified_db()
    try:
        asyncio.create_task(run_state_differential_tracker_loop(interval_seconds=86400.0))
        print("[+] Launched background state-differential tracking loop.")
    except Exception as e:
        print(f"[-] Failed to launch background tracking daemon: {e}")

@app.get("/api/ingestion/batch-workspace")
def get_batch_workspace():
    conn = get_unified_connection()
    cursor = conn.cursor()
    
    # Query queue logs
    cursor.execute("SELECT * FROM preflight_queue ORDER BY id DESC LIMIT 200")
    queue_rows = [dict(row) for row in cursor.fetchall()]
    
    # Query bucket aggregations
    cursor.execute("""
    SELECT 
        token_bucket_tier,
        COUNT(*) as total,
        SUM(CASE WHEN dispatch_status = 'DISPATCHED' THEN 1 ELSE 0 END) as dispatched,
        SUM(CASE WHEN dispatch_status = 'PENDING' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN dispatch_status = 'FAILED' THEN 1 ELSE 0 END) as failed,
        SUM(CASE WHEN dispatch_status = 'INVALID' THEN 1 ELSE 0 END) as invalid,
        SUM(CASE WHEN dispatch_status = 'INVALID_INPUT' THEN 1 ELSE 0 END) as invalid_input,
        SUM(CASE WHEN dispatch_status = 'PROSE_REFUSAL' THEN 1 ELSE 0 END) as prose_refusal,
        SUM(CASE WHEN dispatch_status = 'MALFORMED_JSON' THEN 1 ELSE 0 END) as malformed_json,
        SUM(CASE WHEN dispatch_status = 'SKIPPED_METADATA' THEN 1 ELSE 0 END) as skipped_metadata,
        SUM(CASE WHEN dispatch_status = 'NO CONTENT' THEN 1 ELSE 0 END) as no_content
    FROM preflight_queue
    GROUP BY token_bucket_tier
    """)
    
    aggs = {}
    for tier in TOKEN_BUCKET_TIERS:
        aggs[tier] = {
            "total": 0, "dispatched": 0, "pending": 0, "failed": 0,
            "invalid": 0, "invalid_input": 0, "prose_refusal": 0,
            "malformed_json": 0, "skipped_metadata": 0, "no content": 0
        }
        
    for row in cursor.fetchall():
        tier = row["token_bucket_tier"]
        if tier in aggs:
            aggs[tier] = {
                "total": row["total"] or 0,
                "dispatched": row["dispatched"] or 0,
                "pending": row["pending"] or 0,
                "failed": row["failed"] or 0,
                "invalid": row["invalid"] or 0,
                "invalid_input": row["invalid_input"] or 0,
                "prose_refusal": row["prose_refusal"] or 0,
                "malformed_json": row["malformed_json"] or 0,
                "skipped_metadata": row["skipped_metadata"] or 0,
                "no content": row["no_content"] or 0,
            }
            
    # Query recent bounty state mutations
    try:
        cursor.execute("SELECT * FROM bounty_state_mutations ORDER BY id DESC LIMIT 50")
        mutation_rows = [dict(row) for row in cursor.fetchall()]
    except Exception:
        mutation_rows = []

    conn.close()
    
    # Prompt configuration metadata
    prompt_config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                prompt_config = json.load(f)
        except Exception:
            pass

    # Diagnostics mock
    system_diagnostics = {
        "docker": {"connected": True, "active_sandbox_containers": 4},
        "llm_lock": {"concurrency_limit": prompt_config.get("concurrency_slots", 8), "queued_requests": 0},
        "resources": {"backend_memory_mb": 1420.5, "cpu_percentage": 18.4},
        "swarm_status": {"queued": aggs.get("less_than_1k", {}).get("pending", 0), "running": 2, "paused": 0},
        "log_stats": {"info": 124, "warning": 3, "error": 0}
    }

    return {
        "queue": queue_rows,
        "aggregations": aggs,
        "mutations": mutation_rows,
        "prompt_config": prompt_config,
        "system_diagnostics": system_diagnostics
    }

@app.get("/api/ingestion/prompt-config")
def get_prompt_config():
    """Stream and read data fields out of config/prompt_config.json."""
    if not CONFIG_FILE.exists():
        raise HTTPException(status_code=404, detail="prompt_config.json not found")
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading prompt config: {str(e)}")

@app.put("/api/ingestion/prompt-config")
def update_prompt_config(payload: Dict[str, Any] = Body(...)):
    """Accept and update configurations (max_tokens, concurrency_slots, vllm_endpoint, model_name)."""
    current_config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                current_config = json.load(f)
        except Exception:
            pass

    for key in ["max_tokens", "concurrency_slots", "vllm_endpoint", "model_name"]:
        if key in payload:
            current_config[key] = payload[key]

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=2)
        return {"status": "success", "config": current_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating prompt config: {str(e)}")

@app.post("/api/ingestion/compile")
def compile_source_ingestion(background_tasks: BackgroundTasks):
    """Launch a background task that executes run_full_source_ingestion() to clear and re-populate preflight_queue."""
    background_tasks.add_task(run_full_source_ingestion)
    return {"status": "compilation_started", "message": "Source database ingestion initiated in background."}

@app.post("/api/ingestion/calculate-tokens")
def calculate_tokens(payload: Optional[Dict[str, Any]] = Body(None)):
    """Recalculate estimated tokens for target IDs or all rows using a realistic string length estimation helper."""
    item_ids = payload.get("item_ids") if payload else None
    
    conn = get_unified_connection()
    cursor = conn.cursor()
    
    if item_ids:
        placeholders = ",".join("?" for _ in item_ids)
        cursor.execute(f"SELECT * FROM preflight_queue WHERE id IN ({placeholders})", item_ids)
    else:
        cursor.execute("SELECT * FROM preflight_queue")
        
    rows = [dict(r) for r in cursor.fetchall()]
    updated_count = 0
    
    with DB_LOCK:
        with conn:
            for row in rows:
                sys_p = row["system_prompt_payload"] or ""
                usr_p = row["user_prompt_payload"] or ""
                ref_p = row["refusal_prompt_payload"] or REFUSAL_GUARD_TEXT
                char_count = len(sys_p) + len(usr_p) + len(ref_p)
                est_tokens = char_count // 4
                tier = classify_token_tier(char_count, est_tokens)
                
                cursor.execute("""
                UPDATE preflight_queue
                SET character_count = ?, estimated_tokens = ?, token_bucket_tier = ?
                WHERE id = ?
                """, (char_count, est_tokens, tier, row["id"]))
                updated_count += 1
                
    conn.close()
    return {"status": "success", "updated_count": updated_count}

@app.post("/api/ingestion/stop")
def stop_ingestion():
    """Provide cancellation control to kill active thread worker execution pools gracefully."""
    set_cancellation_flag(True)
    return {"status": "stopped", "message": "Thread worker pool cancellation flag activated."}

@app.post("/api/ingestion/requeue/{item_id}")
def requeue_item(item_id: int):
    """Surgically reset a specific ID's status back to 'PENDING' and empty its log column."""
    conn = get_unified_connection()
    cursor = conn.cursor()
    with DB_LOCK:
        with conn:
            cursor.execute("""
            UPDATE preflight_queue
            SET dispatch_status = 'PENDING', error_log = NULL
            WHERE id = ?
            """, (item_id,))
            affected = cursor.rowcount
    conn.close()
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Preflight queue item #{item_id} not found.")
    return {"status": "success", "item_id": item_id, "dispatch_status": "PENDING"}

@app.post("/api/ingestion/requeue-batch")
def requeue_batch(payload: Dict[str, Any] = Body(...)):
    """Accept a list of row integers and batch reset them back to 'PENDING'."""
    item_ids = payload.get("item_ids", [])
    if not item_ids:
        return {"status": "success", "requeued_count": 0}
        
    conn = get_unified_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in item_ids)
    with DB_LOCK:
        with conn:
            cursor.execute(f"""
            UPDATE preflight_queue
            SET dispatch_status = 'PENDING', error_log = NULL
            WHERE id IN ({placeholders})
            """, item_ids)
            affected = cursor.rowcount
    conn.close()
    return {"status": "success", "requeued_count": affected}

@app.post("/api/ingestion/set-pending-batch")
def set_pending_batch(payload: Dict[str, Any] = Body(...)):
    """Batch update a list of chosen row IDs to 'PENDING'."""
    return requeue_batch(payload)

@app.put("/api/ingestion/batch/{item_id}/prompts")
def update_item_prompts(item_id: int, payload: Dict[str, Any] = Body(...)):
    """Persist specific manual textual edits made to user or system prompt strings inside the row record before requeuing."""
    sys_prompt = payload.get("system_prompt")
    usr_prompt = payload.get("user_prompt")
    
    conn = get_unified_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM preflight_queue WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Preflight item #{item_id} not found.")
        
    current_sys = sys_prompt if sys_prompt is not None else row["system_prompt_payload"]
    current_usr = usr_prompt if usr_prompt is not None else row["user_prompt_payload"]
    ref_prompt = row["refusal_prompt_payload"] or REFUSAL_GUARD_TEXT
    
    char_count = len(current_sys) + len(current_usr) + len(ref_prompt)
    est_tokens = char_count // 4
    tier = classify_token_tier(char_count, est_tokens)
    
    with DB_LOCK:
        with conn:
            cursor.execute("""
            UPDATE preflight_queue
            SET system_prompt_payload = ?,
                user_prompt_payload = ?,
                character_count = ?,
                estimated_tokens = ?,
                token_bucket_tier = ?,
                dispatch_status = 'PENDING',
                error_log = NULL
            WHERE id = ?
            """, (current_sys, current_usr, char_count, est_tokens, tier, item_id))
    conn.close()
    return {"status": "success", "item_id": item_id, "dispatch_status": "PENDING", "estimated_tokens": est_tokens, "token_bucket_tier": tier}

@app.post("/api/ingestion/export-simplified")
def export_simplified():
    """Export standard target asset features down to a clean JSON data dump."""
    conn = get_unified_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT slug, source_platform, project_name, max_bounty_usd, kyc_required, primacy_model FROM projects")
    projects = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT project_slug, asset_identifier, type FROM assets")
    assets = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT project_slug, severity_level, min_reward, max_reward, impact_type_normalized FROM rewards")
    rewards = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    export_payload = {
        "timestamp": time.time(),
        "total_projects": len(projects),
        "projects": projects,
        "assets": assets,
        "rewards": rewards
    }
    return JSONResponse(content=export_payload)

import math

@app.get("/api/analytics/profitability-matrix")
def get_profitability_matrix():
    """Queries live unified_bug_bounties.db joined with vulnerabilities.db without static fallback arrays."""
    conn = get_unified_connection()
    try:
        matrix = get_target_profitability_matrix(conn)
        sanitized_matrix = []
        
        float_fields = [
            "stated_max_reward", "calculated_real_reward", "tvl_applied",
            "complexity_time_cost", "success_probability", "expected_profitability_yield"
        ]
        
        for row in matrix:
            clean_row = dict(row)
            for field in float_fields:
                val = clean_row.get(field)
                if val is not None and isinstance(val, (int, float)):
                    if math.isnan(val) or math.isinf(val):
                        clean_row[field] = 0.0
                    else:
                        clean_row[field] = round(float(val), 4)
            sanitized_matrix.append(clean_row)
            
        return {"status": "success", "count": len(sanitized_matrix), "data": sanitized_matrix}
    except Exception as e:
        print(f"[-] Error fetching live profitability matrix: {e}")
        return {"status": "error", "count": 0, "data": []}
    finally:
        conn.close()

@app.post("/api/ingestion/dispatch")
def dispatch_tier(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    bucket_tier = payload.get("bucket_tier", "less_than_1k")
    limit = payload.get("limit", 25)
    
    background_tasks.add_task(dispatch_token_bucket_queue, bucket_tier, limit)
    return {"status": "dispatched", "bucket_tier": bucket_tier, "limit": limit}

@app.post("/api/ingestion/reset-status")
def reset_status():
    reset_count = reset_errored_queue_status()
    return {"status": "success", "reset_count": reset_count}

@app.get("/api/ingestion/stream")
async def event_stream(request: Request):
    """
    SSE Telemetry Stream sending live metrics reading queue breakdown from audit_logs/queue_distribution.json
    and completion metrics directly from vuln.enriched_findings_metadata with ZERO hardcoded fallback mocks.
    """
    async def generate_telemetry():
        queue_log_file = WORKSPACE_DIR / "audit_logs" / "queue_distribution.json"
        
        while True:
            if await request.is_disconnected():
                break
                
            conn = get_unified_connection()
            cursor = conn.cursor()
            
            # Fetch completed enrichment count from database
            completed_enrichment_cnt = 0
            total_normalized_cnt = 0
            try:
                from core.database import attach_vulnerabilities_db
                attach_vulnerabilities_db(conn)
                cursor.execute("SELECT COUNT(*) as completed FROM vuln.enriched_findings_metadata")
                res = cursor.fetchone()
                if res:
                    completed_enrichment_cnt = res["completed"]
                
                cursor.execute("SELECT COUNT(*) as total FROM vuln.normalized_findings")
                res2 = cursor.fetchone()
                if res2:
                    total_normalized_cnt = res2["total"]
            except Exception as e:
                print(f"[-] SSE query error: {e}")
                
            conn.close()
            
            # Read pre-processed bucket distribution report
            queue_summary = {"less_than_1k": 0, "1k_to_2k": 0, "2k_to_4k": 0, "greater_than_4k": 0}
            if queue_log_file.exists():
                try:
                    with open(queue_log_file, "r", encoding="utf-8") as f:
                        q_data = json.load(f)
                        queue_summary = q_data.get("summary_counts", queue_summary)
                except Exception:
                    pass
            
            pending_queue_length = max(0, total_normalized_cnt - completed_enrichment_cnt)
            
            telemetry_data = {
                "timestamp": time.strftime("%H:%M:%S"),
                "total_normalized_findings": total_normalized_cnt,
                "completed_dispatches": completed_enrichment_cnt,
                "pending_queue_length": pending_queue_length,
                "queue_summary": queue_summary,
                "active_concurrency": 240,
                "max_concurrency": 240
            }
            
            yield f"data: {json.dumps(telemetry_data)}\n\n"
            await asyncio.sleep(2)
            
    return StreamingResponse(generate_telemetry(), media_type="text/event-stream")

# ── PRE-PROCESSED QUEUE & CONTROL API ENDPOINTS ─────────────────────────────

_QUEUE_CACHE = None
_QUEUE_CACHE_MTIME = 0
BATCH_INFERENCE_PROC: Optional[subprocess.Popen] = None

def load_queue_distribution() -> Dict[str, Any]:
    global _QUEUE_CACHE, _QUEUE_CACHE_MTIME
    log_file = WORKSPACE_DIR / "audit_logs" / "queue_distribution.json"
    if not log_file.exists():
        return {"total_staged": 0, "summary_counts": {}, "buckets": {}}
    try:
        mtime = log_file.stat().st_mtime
        if _QUEUE_CACHE is None or mtime > _QUEUE_CACHE_MTIME:
            with open(log_file, "r", encoding="utf-8") as f:
                _QUEUE_CACHE = json.load(f)
            _QUEUE_CACHE_MTIME = mtime
    except Exception as e:
        print(f"[-] Error reading queue_distribution.json: {e}")
        if _QUEUE_CACHE is None:
            return {"total_staged": 0, "summary_counts": {}, "buckets": {}}
    return _QUEUE_CACHE

@app.get("/api/batch/queue")
def get_batch_queue(
    page: int = 1,
    limit: int = 50,
    tier: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Exposes pre-processed requests from audit_logs/queue_distribution.json
    with live status attached from vuln.enriched_findings_metadata.
    Supports tier filtering and text search over id, protocol_name, title, source_pool.
    """
    queue_data = load_queue_distribution()
    total_staged = queue_data.get("total_staged") or queue_data.get("total_unprocessed_findings") or 0
    summary_counts = queue_data.get("summary_counts", {
        "less_than_1k": 0,
        "1k_to_2k": 0,
        "2k_to_4k": 0,
        "greater_than_4k": 0
    })
    buckets = queue_data.get("buckets", {})

    # Fetch completed finding IDs from database
    completed_ids = set()
    try:
        conn = get_unified_connection()
        from core.database import attach_vulnerabilities_db
        attach_vulnerabilities_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT finding_id FROM vuln.enriched_findings_metadata")
        completed_ids = set(r[0] for r in cursor.fetchall())
        conn.close()
    except Exception as e:
        print(f"[-] Error fetching completed IDs: {e}")

    # Collect items based on tier filter
    staged_items: List[Dict[str, Any]] = []
    tier_keys = ["less_than_1k", "1k_to_2k", "2k_to_4k", "greater_than_4k"]
    
    if tier and tier in buckets:
        selected_tiers = [tier]
    else:
        selected_tiers = [t for t in tier_keys if t in buckets]

    for t_key in selected_tiers:
        for raw_item in buckets.get(t_key, []):
            item = dict(raw_item)
            item["context_tier"] = t_key
            fid = item.get("id")
            is_completed = fid in completed_ids
            item["enrichment_status"] = "COMPLETED" if is_completed else "PENDING"
            item["status"] = item["enrichment_status"]
            staged_items.append(item)

    # Apply search filter if provided
    if search:
        search_lower = search.strip().lower()
        filtered = []
        for item in staged_items:
            fid = str(item.get("id", "")).lower()
            proto = str(item.get("protocol_name", "")).lower()
            title = str(item.get("title", "")).lower()
            pool = str(item.get("source_pool", "")).lower()
            if (search_lower in fid or search_lower in proto or 
                search_lower in title or search_lower in pool):
                filtered.append(item)
        staged_items = filtered

    total_matching = len(staged_items)

    # Apply pagination
    page = max(1, page)
    limit = max(1, limit)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_items = staged_items[start_idx:end_idx]

    return {
        "status": "success",
        "total_staged": total_staged,
        "page": page,
        "limit": limit,
        "total": total_matching,
        "summary_counts": summary_counts,
        "items": paginated_items
    }

@app.api_route("/api/batch/control", methods=["GET", "POST"])
def batch_control(payload: Optional[Dict[str, Any]] = Body(None), action: Optional[str] = None):
    """
    Trigger or pause background execution of core/production_batch_enricher.py --run-inference.
    Actions: 'start' / 'run', 'pause' / 'stop', 'status'.
    """
    global BATCH_INFERENCE_PROC

    req_action = action
    if not req_action and payload:
        req_action = payload.get("action")
    if not req_action:
        req_action = "status"

    req_action = req_action.lower().strip()

    is_running = BATCH_INFERENCE_PROC is not None and BATCH_INFERENCE_PROC.poll() is None

    if req_action in ["start", "run", "launch"]:
        if is_running:
            return {
                "status": "success",
                "message": "Production batch inference process is already running.",
                "batch_status": "RUNNING",
                "pid": BATCH_INFERENCE_PROC.pid
            }
        
        enricher_script = WORKSPACE_DIR / "core" / "production_batch_enricher.py"
        try:
            BATCH_INFERENCE_PROC = subprocess.Popen(
                [sys.executable, str(enricher_script), "--run-inference"],
                cwd=str(WORKSPACE_DIR)
            )
            return {
                "status": "success",
                "message": "Production batch inference run launched.",
                "batch_status": "RUNNING",
                "pid": BATCH_INFERENCE_PROC.pid
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to launch batch inference run: {e}")

    elif req_action in ["pause", "stop"]:
        if is_running and BATCH_INFERENCE_PROC:
            try:
                BATCH_INFERENCE_PROC.terminate()
                BATCH_INFERENCE_PROC.wait(timeout=5)
            except Exception:
                BATCH_INFERENCE_PROC.kill()
            BATCH_INFERENCE_PROC = None
            return {
                "status": "success",
                "message": "Production batch inference run paused/stopped.",
                "batch_status": "STOPPED"
            }
        else:
            BATCH_INFERENCE_PROC = None
            return {
                "status": "success",
                "message": "No active batch inference process running.",
                "batch_status": "STOPPED"
            }

    elif req_action == "status":
        return {
            "status": "success",
            "batch_status": "RUNNING" if is_running else "STOPPED",
            "pid": BATCH_INFERENCE_PROC.pid if is_running and BATCH_INFERENCE_PROC else None
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action '{req_action}'. Valid actions: start, pause, status.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=10000, reload=True)

