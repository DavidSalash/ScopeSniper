import sys
import os
import json
import time
from pathlib import Path

# Add project root to sys.path
WORKSPACE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from core.database import init_unified_db, get_unified_connection, DB_LOCK
from core.math_engine import get_target_profitability_matrix, calculate_expected_profitability_yield
from core.pipeline import stage_preflight_queue_item, process_single_queue_item, TOKEN_BUCKET_TIERS

def seed_sample_data():
    """Seeds sample bug bounty program projects, assets, and rewards into unified_bug_bounties.db."""
    conn = get_unified_connection()
    cursor = conn.cursor()
    with DB_LOCK:
        with conn:
            # 1. Projects
            projects = [
                ("aave-v3", "immunefi", "imm_001", "Aave V3 Protocol", "DeFi Money Market Protocol", "Full Scope", "Rules apply", "Flash Loan Attacks", "https://aave.com", "https://github.com/aave/aave-v3-core", "https://logo.png", "2023-01-01", "2026-01-01", None, None, 1000000, 5000000, "USDC", 0, 0, "none", 1, "impact", 10.0, "TVL", 3600, 1, '{"raw": true}'),
                ("morpho-blue", "cantina", "cnt_002", "Morpho Blue Core", "Lending Primitive", "Core Contracts", "Strict Scope", "Reentrancy", "https://morpho.org", "https://github.com/morpho-org/morpho-blue", "https://logo.png", "2023-05-01", "2026-05-01", None, None, 500000, 2000000, "ETH", 0, 1, "light", 0, "impact", 10.0, "TVL", 3600, 1, '{"raw": true}'),
                ("sherlock-vaults", "sherlock", "sh_003", "Sherlock Staking Pool", "Vault Insurance", "WETH Vaults", "Standard Rules", "Vault Drainage", "https://sherlock.xyz", "https://github.com/sherlock-protocol", "https://logo.png", "2023-08-01", "2026-08-01", None, None, 250000, 1000000, "USDC", 0, 0, "none", 0, "rules", 100.0, "TVL", 3600, 0, '{"raw": true}'),
                ("hackenproof-dex", "hackenproof", "hp_004", "HackenProof MultiDEX", "AMM Exchange", "Router & Factory", "Rules apply", "Price Manipulation", "https://hackenproof.com", "https://github.com/hackenproof/dex", "https://logo.png", "2024-01-01", "2026-01-01", None, None, 100000, 500000, "USDT", 1, 1, "full_aml", 0, "mixed", 100.0, "TVL", 3600, 0, '{"raw": true}')
            ]
            cursor.executemany("""
            INSERT OR REPLACE INTO projects (
                slug, source_platform, native_id, project_name, description, program_overview,
                out_of_scope_and_rules, prioritized_vulnerabilities, website_url, github_url,
                logo_url, launch_date, updated_date, end_date, evaluation_end_date,
                max_bounty_usd, rewards_pool, rewards_token, invite_only, kyc_required,
                kyc_type, immunefi_standard, primacy_model, scaling_percentage, scaling_base_metric,
                exploit_window_seconds, known_issue_assurance, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, projects)

            # 2. Rewards
            rewards = [
                ("aave-v3", "critical", "Direct theft of user funds", "In Scope", 50000, 1000000, 1, "direct", "Direct Theft of User Deposits", 10000, 0, "unprivileged"),
                ("morpho-blue", "critical", "Protocol Insolvency", "In Scope", 25000, 500000, 1, "direct", "Protocol Insolvency / Logic Flaw", 5000, 0, "unprivileged"),
                ("sherlock-vaults", "high", "Vault Drain", "In Scope", 10000, 250000, 1, "tier", "Yield Manipulation / Drain", 1000, 0, "moderator"),
                ("hackenproof-dex", "high", "Unsafe Token Drain", "In Scope", 5000, 100000, 1, "tier", "Unsafe Token Drain", 500, 0, "admin")
            ]
            cursor.executemany("""
            INSERT OR REPLACE INTO rewards (
                project_slug, severity_level, payout_description, asset_group_scope,
                min_reward, max_reward, poc_required, reward_model, impact_type_normalized,
                min_loss_threshold_usd, min_freeze_duration_seconds, privilege_escalation_tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rewards)

            # 3. Assets
            assets = [
                ("aave-v3", "Pool.sol", "https://github.com/aave/aave-v3-core/blob/main/contracts/protocol/pool/Pool.sol", "solidity", "Core Lending Pool", 1),
                ("aave-v3", "AToken.sol", "https://github.com/aave/aave-v3-core/blob/main/contracts/protocol/tokenization/AToken.sol", "solidity", "Yield Token", 1),
                ("morpho-blue", "Morpho.sol", "https://github.com/morpho-org/morpho-blue/blob/main/src/Morpho.sol", "solidity", "Morpho Blue Core Primitive", 1),
                ("sherlock-vaults", "Sherlock.sol", "https://github.com/sherlock-protocol/sherlock-v2/blob/main/contracts/Sherlock.sol", "solidity", "Sherlock Core Vault", 1),
                ("hackenproof-dex", "DEXRouter.sol", "https://github.com/hackenproof/dex/blob/main/contracts/DEXRouter.sol", "solidity", "AMM Router", 1)
            ]
            cursor.executemany("""
            INSERT INTO assets (project_slug, asset_identifier, url, type, description, is_safe_harbor)
            VALUES (?, ?, ?, ?, ?, ?)
            """, assets)

    conn.close()
    print("[+] Sample project and reward metadata successfully seeded.")

def seed_preflight_queue():
    """Seeds items into preflight_queue to test LLM batch processing and token classification."""
    sys_prompt = "You are an expert security audit parser."
    sample_items = [
        ("cbb", "aave_v3_core", "structural_extraction", sys_prompt, "contract AavePool { function flashLoan() public {} }"),
        ("hbb", "morpho_blue", "taxonomy_tagging", sys_prompt, "contract MorphoBlue { function supply() public {} }"),
        ("ibb", "sherlock_pool", "structural_extraction", sys_prompt, "contract SherlockPool { function withdraw() public {} }"),
        ("sbb", "hacken_dex", "taxonomy_tagging", sys_prompt, "contract Router { fontion swap() public {} } invalid input")
    ]

    for pool, identifier, req_type, sys_p, usr_p in sample_items:
        row_id = stage_preflight_queue_item(pool, identifier, req_type, sys_p, usr_p)
        print(f"[+] Staged preflight queue item #{row_id} [{pool} / {identifier}]")

def test_pipeline_execution():
    """Executes a single test dispatch pass over queued items."""
    print("[*] Dispatching pending preflight queue items...")
    conn = get_unified_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM preflight_queue WHERE dispatch_status = 'PENDING' LIMIT 5")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    for item in rows:
        res = process_single_queue_item(item)
        print(f"[+] Processed preflight queue item #{res['id']} -> Status: {res['status']}")

def run_verification_tests():
    """Runs automated verification unit tests over schemas and math formulas."""
    print("\n==================================================")
    print("RUNNING AUTOMATED SYSTEM & INTEGRATION VERIFICATIONS")
    print("==================================================")
    
    # Test 1: Math engine zero TVL clamping
    print("[1/4] Testing Math Engine clamping under near-zero TVL...")
    yield_zero = calculate_expected_profitability_yield(
        p_success=0.5, r_max=1000000, alpha=0.10, tvl=0.0, c_time=150.0, t_index=5.0
    )
    assert yield_zero == -750.0, f"Expected -750.0, got {yield_zero}"
    print("      [OK] Zero TVL clamping verified successfully.")
    # Test 2: Database connection and schema PRAGMA validation
    print("[2/4] Validating SQLite WAL mode & Schema foreign key integrity...")
    conn = get_unified_connection()
    cursor = conn.cursor()
    pragma_wal = cursor.execute("PRAGMA journal_mode;").fetchone()[0]
    assert pragma_wal.lower() == "wal", f"Expected WAL mode, got {pragma_wal}"
    cursor.execute("PRAGMA foreign_key_check;")
    fk_errors = cursor.fetchall()
    assert len(fk_errors) == 0, f"Foreign key violations detected: {fk_errors}"
    conn.close()
    print("      [OK] Database schema and WAL pooling verified zero PRAGMA errors.")

    # Test 3: Profitability Matrix Query
    print("[3/4] Testing Target Profitability Matrix scoring engine...")
    conn = get_unified_connection()
    matrix = get_target_profitability_matrix(conn)
    conn.close()
    assert len(matrix) > 0, "Profitability matrix returned 0 rows"
    print(f"      [OK] Matrix Engine successfully calculated {len(matrix)} scored targets.")

    # Test 4: Cascading Delete Verification
    print("[4/4] Verifying foreign key cascading deletes...")
    conn = get_unified_connection()
    cursor = conn.cursor()
    with DB_LOCK:
        with conn:
            cursor.execute("DELETE FROM projects WHERE slug = 'hackenproof-dex';")
    cursor.execute("SELECT COUNT(*) FROM rewards WHERE project_slug = 'hackenproof-dex';")
    count = cursor.fetchone()[0]
    assert count == 0, "Cascading delete failed on rewards table"
    conn.close()
    print("      [OK] Cascading deletes functioning as expected.")

    print("\n[SUCCESS] All stability assertions and integration tests PASSED!")

if __name__ == "__main__":
    init_unified_db()
    seed_sample_data()
    seed_preflight_queue()
    test_pipeline_execution()
    run_verification_tests()
