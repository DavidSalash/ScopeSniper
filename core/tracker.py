import os
import sys
import json
import sqlite3
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add project root to sys.path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from core.database import init_unified_db, get_unified_connection, DB_LOCK

def safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None

def normalize_asset_key(identifier: Optional[str], asset_type: Optional[str], url: Optional[str] = None) -> Tuple[str, str]:
    clean_id = (identifier or url or "").strip().lower()
    clean_type = (asset_type or "contract").strip().lower()
    return (clean_id, clean_type)

def compare_and_apply_project_differential(incoming_project: dict, incoming_assets: list, conn: Optional[sqlite3.Connection] = None) -> list:
    """
    Row-level order-agnostic differential comparison engine matching incoming payload
    against existing database record state. Logs detected mutations to bounty_state_mutations,
    evicts preflight_queue entries back to PENDING, and commits state updates.
    """
    should_close_conn = False
    if conn is None:
        conn = get_unified_connection()
        should_close_conn = True

    slug = str(incoming_project.get("slug") or incoming_project.get("native_id") or incoming_project.get("id") or "").strip()
    platform = str(incoming_project.get("source_platform") or "unknown").strip().lower()
    if not slug:
        if should_close_conn:
            conn.close()
        return []

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE slug = ?", (slug,))
    db_proj_row = cursor.fetchone()
    db_proj = dict(db_proj_row) if db_proj_row else None

    # Handle New Program Discovery
    if not db_proj:
        with DB_LOCK:
            with conn:
                native_id = str(incoming_project.get("native_id") or incoming_project.get("id") or slug)
                proj_name = str(incoming_project.get("project_name") or incoming_project.get("project") or incoming_project.get("name") or slug).strip()
                desc = incoming_project.get("description") or incoming_project.get("program_overview") or ""
                overview = incoming_project.get("program_overview") or desc
                rules = incoming_project.get("out_of_scope_and_rules") or incoming_project.get("rules") or ""
                prioritized = incoming_project.get("prioritized_vulnerabilities") or ""
                web_url = incoming_project.get("website_url") or incoming_project.get("website")
                github_url = incoming_project.get("github_url") or incoming_project.get("github")
                logo = incoming_project.get("logo_url") or incoming_project.get("logo")
                p_max = safe_int(incoming_project.get("max_bounty_usd") if incoming_project.get("max_bounty_usd") is not None else incoming_project.get("max_bounty"))
                rewards_pool = safe_int(incoming_project.get("rewards_pool"))
                rewards_token = incoming_project.get("rewards_token") or "USDC"
                invite_only = safe_int(incoming_project.get("invite_only")) or 0
                kyc_req = safe_int(incoming_project.get("kyc_required")) or 0
                kyc_type = incoming_project.get("kyc_type") or ("light" if kyc_req else "none")
                immunefi_std = safe_int(incoming_project.get("immunefi_standard")) or 0
                primacy_model = incoming_project.get("primacy_model") or "impact"
                scaling_pct = incoming_project.get("scaling_percentage") or 10.0
                raw_json_str = incoming_project.get("raw_json") or json.dumps(incoming_project, default=str)

                cursor.execute("""
                INSERT OR REPLACE INTO projects (
                    slug, source_platform, native_id, project_name, description, program_overview,
                    out_of_scope_and_rules, prioritized_vulnerabilities, website_url, github_url,
                    logo_url, launch_date, updated_date, end_date, evaluation_end_date,
                    max_bounty_usd, rewards_pool, rewards_token, invite_only, kyc_required,
                    kyc_type, immunefi_standard, primacy_model, scaling_percentage, scaling_base_metric,
                    exploit_window_seconds, known_issue_assurance, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    slug, platform, native_id, proj_name, desc, overview,
                    rules, prioritized, web_url, github_url,
                    logo, incoming_project.get("launch_date"), incoming_project.get("updated_date"), incoming_project.get("end_date"), incoming_project.get("evaluation_end_date"),
                    p_max, rewards_pool, rewards_token, invite_only, kyc_req,
                    kyc_type, immunefi_std, primacy_model, scaling_pct, "TVL",
                    3600, 0, raw_json_str
                ))

                cursor.execute("DELETE FROM assets WHERE project_slug = ?", (slug,))
                for a in incoming_assets:
                    identifier = a.get("asset_identifier") or a.get("identifier") or a.get("url") or "Asset"
                    a_url = a.get("url")
                    a_type = a.get("type") or a.get("asset_type") or "contract"
                    a_desc = a.get("description") or a.get("scope_description")
                    safe_harbor = 1 if a.get("is_safe_harbor") in (1, "1", True) else 0
                    cursor.execute("""
                    INSERT INTO assets (project_slug, asset_identifier, url, type, description, is_safe_harbor)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (slug, identifier, a_url, a_type, a_desc, safe_harbor))

        print(f"[+] Direct Insertion: Registered new program discovery '{slug}' ({platform}) into projects & assets.")
        if should_close_conn:
            conn.close()
        return []

    mutations = []

    if db_proj:
        # Check 1: Max Reward Drift
        inc_max = safe_int(incoming_project.get("max_bounty_usd") if incoming_project.get("max_bounty_usd") is not None else incoming_project.get("max_bounty"))
        old_max = safe_int(db_proj.get("max_bounty_usd"))
        if inc_max is not None and old_max is not None and inc_max != old_max:
            inc_fmt = f"${inc_max:,}"
            old_fmt = f"${old_max:,}"
            change_type = "increased" if inc_max > old_max else "decreased"
            token_suffix = incoming_project.get("rewards_token") or db_proj.get("rewards_token") or "USDC"
            msg = f"MUTATION DETECTED [{platform}_{slug}]: Max Bounty {change_type} from {old_fmt} to {inc_fmt} {token_suffix}."
            mutations.append({
                "project_slug": slug,
                "source_platform": platform,
                "mutation_type": "MAX_REWARD_DRIFT",
                "field_name": "max_bounty_usd",
                "old_value": str(old_max),
                "new_value": str(inc_max),
                "log_message": msg
            })

        # Check 2: Legal/Access Drift (primacy_model, kyc_required, invite_only)
        for legal_field in ["primacy_model", "kyc_required", "invite_only"]:
            if legal_field in incoming_project and incoming_project[legal_field] is not None:
                inc_val = str(incoming_project[legal_field])
                old_val = str(db_proj.get(legal_field) if db_proj.get(legal_field) is not None else "")
                if inc_val != old_val:
                    msg = f"MUTATION DETECTED [{platform}_{slug}]: Legal Drift updated {legal_field} from '{old_val}' to '{inc_val}'."
                    mutations.append({
                        "project_slug": slug,
                        "source_platform": platform,
                        "mutation_type": "LEGAL_ACCESS_DRIFT",
                        "field_name": legal_field,
                        "old_value": old_val,
                        "new_value": inc_val,
                        "log_message": msg
                    })

        # Check 3: Structural Scope Drift (Order-Agnostic Comparison)
        cursor.execute("SELECT * FROM assets WHERE project_slug = ?", (slug,))
        db_assets = [dict(r) for r in cursor.fetchall()]
        
        db_asset_map = {}
        for a in db_assets:
            key = normalize_asset_key(a.get("asset_identifier"), a.get("type"), a.get("url"))
            if key[0]:
                db_asset_map[key] = a

        inc_asset_map = {}
        for a in incoming_assets:
            a_ident = a.get("asset_identifier") or a.get("identifier") or a.get("url")
            a_type = a.get("type") or a.get("asset_type")
            a_url = a.get("url")
            key = normalize_asset_key(a_ident, a_type, a_url)
            if key[0]:
                inc_asset_map[key] = a

        added_keys = set(inc_asset_map.keys()) - set(db_asset_map.keys())
        removed_keys = set(db_asset_map.keys()) - set(inc_asset_map.keys())

        if added_keys or removed_keys:
            added_names = [k[0] for k in added_keys]
            removed_names = [k[0] for k in removed_keys]
            details = []
            if added_names:
                details.append(f"Added assets: {', '.join(added_names)}")
            if removed_names:
                details.append(f"Removed assets: {', '.join(removed_names)}")
            detail_str = "; ".join(details)
            msg = f"MUTATION DETECTED [{platform}_{slug}]: Structural Scope Drift updated scope assets ({detail_str})."
            mutations.append({
                "project_slug": slug,
                "source_platform": platform,
                "mutation_type": "STRUCTURAL_SCOPE_DRIFT",
                "field_name": "assets",
                "old_value": f"{len(db_asset_map)} assets",
                "new_value": f"{len(inc_asset_map)} assets",
                "log_message": msg
            })

    with DB_LOCK:
        with conn:
            # 1. Commit mutation logs
            for m in mutations:
                cursor.execute("""
                INSERT INTO bounty_state_mutations (
                    project_slug, source_platform, mutation_type, field_name, old_value, new_value, log_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    m["project_slug"], m["source_platform"], m["mutation_type"],
                    m["field_name"], m["old_value"], m["new_value"], m["log_message"]
                ))
                print(m["log_message"])

            # 2. Automated Queue Eviction: If any mutation detected, reset preflight_queue entries for this project to PENDING
            if mutations:
                cursor.execute("""
                UPDATE preflight_queue
                SET dispatch_status = 'PENDING', error_log = NULL
                WHERE source_identifier = ? OR source_identifier LIKE '%' || ? || '%'
                """, (slug, slug))
                evicted_count = cursor.rowcount
                if evicted_count > 0:
                    print(f"[+] Automated Queue Eviction: Reset {evicted_count} queue item(s) for '{slug}' to 'PENDING'.")

            # 3. Update project row with fresh incoming values
            if db_proj:
                p_max = safe_int(incoming_project.get("max_bounty_usd") if incoming_project.get("max_bounty_usd") is not None else incoming_project.get("max_bounty")) or db_proj.get("max_bounty_usd")
                p_primacy = incoming_project.get("primacy_model") or db_proj.get("primacy_model")
                p_kyc = safe_int(incoming_project.get("kyc_required")) if incoming_project.get("kyc_required") is not None else db_proj.get("kyc_required")
                p_invite = safe_int(incoming_project.get("invite_only")) if incoming_project.get("invite_only") is not None else db_proj.get("invite_only")
                
                cursor.execute("""
                UPDATE projects
                SET max_bounty_usd = ?, primacy_model = ?, kyc_required = ?, invite_only = ?, updated_date = CURRENT_TIMESTAMP
                WHERE slug = ?
                """, (p_max, p_primacy, p_kyc, p_invite, slug))

                # Update assets if structural drift occurred
                scope_mutations = [m for m in mutations if m["mutation_type"] == "STRUCTURAL_SCOPE_DRIFT"]
                if scope_mutations:
                    cursor.execute("DELETE FROM assets WHERE project_slug = ?", (slug,))
                    for a in incoming_assets:
                        identifier = a.get("asset_identifier") or a.get("identifier") or a.get("url") or "Asset"
                        a_url = a.get("url")
                        a_type = a.get("type") or a.get("asset_type") or "contract"
                        a_desc = a.get("description") or a.get("scope_description")
                        safe_harbor = 1 if a.get("is_safe_harbor") in (1, "1", True) else 0
                        cursor.execute("""
                        INSERT INTO assets (project_slug, asset_identifier, url, type, description, is_safe_harbor)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """, (slug, identifier, a_url, a_type, a_desc, safe_harbor))

    if should_close_conn:
        conn.close()

    return mutations

def run_differential_ingestion_pass() -> dict:
    """
    Executes a synchronous ingestion differential pass across target source databases
    (cbb.db, hbb.db, ibb.db, sbb.db), sequentially inspecting network payload states
    and triggering state-differential checks against unified_bug_bounties.db.
    """
    init_unified_db()
    
    if os.path.exists("/app"):
        DB_DIR = Path("/app/data_store")
    else:
        DB_DIR = Path("C:/users/david")

    source_configs = [
        ("cbb.db", "cantina"),
        ("hbb.db", "hackenproof"),
        ("ibb.db", "immunefi"),
        ("sbb.db", "sherlock")
    ]

    total_mutations_detected = 0
    all_mutations = []

    conn = get_unified_connection()

    for db_filename, platform_name in source_configs:
        db_path = DB_DIR / db_filename
        if not db_path.exists():
            continue

        try:
            s_conn = sqlite3.connect(str(db_path))
            s_conn.row_factory = sqlite3.Row
            s_cursor = s_conn.cursor()

            s_tables = [r[0] for r in s_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'").fetchall()]
            if "projects" not in s_tables:
                s_conn.close()
                continue

            s_cursor.execute("SELECT * FROM projects")
            projects = [dict(r) for r in s_cursor.fetchall()]

            for p in projects:
                slug = str(p.get("slug") or p.get("id") or p.get("native_id") or "").strip()
                if not slug:
                    continue

                p["source_platform"] = platform_name
                
                # Fetch child assets for incoming payload comparison
                assets = []
                if "assets" in s_tables:
                    s_cursor.execute("SELECT * FROM assets WHERE project_slug = ?", (slug,))
                    assets = [dict(r) for r in s_cursor.fetchall()]

                muts = compare_and_apply_project_differential(p, assets, conn=conn)
                if muts:
                    total_mutations_detected += len(muts)
                    all_mutations.extend(muts)

            s_conn.close()
        except Exception as e:
            print(f"[-] Error scanning source DB {db_filename}: {e}")

    conn.close()
    return {"mutations_count": total_mutations_detected, "mutations": all_mutations}

async def run_state_differential_tracker_loop(interval_seconds: float = 60.0):
    """
    Non-blocking asynchronous background tracking loop that offloads synchronous DB scanning
    to a worker thread via asyncio.to_thread to prevent blocking the main event loop.
    """
    print(f"[+] Starting Async Live Bounty State-Differential Tracker Loop (Interval: {interval_seconds}s)...")
    while True:
        try:
            res = await asyncio.to_thread(run_differential_ingestion_pass)
            if res.get("mutations_count", 0) > 0:
                print(f"[+] Tracker pass complete: {res['mutations_count']} mutation(s) detected and processed.")
        except Exception as e:
            print(f"[-] Error in state differential tracker loop: {e}")

        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    asyncio.run(run_state_differential_tracker_loop(10.0))
