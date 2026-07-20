import os
import sys
import sqlite3
import json
from pathlib import Path

# Add project root to path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from core.database import init_unified_db, get_unified_connection, DB_LOCK
from core.pipeline import stage_preflight_queue_item

def run_full_source_ingestion():
    """
    Reads all projects, assets, rewards, impacts, and metadata from
    cbb.db, hbb.db, ibb.db, sbb.db and normalizes them into unified_bug_bounties.db.
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

    unified_conn = get_unified_connection()
    u_cursor = unified_conn.cursor()

    total_ingested = 0
    total_assets = 0
    total_rewards = 0
    total_queued = 0

    print("==================================================")
    print("STARTING FULL INGESTION FROM ALL SOURCE DATABASES")
    print("==================================================")

    for db_filename, platform_name in source_configs:
        db_path = DB_DIR / db_filename
        if not db_path.exists():
            print(f"[-] Database file not found: {db_path}")
            continue

        print(f"\n[+] Ingesting from {db_filename} (Platform: {platform_name})...")
        s_conn = sqlite3.connect(str(db_path))
        s_conn.row_factory = sqlite3.Row
        s_cursor = s_conn.cursor()

        # Check tables in source DB
        s_tables = [r[0] for r in s_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'").fetchall()]

        # Query projects
        s_cursor.execute("SELECT * FROM projects")
        projects = [dict(r) for r in s_cursor.fetchall()]

        for p in projects:
            slug = str(p.get("slug") or p.get("id") or "").strip()
            if not slug:
                continue

            native_id = str(p.get("id") or slug)
            proj_name = str(p.get("project") or p.get("title") or p.get("name") or slug).strip()
            desc = p.get("description") or p.get("program_overview") or p.get("main_content") or ""
            overview = p.get("program_overview") or desc
            rules = p.get("out_of_scope_and_rules") or ""
            prioritized = p.get("prioritized_vulnerabilities") or ""
            web_url = p.get("website_url")
            github_url = p.get("github_url")
            logo = p.get("logo") or p.get("logo_url")
            launch_date = p.get("launch_date")
            updated_date = p.get("updated_date")
            end_date = p.get("end_date")
            eval_end_date = p.get("evaluation_end_date")
            
            # Numeric parsing with fallbacks
            try:
                max_bounty = int(p.get("max_bounty")) if p.get("max_bounty") is not None else None
            except (ValueError, TypeError):
                max_bounty = None

            try:
                rewards_pool = int(p.get("rewards_pool")) if p.get("rewards_pool") is not None else None
            except (ValueError, TypeError):
                rewards_pool = None

            rewards_token = p.get("rewards_token") or "USDC"
            invite_only = 1 if p.get("invite_only") in (1, "1", True) else 0
            
            kyc_val = p.get("kyc")
            if kyc_val in (1, "1", True):
                kyc_req = 1
                kyc_type = "light"
            elif isinstance(kyc_val, str) and kyc_val.lower() in ("full", "full_aml"):
                kyc_req = 1
                kyc_type = "full_aml"
            else:
                kyc_req = 0
                kyc_type = "none"

            immunefi_std = 1 if p.get("immunefi_standard") in (1, "1", True) else 0

            # Primacy model detection
            ten_pct_rule = p.get("ten_percent_economic_rule") in (1, "1", True)
            if ten_pct_rule or platform_name in ("immunefi", "cantina"):
                primacy_model = "impact"
            else:
                primacy_model = "rules"

            scaling_pct = 10.0 if ten_pct_rule else 100.0
            raw_json_str = p.get("raw_json") or json.dumps(p, default=str)

            with DB_LOCK:
                with unified_conn:
                    u_cursor.execute("""
                    INSERT OR REPLACE INTO projects (
                        slug, source_platform, native_id, project_name, description, program_overview,
                        out_of_scope_and_rules, prioritized_vulnerabilities, website_url, github_url,
                        logo_url, launch_date, updated_date, end_date, evaluation_end_date,
                        max_bounty_usd, rewards_pool, rewards_token, invite_only, kyc_required,
                        kyc_type, immunefi_standard, primacy_model, scaling_percentage, scaling_base_metric,
                        exploit_window_seconds, known_issue_assurance, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        slug, platform_name, native_id, proj_name, desc, overview,
                        rules, prioritized, web_url, github_url,
                        logo, launch_date, updated_date, end_date, eval_end_date,
                        max_bounty, rewards_pool, rewards_token, invite_only, kyc_req,
                        kyc_type, immunefi_std, primacy_model, scaling_pct, "TVL",
                        3600, 1 if ten_pct_rule else 0, raw_json_str
                    ))

            total_ingested += 1

            # Ingest child assets if present
            if "assets" in s_tables:
                s_cursor.execute("SELECT * FROM assets WHERE project_slug = ?", (slug,))
                assets = [dict(r) for r in s_cursor.fetchall()]
                for a in assets:
                    identifier = a.get("asset_identifier") or a.get("url") or a.get("id") or "Asset"
                    a_url = a.get("url")
                    a_type = a.get("type") or "contract"
                    a_desc = a.get("description")
                    safe_harbor = 1 if a.get("is_safe_harbor") in (1, "1", True) else 0

                    with DB_LOCK:
                        with unified_conn:
                            u_cursor.execute("""
                            INSERT INTO assets (project_slug, asset_identifier, url, type, description, is_safe_harbor)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """, (slug, identifier, a_url, a_type, a_desc, safe_harbor))
                    total_assets += 1

            # Ingest child rewards if present
            if "rewards" in s_tables:
                s_cursor.execute("SELECT * FROM rewards WHERE project_slug = ?", (slug,))
                rewards = [dict(r) for r in s_cursor.fetchall()]
                for r in rewards:
                    severity = str(r.get("severity") or r.get("level") or "high").lower()
                    payout_desc = r.get("payout") or r.get("payout_description") or f"{severity.title()} Reward"
                    
                    try:
                        r_min = int(r.get("min_reward")) if r.get("min_reward") is not None else 0
                    except (ValueError, TypeError):
                        r_min = 0

                    try:
                        r_max = int(r.get("max_reward")) if r.get("max_reward") is not None else max_bounty or 0
                    except (ValueError, TypeError):
                        r_max = max_bounty or 0

                    poc_req = 1 if r.get("poc_required") in (1, "1", True) else 0
                    reward_model = r.get("reward_model") or "direct"
                    impact_type = r.get("impact_type_normalized") or r.get("asset_type") or "Smart Contract Flaw"

                    with DB_LOCK:
                        with unified_conn:
                            u_cursor.execute("""
                            INSERT INTO rewards (
                                project_slug, severity_level, payout_description, asset_group_scope,
                                min_reward, max_reward, poc_required, reward_model, impact_type_normalized,
                                min_loss_threshold_usd, min_freeze_duration_seconds, privilege_escalation_tier
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                slug, severity, payout_desc, "In Scope",
                                r_min, r_max, poc_req, reward_model, impact_type,
                                0, 0, "unprivileged"
                            ))
                    total_rewards += 1

            # Enqueue preflight queue items for structured LLM parsing
            if len(desc) > 50:
                stage_preflight_queue_item(
                    source_pool=platform_name,
                    source_identifier=slug,
                    request_type="structural_extraction",
                    system_prompt="You are an expert security researcher and smart contract audit parser.",
                    user_prompt=f"Extract structured parameters for project {proj_name}:\n\n{desc[:1500]}"
                )
                total_queued += 1

        s_conn.close()

    unified_conn.close()

    print("\n==================================================")
    print(f"INGESTION COMPLETE SUMMARY:")
    print(f"  Total Projects Ingested: {total_ingested}")
    print(f"  Total Child Assets Ingested: {total_assets}")
    print(f"  Total Rewards Matrix Rows Ingested: {total_rewards}")
    print(f"  Total Preflight Queue Jobs Enqueued: {total_queued}")
    print("==================================================")

if __name__ == "__main__":
    run_full_source_ingestion()
