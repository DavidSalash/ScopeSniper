import asyncio
import json
import urllib.request
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_unified_connection, attach_vulnerabilities_db
from core.pipeline import get_prompt_config
from core.batch_enricher import _get_active_taxonomy_guide

conn = get_unified_connection()
attach_vulnerabilities_db(conn)
cursor = conn.cursor()
cursor.execute("SELECT id, source_pool, protocol_name, source_repo, title, content_markdown, severity FROM vuln.normalized_findings WHERE id='c4-2021-05-visorfinance-findings-80'")
finding = dict(cursor.fetchone())

taxonomy_guide = _get_active_taxonomy_guide(conn)
cfg = get_prompt_config()

endpoint = cfg.get("vllm_endpoint", "http://192.168.1.57:8000/v1/chat/completions")
model_name = cfg.get("model_name", "nvidia/Qwen3.6-27B-NVFP4")

default_path = taxonomy_guide[0]["path"]

system_prompt = (
    "You are an expert smart contract security auditor and AI trainer. "
    "Classify the input finding into our vulnerability taxonomy and extract rich structured metadata.\n"
    f"Valid active taxonomy guide: {json.dumps(taxonomy_guide)}\n"
    "Output ONLY a valid JSON object strictly matching this payload schema:\n"
    "{\n"
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

user_prompt = f"Finding Title: {finding.get('title')}\nSeverity: {finding.get('severity')}\n\nContent:\n{(finding.get('content_markdown') or '')[:2000]}"

payload = {
    "model": model_name,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    "temperature": 0.1,
    "max_tokens": 2048,
    "response_format": {"type": "json_object"}
}

req_data = json.dumps(payload).encode("utf-8")
headers = {"Content-Type": "application/json"}
req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")

try:
    with urllib.request.urlopen(req, timeout=120.0) as resp:
        resp_bytes = resp.read()
        resp_json = json.loads(resp_bytes.decode("utf-8"))
        print("FULL RESPONSE:")
        print(json.dumps(resp_json, indent=2))
except Exception as e:
    print("ERROR:", e)
