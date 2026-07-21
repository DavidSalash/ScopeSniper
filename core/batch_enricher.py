import asyncio
import json
import urllib.request
import traceback
import sqlite3
from typing import Dict, Any, List, Optional
from core.database import get_unified_connection, attach_vulnerabilities_db, DB_LOCK
from core.pipeline import get_prompt_config

def _get_stratified_samples(conn: sqlite3.Connection, sample_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Selects stratified findings query taking up to 3 reports per distinct (source_pool, protocol_name/source_repo) group."""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, source_pool, protocol_name, source_repo, title, content_markdown, severity 
    FROM vuln.normalized_findings
    """)
    all_findings = [dict(r) for r in cursor.fetchall()]

    # Group using compound key combining source_pool and protocol_name (or source_repo author)
    group_map: Dict[tuple, List[Dict[str, Any]]] = {}
    for f in all_findings:
        pool = f.get("source_pool") or "unknown"
        proto = f.get("protocol_name") or f.get("source_repo") or "unknown"
        key = (pool, proto)
        group_map.setdefault(key, []).append(f)

    stratified: List[Dict[str, Any]] = []
    # Collect up to 3 distinct reports per group
    for key, items in group_map.items():
        stratified.extend(items[:3])

    if sample_limit and sample_limit > 0:
        return stratified[:sample_limit]
    return stratified

def _get_active_taxonomy_guide(conn: sqlite3.Connection) -> List[Dict[str, str]]:
    """Fetches list of active taxonomy path and description records from database."""
    cursor = conn.cursor()
    cursor.execute("SELECT path, description FROM vuln.vulnerability_taxonomy WHERE description IS NULL OR description NOT LIKE 'Mined pattern tag:%'")
    return [{"path": r["path"], "description": r["description"] or ""} for r in cursor.fetchall()]

def _get_active_taxonomy_paths(conn: sqlite3.Connection) -> List[str]:
    """Fetches list of active taxonomy paths in database."""
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM vuln.vulnerability_taxonomy")
    return [r[0] for r in cursor.fetchall()]

def process_single_finding_enrichment(
    finding: Dict[str, Any],
    taxonomy_guide_or_paths: Any,
    cfg: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Executes vLLM structured JSON completion request for a single finding report,
    with fallback parsing for offline/mock environments.
    """
    endpoint = cfg.get("vllm_endpoint", "http://192.168.1.57:8000/v1/chat/completions")
    model_name = cfg.get("model_name", "nvidia/Qwen3.6-27B-NVFP4")
    max_tokens = cfg.get("max_tokens", 4096)

    title = finding.get("title", "Vulnerability Finding")
    content = finding.get("content_markdown", "") or f"Title: {title}"
    severity = finding.get("severity", "high")
    
    # Standardize taxonomy guide
    if taxonomy_guide_or_paths and isinstance(taxonomy_guide_or_paths[0], str):
        taxonomy_guide = [{"path": p, "description": ""} for p in taxonomy_guide_or_paths]
    else:
        taxonomy_guide = taxonomy_guide_or_paths or []

    valid_paths = [t["path"] for t in taxonomy_guide]
    
    # Pick target valid path (fallback if none match)
    default_path = "smart_contract/reentrancy/read_only/view_desync"
    if valid_paths and default_path not in valid_paths:
        default_path = valid_paths[0]

    system_prompt = (
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

    user_prompt = f"Finding Title: {title}\nSeverity: {severity}\n\nContent:\n{content[:2000]}"
    raw_input_prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}
    }

    raw_vllm_response = None
    extracted_data = None
    validation_status = "FAIL"
    validation_errors = []

    max_retries = 10
    for attempt in range(max_retries):
        try:
            req_data = json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=180.0) as resp:
                resp_bytes = resp.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))
                msg = resp_json["choices"][0]["message"]
                
                # Prefer content field; if None, attempt extracting JSON from reasoning
                content_text = msg.get("content") or ""
                reasoning_text = msg.get("reasoning_content") or msg.get("reasoning") or ""
                
                raw_content = content_text.strip()
                if not raw_content and reasoning_text:
                    # Search for JSON object within reasoning
                    s_idx = reasoning_text.find("{")
                    e_idx = reasoning_text.rfind("}")
                    if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                        raw_content = reasoning_text[s_idx:e_idx+1]
                    else:
                        raw_content = reasoning_text

                raw_vllm_response = raw_content.strip()
                if not raw_vllm_response:
                    raise ValueError("vLLM response message content is empty or null")
                
                try:
                    extracted_data = json.loads(raw_vllm_response)
                except Exception:
                    # Attempt JSON repair (strip markdown blocks / slice JSON brackets)
                    cleaned = raw_vllm_response.replace("```json", "").replace("```", "").strip()
                    s_idx = cleaned.find("{")
                    e_idx = cleaned.rfind("}")
                    if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                        extracted_data = json.loads(cleaned[s_idx:e_idx+1])
                    else:
                        raise
                break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[!] Timeout/Error for finding {finding['id']} (attempt {attempt+1}/{max_retries}): {e}. Resending request...")
                import time
                time.sleep(1.0)
            else:
                print(f"[-] vLLM Request Failed for finding {finding['id']} after {max_retries} attempts: {e}")
                validation_errors.append(f"vLLM Request Error: {e}")
                raw_vllm_response = None
                extracted_data = None

    # Strict validation of raw vLLM output (NO defaults or mock fallbacks)
    if not isinstance(extracted_data, dict):
        validation_status = "FAIL"
        validation_errors.append("Model failed to output valid JSON object")
    else:
        # Validate required keys and check for hardcoded/generic placeholder text
        required_keys = ["vulnerability_summary", "attack_vector_steps", "root_cause_explanation"]
        placeholder_strings = [
            "Analyze contract logic",
            "Identified security issue in",
            "Contract flaw reported in",
            "Identify state inconsistency"
        ]

        for req_key in required_keys:
            val = extracted_data.get(req_key)
            if val is None:
                validation_errors.append(f"Missing required key: '{req_key}'")
            elif isinstance(val, str):
                if not val.strip():
                    validation_errors.append(f"Empty value for required key: '{req_key}'")
                elif any(p_str in val for p_str in placeholder_strings):
                    validation_errors.append(f"Generic placeholder text found in required key: '{req_key}'")
            elif isinstance(val, list):
                if len(val) == 0:
                    validation_errors.append(f"Empty list for required key: '{req_key}'")
                else:
                    for idx, item in enumerate(val):
                        if not isinstance(item, str) or not item.strip():
                            validation_errors.append(f"Item {idx} in '{req_key}' is empty or not a string")
                        elif any(p_str in str(item) for p_str in placeholder_strings):
                            validation_errors.append(f"Generic placeholder text found in '{req_key}' item {idx}")
            else:
                validation_errors.append(f"Invalid type for required key: '{req_key}'")

        # Normalize taxonomy_path against valid active taxonomy set if taxonomy_path is present
        tax_path = extracted_data.get("taxonomy_path")
        valid_set = set(valid_paths)
        if valid_paths and tax_path and tax_path not in valid_set:
            normalized = None
            alt1 = tax_path.replace("smart_contract/", "defi_protocol/")
            alt2 = tax_path.replace("defi_protocol/", "smart_contract/")
            if alt1 in valid_set:
                normalized = alt1
            elif alt2 in valid_set:
                normalized = alt2
            else:
                for vp in valid_paths:
                    if vp.endswith(tax_path) or tax_path.endswith(vp) or vp.split("/")[-1] == tax_path.split("/")[-1]:
                        normalized = vp
                        break
            if normalized:
                extracted_data["taxonomy_path"] = normalized

        if not validation_errors:
            validation_status = "PASS"
        else:
            validation_status = "FAIL"

    protocol_name = finding.get("protocol_name") or finding.get("source_repo") or "unknown"

    return {
        "finding_id": finding["id"],
        "source_pool": finding.get("source_pool", "unknown"),
        "protocol_name": protocol_name,
        "raw_input_prompt": raw_input_prompt,
        "raw_vllm_response": raw_vllm_response,
        "parsed_json_output": extracted_data,
        "payload": extracted_data,
        "validation_status": validation_status,
        "validation_errors": validation_errors
    }

async def run_enrichment_batch(sample_limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Orchestrates vLLM JSON-mode batch extraction over stratified findings sample,
    persisting output into enriched_findings_metadata and vulnerability_tags_index
    with up to concurrency_slots parallel worker requests.
    """
    import concurrent.futures

    conn = get_unified_connection()
    attach_vulnerabilities_db(conn)

    samples = _get_stratified_samples(conn, sample_limit)
    taxonomy_guide = _get_active_taxonomy_guide(conn)
    cfg = get_prompt_config()
    
    model_name = cfg.get("model_name", "")
    if "9B" in model_name or "9b" in model_name:
        concurrency_slots = 240
    else:
        concurrency_slots = int(cfg.get("concurrency_slots", 32))

    print(f"[+] Using {concurrency_slots} concurrency workers for model '{model_name}'")

    processed_count = 0
    results = []

    # Parallel processing of HTTP enrichment payloads up to concurrency_slots (240 workers for 9B)
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_slots) as executor:
        futures = [
            loop.run_in_executor(executor, process_single_finding_enrichment, finding, taxonomy_guide, cfg)
            for finding in samples
        ]
        enrichment_results = await asyncio.gather(*futures)

    # Persist extracted results into database
    for res in enrichment_results:
        results.append(res)
        data = res.get("payload")
        if not data or res.get("validation_status") != "PASS":
            continue

        finding_id = res["finding_id"]
        source_pool = res["source_pool"]

        tax_path = data.get("taxonomy_path", "smart_contract/reentrancy/read_only/view_desync")
        summary = data.get("vulnerability_summary", "")
        root_cause = data.get("root_cause_explanation", "")
        attack_steps_json = json.dumps(data.get("attack_vector_steps", []))
        preconditions_json = json.dumps(data.get("preconditions", []))
        impact_scope = data.get("impact_scope", "direct_theft_of_user_funds")
        affected_constructs_json = json.dumps(data.get("affected_solidity_constructs", []))
        remediation = data.get("remediation_pattern", "")
        slug = data.get("taxonomy_slug", tax_path.split("/")[-1])

        cursor = conn.cursor()
        with DB_LOCK:
            with conn:
                cursor.execute("""
                INSERT OR REPLACE INTO vuln.enriched_findings_metadata (
                    finding_id, taxonomy_path, vulnerability_summary, root_cause_explanation,
                    attack_vector_steps_json, preconditions_json, impact_scope,
                    affected_constructs_json, remediation_pattern
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    finding_id, tax_path, summary, root_cause,
                    attack_steps_json, preconditions_json, impact_scope,
                    affected_constructs_json, remediation
                ))

                cursor.execute("""
                INSERT OR IGNORE INTO vuln.vulnerability_tags_index (finding_id, source_pool, tag)
                VALUES (?, ?, ?)
                """, (finding_id, source_pool, slug))

        processed_count += 1

    conn.close()
    return {
        "processed_count": processed_count,
        "sample_limit": sample_limit,
        "results": results
    }

if __name__ == "__main__":
    out = asyncio.run(run_enrichment_batch(sample_limit=5))
    print(f"[+] Batch enrichment completed. Processed items: {out['processed_count']}")

