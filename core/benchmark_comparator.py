import asyncio
import json
import random
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any, List

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from core.pipeline import get_prompt_config

def check_vllm_reachability(expected_model: str = "nvidia/Qwen3.6-27B-NVFP4") -> bool:
    """Verifies that the vLLM server is reachable and loaded with the expected model."""
    cfg = get_prompt_config()
    endpoint = cfg.get("vllm_endpoint", "http://192.168.1.57:8000/v1/chat/completions")
    base_url = endpoint.replace("/v1/chat/completions", "/v1/models")
    
    try:
        req = urllib.request.Request(base_url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status == 200:
                models_data = json.loads(resp.read().decode("utf-8"))
                loaded_models = [m.get("id") for m in models_data.get("data", [])]
                print(f"[+] vLLM Server Reachable at {base_url}. Loaded models: {loaded_models}")
                if expected_model and expected_model not in loaded_models:
                    print(f"[!] WARNING: Expected model '{expected_model}' not found in loaded models: {loaded_models}")
                    print(f"[!] Please switch / load '{expected_model}' on the vLLM server before running judge pass.")
                    return False
                return True
    except Exception as e:
        print(f"[!] CRITICAL: Cannot connect to vLLM server at {base_url}: {e}")
        return False
    return False

def evaluate_pair_single(
    finding_id: Any,
    rec_27b: Dict[str, Any],
    rec_9b: Dict[str, Any],
    cfg: Dict[str, Any]
) -> Dict[str, Any]:
    """Runs a single judge evaluation query comparing 27B vs 9B outputs with randomized position order."""
    endpoint = cfg.get("vllm_endpoint", "http://192.168.1.57:8000/v1/chat/completions")
    model_name = "nvidia/Qwen3.6-27B-NVFP4"
    
    payload_27b = rec_27b.get("parsed_json_output") or rec_27b.get("payload") or {}
    payload_9b = rec_9b.get("parsed_json_output") or rec_9b.get("payload") or {}
    
    # Position swapping to eliminate position bias
    swap = random.choice([True, False])
    if swap:
        answer_a = payload_9b
        answer_b = payload_27b
        model_a_name = "9B"
        model_b_name = "27B"
    else:
        answer_a = payload_27b
        answer_b = payload_9b
        model_a_name = "27B"
        model_b_name = "9B"
        
    system_prompt = (
        "You are an expert AI evaluator judging the quality of smart contract vulnerability analysis outputs. "
        "Compare Answer A and Answer B based on:\n"
        "1. Taxonomy Path Accuracy: Which path is more precise and appropriate?\n"
        "2. Root Cause Clarity: Which explanation is clearer and more technically accurate?\n"
        "3. Attack Vector Precision: Which sequential steps are more logical and actionable?\n\n"
        "Output ONLY a valid JSON object strictly matching this schema:\n"
        "{\n"
        '  "winner": "Model_A" | "Model_B" | "Tie",\n'
        '  "taxonomy_score_diff": 0,\n'
        '  "explanation_quality_diff": 0,\n'
        '  "reasoning": "<brief explanation of judgment>"\n'
        "}"
    )

    title = rec_27b.get("protocol_name") or f"Finding #{finding_id}"
    user_prompt = (
        f"Finding Context / Title: {title}\n\n"
        f"--- ANSWER A ---\n{json.dumps(answer_a, indent=2)}\n\n"
        f"--- ANSWER B ---\n{json.dumps(answer_b, indent=2)}\n"
    )

    req_payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"}
    }

    judge_raw = None
    judge_json = {}
    
    try:
        req_data = json.dumps(req_payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(endpoint, data=req_data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=90.0) as resp:
            resp_bytes = resp.read()
            resp_data = json.loads(resp_bytes.decode("utf-8"))
            msg = resp_data["choices"][0]["message"]
            judge_raw = (msg.get("content") or msg.get("reasoning") or "").strip()
            judge_json = json.loads(judge_raw)
    except Exception as e:
        judge_json = {
            "winner": "Tie",
            "taxonomy_score_diff": 0,
            "explanation_quality_diff": 0,
            "reasoning": f"Evaluation error: {e}"
        }

    raw_winner = judge_json.get("winner", "Tie")
    
    # Map raw winner back to true model name (9B vs 27B vs Tie)
    if raw_winner == "Model_A":
        true_winner = model_a_name
    elif raw_winner == "Model_B":
        true_winner = model_b_name
    else:
        true_winner = "Tie"

    # Normalize score diff relative to 9B vs 27B
    raw_tax_diff = judge_json.get("taxonomy_score_diff", 0)
    raw_exp_diff = judge_json.get("explanation_quality_diff", 0)
    if model_a_name == "9B":
        diff_9b_vs_27b_tax = raw_tax_diff
        diff_9b_vs_27b_exp = raw_exp_diff
    else:
        diff_9b_vs_27b_tax = -raw_tax_diff
        diff_9b_vs_27b_exp = -raw_exp_diff

    # Check exact taxonomy alignment between 27B and 9B
    tax_27b = payload_27b.get("taxonomy_path")
    tax_9b = payload_9b.get("taxonomy_path")
    taxonomy_exact_match = (tax_27b is not None and tax_27b == tax_9b)

    return {
        "finding_id": finding_id,
        "true_winner": true_winner,
        "swap_positions": swap,
        "taxonomy_exact_match": taxonomy_exact_match,
        "taxonomy_27b": tax_27b,
        "taxonomy_9b": tax_9b,
        "score_diff_taxonomy_9b": diff_9b_vs_27b_tax,
        "score_diff_explanation_9b": diff_9b_vs_27b_exp,
        "judge_reasoning": judge_json.get("reasoning", "")
    }

async def run_judge_evaluation(
    file_27b: str = "audit_logs/test_batch_27b.json",
    file_9b: str = "audit_logs/test_batch_9b.json",
    output_report_file: str = "audit_logs/model_comparison_report.json"
) -> dict:
    """Orchestrates 27B LLM-as-a-Judge comparison between 27B and 9B output ledgers."""
    path_27b = Path(file_27b)
    path_9b = Path(file_9b)
    
    if not path_27b.exists():
        raise FileNotFoundError(f"Baseline file {path_27b} does not exist.")
    if not path_9b.exists():
        raise FileNotFoundError(f"9B output file {path_9b} does not exist.")

    with open(path_27b, "r", encoding="utf-8") as f:
        records_27b = json.load(f)
    with open(path_9b, "r", encoding="utf-8") as f:
        records_9b = json.load(f)

    map_27b = {r["finding_id"]: r for r in records_27b if "finding_id" in r}
    map_9b = {r["finding_id"]: r for r in records_9b if "finding_id" in r}

    matched_ids = sorted(list(set(map_27b.keys()) & set(map_9b.keys())))
    print(f"[+] Found {len(matched_ids)} matching report records in both 27B and 9B ledgers.")

    if not check_vllm_reachability(expected_model="nvidia/Qwen3.6-27B-NVFP4"):
        print("\n" + "!"*65)
        print("ACTION REQUIRED BY USER:")
        print("Please load 'nvidia/Qwen3.6-27B-NVFP4' on http://192.168.1.57:8000")
        print("Then re-run: python core/benchmark_comparator.py")
        print("!"*65 + "\n")
        return {"status": "WAITING_FOR_27B_MODEL", "matched_records": len(matched_ids)}

    cfg = get_prompt_config()
    start_time = time.time()
    evaluations = []

    print(f"[+] Starting position-randomized 27B LLM-as-a-Judge evaluations across {len(matched_ids)} reports...")
    
    import concurrent.futures
    loop = asyncio.get_running_loop()
    concurrency_slots = int(cfg.get("concurrency_slots", 16))

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_slots) as executor:
        futures = [
            loop.run_in_executor(
                executor,
                evaluate_pair_single,
                fid,
                map_27b[fid],
                map_9b[fid],
                cfg
            )
            for fid in matched_ids
        ]
        evaluations = await asyncio.gather(*futures)

    duration = time.time() - start_time
    total_evals = len(evaluations)

    # Compute metrics
    win_9b = sum(1 for e in evaluations if e["true_winner"] == "9B")
    tie_count = sum(1 for e in evaluations if e["true_winner"] == "Tie")
    win_27b = sum(1 for e in evaluations if e["true_winner"] == "27B")
    
    taxonomy_exact_count = sum(1 for e in evaluations if e["taxonomy_exact_match"])

    win_rate_9b = (win_9b / total_evals * 100) if total_evals > 0 else 0.0
    equality_rate_9b = ((win_9b + tie_count) / total_evals * 100) if total_evals > 0 else 0.0
    win_rate_27b = (win_27b / total_evals * 100) if total_evals > 0 else 0.0
    tie_rate = (tie_count / total_evals * 100) if total_evals > 0 else 0.0
    taxonomy_alignment_pct = (taxonomy_exact_count / total_evals * 100) if total_evals > 0 else 0.0
    sec_per_comparison = (duration / total_evals) if total_evals > 0 else 0.0

    print("\n" + "="*60)
    print("      9B vs 27B MODEL BENCHMARK COMPARATIVE QUALITY MATRIX")
    print("="*60)
    print(f" Total Reports Evaluated      : {total_evals}")
    print(f" Total Evaluation Duration    : {duration:.2f} seconds ({sec_per_comparison:.2f} s/report)")
    print("-" * 60)
    print(f" 9B Win Count                 : {win_9b} ({win_rate_9b:.2f}%)")
    print(f" Tie / Equivalent Quality     : {tie_count} ({tie_rate:.2f}%)")
    print(f" 27B Win Count                : {win_27b} ({win_rate_27b:.2f}%)")
    print("-" * 60)
    print(f" 9B Quality Parity Rate (Win+Tie) : {equality_rate_9b:.2f}%")
    print(f" Taxonomy Path Alignment       : {taxonomy_alignment_pct:.2f}% ({taxonomy_exact_count}/{total_evals} exact match)")
    print("="*60 + "\n")

    report_payload = {
        "summary": {
            "total_evaluated": total_evals,
            "duration_seconds": duration,
            "seconds_per_report": sec_per_comparison,
            "9b_wins": win_9b,
            "9b_win_rate_pct": win_rate_9b,
            "ties": tie_count,
            "tie_rate_pct": tie_rate,
            "27b_wins": win_27b,
            "27b_win_rate_pct": win_rate_27b,
            "9b_quality_parity_rate_pct": equality_rate_9b,
            "taxonomy_alignment_pct": taxonomy_alignment_pct
        },
        "evaluations": evaluations
    }

    out_path = Path(output_report_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print(f"[+] Exported detailed comparison report to: {out_path.resolve()}")
    return report_payload

if __name__ == "__main__":
    asyncio.run(run_judge_evaluation())
