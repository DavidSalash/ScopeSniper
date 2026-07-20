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
        res = process_single_queue_item(item, timeout=1.0)
        print(f"[+] Processed preflight queue item #{res['id']} -> Status: {res['status']}")

def seed_empirical_vulnerabilities_data(conn):
    """Explicitly seeds empirical mock data into the attached vuln database tables for verification."""
    from core.database import attach_vulnerabilities_db
    attach_vulnerabilities_db(conn)
    cursor = conn.cursor()
    
    # Explicitly ensure target schema structures exist on fresh environment setups
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vuln.normalized_findings (
        id TEXT PRIMARY KEY, source_pool TEXT, protocol_name TEXT, title TEXT, severity TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vuln.vulnerability_tags_index (
        finding_id TEXT, source_pool TEXT, tag TEXT, PRIMARY KEY(finding_id, tag)
    )""")
    
    # 1. Seed normalized_findings if needed
    cursor.execute("SELECT COUNT(*) FROM vuln.normalized_findings")
    count_findings = cursor.fetchone()[0]
    if count_findings == 0:
        cursor.execute("""
        INSERT INTO vuln.normalized_findings (id, source_pool, protocol_name, title, severity)
        VALUES ('f1', 'test_pool', 'Aave V3', 'Flash Loan Bug', 'high'),
               ('f2', 'test_pool', 'Morpho', 'Reentrancy Bug', 'critical')
        """)
        
    # 2. Seed vulnerability_tags_index with tag counts for project rewards
    tags = [
        ("f1", "test_pool", "Direct Theft of User Deposits"),
        ("f1", "test_pool", "Direct Theft of User Deposits"),
        ("f2", "test_pool", "Protocol Insolvency / Logic Flaw")
    ]
    cursor.executemany("""
    INSERT OR IGNORE INTO vuln.vulnerability_tags_index (finding_id, source_pool, tag)
    VALUES (?, ?, ?)
    """, tags)

def run_verification_tests():
    """Runs automated verification unit tests over schemas, cross-database joins, math formulas, and DeFiLlama ingestion client."""
    print("\n==================================================")
    print("RUNNING AUTOMATED SYSTEM & INTEGRATION VERIFICATIONS")
    print("==================================================")
    
    from core.database import attach_vulnerabilities_db
    from core.math_engine import fetch_defillama_tvl_cache
    
    # Test Pass 1: Confirm ATTACH DATABASE routes resolve without throwing OperationalError path exceptions
    print("[1/8] Test Pass 1: Validating ATTACH DATABASE path resolution...")
    conn = get_unified_connection()
    try:
        attach_vulnerabilities_db(conn)
        print("      [OK] ATTACH DATABASE mounted 'vuln' schema without OperationalError path exceptions.")
    except Exception as e:
        raise AssertionError(f"ATTACH DATABASE failed with exception: {e}")
        
    # Seed empirical data for verification tests
    seed_empirical_vulnerabilities_data(conn)

    # Test Pass 2: Verify cross-database joins executing over vuln return valid numerical counts > 0
    print("[2/8] Test Pass 2: Verifying cross-database queries over vuln tables return counts > 0...")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vuln.normalized_findings")
    total_findings = cursor.fetchone()[0]
    assert total_findings > 0, f"Expected vuln.normalized_findings count > 0, got {total_findings}"
    
    cursor.execute("SELECT COUNT(*) FROM vuln.vulnerability_tags_index")
    total_tags = cursor.fetchone()[0]
    assert total_tags > 0, f"Expected vuln.vulnerability_tags_index count > 0, got {total_tags}"
    print(f"      [OK] Cross-database queries verified (Total findings: {total_findings}, Tag indices: {total_tags}).")

    # Test Pass 3: Assert calculated expected_profitability_yield values fluctuate dynamically across target rows
    print("[3/8] Test Pass 3: Verifying dynamic target profitability matrix yield variance...")
    matrix = get_target_profitability_matrix(conn)
    assert len(matrix) >= 2, f"Expected at least 2 scored targets, got {len(matrix)}"
    
    yields = [row["expected_profitability_yield"] for row in matrix]
    success_probs = [row["success_probability"] for row in matrix]
    
    # Ensure yields fluctuate across rows rather than returning static identical values
    unique_yields = set(yields)
    assert len(unique_yields) > 1, f"Yield values did not fluctuate dynamically across rows: {yields}"
    print(f"      [OK] Matrix yield metrics fluctuate dynamically across target rows (Yields: {yields}).")

    # Test Pass 4: Cascading Delete & DB Schema Health
    print("[4/8] Test Pass 4: Verifying foreign key cascading deletes & PRAGMA health...")
    pragma_wal = cursor.execute("PRAGMA journal_mode;").fetchone()[0]
    assert pragma_wal.lower() == "wal", f"Expected WAL mode, got {pragma_wal}"
    
    with DB_LOCK:
        with conn:
            cursor.execute("DELETE FROM projects WHERE slug = 'hackenproof-dex';")
    cursor.execute("SELECT COUNT(*) FROM rewards WHERE project_slug = 'hackenproof-dex';")
    count = cursor.fetchone()[0]
    assert count == 0, "Cascading delete failed on rewards table"
    print("      [OK] Foreign key cascading deletes and database PRAGMA integrity verified.")

    # Test Pass 5: API Reachability & DeFiLlama Ingestion Client Handshake
    print("[5/8] Test Pass 5: Validating DeFiLlama live REST client API reachability...")
    tvl_cache = fetch_defillama_tvl_cache()
    assert isinstance(tvl_cache, dict), "Expected TVL cache to be a dictionary object"
    assert len(tvl_cache) > 0, "Expected live DeFiLlama TVL cache lookup map to contain entries"
    print(f"      [OK] DeFiLlama REST client successfully ingested live protocols (Mapped keys count: {len(tvl_cache)}).")

    # Test Pass 6: Resilience & Dropout Timeout Drop Checking
    print("[6/8] Test Pass 6: Verifying network error resilience and socket drop timeout handling...")
    fallback_cache = fetch_defillama_tvl_cache(endpoint="http://10.255.255.1:9999/protocols", timeout=1.0)
    assert isinstance(fallback_cache, dict), "Fallback cache must return a valid dictionary on network timeout drop"
    print("      [OK] Network connection timeout intercepted gracefully; engine returned cached/fallback map without crashing.")

    # Test Pass 7: Data-Driven Yield Variance & On-Chain TVL Scaling
    print("[7/8] Test Pass 7: Verifying data-driven yield variance and live TVL reward scaling...")
    live_matrix = get_target_profitability_matrix(conn)
    matrix_by_slug = {r["slug"]: r for r in live_matrix}
    
    aave_row = matrix_by_slug.get("aave-v3")
    morpho_row = matrix_by_slug.get("morpho-blue")
    sherlock_row = matrix_by_slug.get("sherlock-vaults")
    
    assert aave_row is not None and morpho_row is not None, "Expected Aave V3 and Morpho Blue in scored matrix"
    assert aave_row["tvl_applied"] > 5_000_000.0, f"Expected Aave live TVL > fallback 5M baseline, got {aave_row['tvl_applied']}"
    assert morpho_row["tvl_applied"] > 5_000_000.0, f"Expected Morpho live TVL > fallback 5M baseline, got {morpho_row['tvl_applied']}"
    
    # Assert high-TVL protocol allows full stated max reward scaling up to its cap
    assert aave_row["calculated_real_reward"] > (sherlock_row["calculated_real_reward"] if sherlock_row else 0), \
        "Protocols with large active TVL must scale higher effective reward ceilings than smaller assets"
        
    print(f"      [OK] Economic TVL rules confirmed (Aave TVL: ${aave_row['tvl_applied']:,.2f}, Real Reward: ${aave_row['calculated_real_reward']:,.2f}).")

    # Test Pass 8: State Differential Validation
    print("[8/8] Test Pass 8: Verifying state differential engine, mutation logging, and queue evictions...")
    from core.tracker import compare_and_apply_project_differential
    
    cursor = conn.cursor()
    with DB_LOCK:
        with conn:
            cursor.execute("""
            INSERT OR REPLACE INTO projects (
                slug, source_platform, native_id, project_name, description,
                max_bounty_usd, primacy_model, kyc_required, invite_only, raw_json
            ) VALUES ('mock-protocol', 'immunefi', 'mock_01', 'Mock Protocol', 'Test Desc', 1000000, 'impact', 0, 0, '{}')
            """)
            cursor.execute("DELETE FROM assets WHERE project_slug = 'mock-protocol'")
            cursor.execute("""
            INSERT INTO assets (project_slug, asset_identifier, url, type, description, is_safe_harbor)
            VALUES ('mock-protocol', 'mock_contract_v1.sol', 'https://github.com/mock/v1.sol', 'solidity', 'v1 core', 1)
            """)
            
            cursor.execute("""
            INSERT INTO preflight_queue (
                source_pool, source_identifier, request_type, system_prompt_payload, user_prompt_payload,
                character_count, estimated_tokens, token_bucket_tier, dispatch_status
            ) VALUES ('immunefi', 'mock-protocol', 'structural_extraction', 'sys', 'usr', 100, 25, 'less_than_1k', 'DISPATCHED')
            """)

    cursor.execute("SELECT COUNT(*) FROM bounty_state_mutations")
    initial_mutations_count = cursor.fetchone()[0]

    incoming_proj = {
        "slug": "mock-protocol",
        "source_platform": "immunefi",
        "max_bounty_usd": 2000000,
        "primacy_model": "impact",
        "kyc_required": 0,
        "invite_only": 0
    }
    incoming_assets = [
        {"asset_identifier": "mock_contract_v1.sol", "type": "solidity", "url": "https://github.com/mock/v1.sol"},
        {"asset_identifier": "mock_contract_v2.sol", "type": "solidity", "url": "https://github.com/mock/v2.sol"}
    ]

    detected_mutations = compare_and_apply_project_differential(incoming_proj, incoming_assets, conn=conn)

    cursor.execute("SELECT COUNT(*) FROM bounty_state_mutations")
    final_mutations_count = cursor.fetchone()[0]
    mutation_delta = final_mutations_count - initial_mutations_count

    assert mutation_delta >= 2, f"Expected scalar mutation count increase >= 2, got delta {mutation_delta}"
    
    mutation_types = [m["mutation_type"] for m in detected_mutations]
    assert "MAX_REWARD_DRIFT" in mutation_types, "Expected MAX_REWARD_DRIFT mutation to be detected"
    assert "STRUCTURAL_SCOPE_DRIFT" in mutation_types, "Expected STRUCTURAL_SCOPE_DRIFT mutation to be detected"

    cursor.execute("SELECT dispatch_status FROM preflight_queue WHERE source_identifier = 'mock-protocol'")
    q_row = cursor.fetchone()
    assert q_row is not None and q_row["dispatch_status"] == "PENDING", f"Expected preflight_queue status revert to 'PENDING', got '{q_row['dispatch_status'] if q_row else None}'"

    # Fresh Unrecognized Program Discovery Validation
    new_proj = {
        "slug": "unrecognized-fresh-protocol",
        "source_platform": "cantina",
        "project_name": "Unrecognized Fresh Protocol",
        "max_bounty_usd": 750000,
        "primacy_model": "impact",
        "kyc_required": 0,
        "invite_only": 0
    }
    new_assets = [
        {"asset_identifier": "FreshVault.sol", "type": "solidity", "url": "https://github.com/fresh/FreshVault.sol"}
    ]
    new_proj_mutations = compare_and_apply_project_differential(new_proj, new_assets, conn=conn)
    assert len(new_proj_mutations) == 0, "New program discovery should bypass mutation logging and return empty mutations list"

    cursor.execute("SELECT * FROM projects WHERE slug = 'unrecognized-fresh-protocol'")
    fresh_p_row = cursor.fetchone()
    assert fresh_p_row is not None and fresh_p_row["max_bounty_usd"] == 750000, "Unrecognized project was not safely inserted into projects table"

    cursor.execute("SELECT * FROM assets WHERE project_slug = 'unrecognized-fresh-protocol'")
    fresh_a_rows = cursor.fetchall()
    assert len(fresh_a_rows) == 1 and fresh_a_rows[0]["asset_identifier"] == "FreshVault.sol", "Unrecognized project asset was not safely inserted into assets table"

    # Stateful SSE Query Deduplication Check
    cursor.execute("SELECT id, log_message FROM bounty_state_mutations WHERE id > 0 ORDER BY id ASC LIMIT 10")
    sse_pass1 = cursor.fetchall()
    max_id_pass1 = max(r["id"] for r in sse_pass1) if sse_pass1 else 0

    cursor.execute("SELECT id, log_message FROM bounty_state_mutations WHERE id > ? ORDER BY id ASC LIMIT 10", (max_id_pass1,))
    sse_pass2 = cursor.fetchall()
    assert len(sse_pass2) == 0, "Stateful SSE query returned duplicate mutation feeds on subsequent pass"

    print("      [OK] State differential engine, new program ingestion path, mutation telemetry, and SSE deduplication verified.")
    conn.close()

    print("\n[SUCCESS] All stability assertions and empirical integration tests PASSED!")

if __name__ == "__main__":
    init_unified_db()
    seed_sample_data()
    seed_preflight_queue()
    test_pipeline_execution()
    run_verification_tests()

