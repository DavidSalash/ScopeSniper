import sqlite3
import re
from typing import Dict, Any, List, Optional, Tuple
from core.database import DB_LOCK

def slugify(text: str) -> str:
    """Converts a raw string tag into a canonical snake_case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text.strip("_")

# Baseline Canonical Taxonomy Architecture (Levels 1 to 4)
CANONICAL_TAXONOMY_NODES = [
    # Level 1: Domains
    {"slug": "smart_contract", "name": "Smart Contract Security", "parent_path": None, "depth": 1, "description": "Core smart contract implementation and language-level vulnerabilities."},
    {"slug": "defi_protocol", "name": "DeFi Protocol Logic", "parent_path": None, "depth": 1, "description": "Economic primitives, liquidity pools, oracles, and financial logic vulnerabilities."},
    {"slug": "web3_infrastructure", "name": "Web3 Infrastructure", "parent_path": None, "depth": 1, "description": "Cross-chain bridges, indexers, RPCs, and validator node vulnerabilities."},
    {"slug": "access_and_governance", "name": "Access Control & Governance", "parent_path": None, "depth": 1, "description": "Privilege management, multisig configurations, and DAO voting vulnerabilities."},

    # Level 2: Classes under smart_contract
    {"slug": "reentrancy", "name": "Reentrancy", "parent_path": "smart_contract", "depth": 2, "description": "State manipulation via unexpected external control flow callbacks."},
    {"slug": "external_call_hazards", "name": "External Call Hazards", "parent_path": "smart_contract", "depth": 2, "description": "Unchecked external call returns, delegatecall injection, or call-depth exhaustion."},
    {"slug": "math_and_precision", "name": "Math & Precision", "parent_path": "smart_contract", "depth": 2, "description": "Overflow, underflow, rounding down/up, or loss of precision in arithmetic calculations."},
    {"slug": "signature_and_auth", "name": "Signature & Cryptography", "parent_path": "smart_contract", "depth": 2, "description": "Signature malleability, replay attacks, ecrecover zero address, or weak PRNG."},

    # Level 2: Classes under defi_protocol
    {"slug": "oracle_manipulation", "name": "Oracle Manipulation", "parent_path": "defi_protocol", "depth": 2, "description": "Spot price manipulation, stale TWAP reads, or lack of slippage/min-out checks."},
    {"slug": "logic_and_state_machine", "name": "Logic & State Machine", "parent_path": "defi_protocol", "depth": 2, "description": "Inconsistent state transitions, order of operations, or flash loan balance checks."},
    {"slug": "tokenomics_and_liquidity", "name": "Tokenomics & Liquidity", "parent_path": "defi_protocol", "depth": 2, "description": "First-deposit share price inflation, fee-on-transfer miscalculations, or reward dilution."},

    # Level 2: Classes under access_and_governance
    {"slug": "access_control", "name": "Access Control", "parent_path": "access_and_governance", "depth": 2, "description": "Missing initializer guards, unprotected admin functions, or role privilege escalation."},

    # Level 3: Patterns under smart_contract/reentrancy
    {"slug": "read_only", "name": "Read-Only Reentrancy", "parent_path": "smart_contract/reentrancy", "depth": 3, "description": "View function state desynchronization during intermediate execution phase."},
    {"slug": "cross_contract", "name": "Cross-Contract Reentrancy", "parent_path": "smart_contract/reentrancy", "depth": 3, "description": "Reentrancy across separate contracts sharing state or balances."},

    # Level 3: Patterns under defi_protocol/oracle_manipulation
    {"slug": "flash_loan_spot", "name": "Flash Loan Spot Oracle", "parent_path": "defi_protocol/oracle_manipulation", "depth": 3, "description": "Instantaneous AMM liquidity pool price skewing within a single transaction block."},
    {"slug": "stale_read", "name": "Stale Price Feed Read", "parent_path": "defi_protocol/oracle_manipulation", "depth": 3, "description": "Unchecked Chainlink updatedAt or missing threshold heartbeat verification."},

    # Level 3: Patterns under defi_protocol/tokenomics_and_liquidity
    {"slug": "first_deposit", "name": "First Deposit Vault Inflation", "parent_path": "defi_protocol/tokenomics_and_liquidity", "depth": 3, "description": "ERC-4626 share ratio manipulation via direct token transfer on zero supply."},
    {"slug": "rounding", "name": "Rounding Direction Exploit", "parent_path": "defi_protocol/tokenomics_and_liquidity", "depth": 3, "description": "Protocol rounding in favor of user rather than protocol on withdraw/redeem."},

    # Level 3: Patterns under access_and_governance/access_control
    {"slug": "initializer", "name": "Unprotected Initializer", "parent_path": "access_and_governance/access_control", "depth": 3, "description": "Implementation contract initialization failure enabling ownership takeover."},
    {"slug": "privilege_escalation", "name": "Privilege Escalation", "parent_path": "access_and_governance/access_control", "depth": 3, "description": "Unauthorized role grant or missing modifier check on administrative setter."},

    # Level 3: Patterns under smart_contract/math_and_precision
    {"slug": "precision_loss", "name": "Division Before Multiplication", "parent_path": "smart_contract/math_and_precision", "depth": 3, "description": "Truncation errors leading to zero or reduced fee and yield calculations."},

    # Level 3: Patterns under smart_contract/signature_and_auth
    {"slug": "sig_replay", "name": "Signature Replay", "parent_path": "smart_contract/signature_and_auth", "depth": 3, "description": "Missing nonces, domain separator, or chain ID in signed authorization messages."},

    # Level 4: Mechanisms under smart_contract/reentrancy/read_only
    {"slug": "view_desync", "name": "View State Desync", "parent_path": "smart_contract/reentrancy/read_only", "depth": 4, "description": "State manipulation during external callback causes stale price reading in dependent contract."},
    {"slug": "callback_state_lag", "name": "Callback State Lag", "parent_path": "smart_contract/reentrancy/read_only", "depth": 4, "description": "ERC-721/ERC-1155 token transfer callback triggers before total reserves update."},

    # Level 4: Mechanisms under smart_contract/reentrancy/cross_contract
    {"slug": "shared_vault_callback", "name": "Shared Vault Callback", "parent_path": "smart_contract/reentrancy/cross_contract", "depth": 4, "description": "Cross-contract balance mismatch during collateral withdrawal callback."},

    # Level 4: Mechanisms under defi_protocol/oracle_manipulation/flash_loan_spot
    {"slug": "balanceof_ratio_skew", "name": "BalanceOf Ratio Skew", "parent_path": "defi_protocol/oracle_manipulation/flash_loan_spot", "depth": 4, "description": "Direct balance query without time-weighted averaging allows flash swap manipulation."},
    {"slug": "reserves_manipulation", "name": "Reserves Ratio Manipulation", "parent_path": "defi_protocol/oracle_manipulation/flash_loan_spot", "depth": 4, "description": "Sync or skim function invocation skews price calculation ratio."},

    # Level 4: Mechanisms under defi_protocol/tokenomics_and_liquidity/first_deposit
    {"slug": "vault_donation_attack", "name": "Vault Direct Donation Attack", "parent_path": "defi_protocol/tokenomics_and_liquidity/first_deposit", "depth": 4, "description": "Direct token transfer inflates share price forcing subsequent depositor loss to zero shares."},

    # Level 4: Mechanisms under access_and_governance/access_control/initializer
    {"slug": "proxy_uninitialized", "name": "Proxy Implementation Uninitialized", "parent_path": "access_and_governance/access_control/initializer", "depth": 4, "description": "Logic contract left uninitialized allowing selfdestruct or delegatecall hijack."},

    # Level 4: Mechanisms under smart_contract/math_and_precision/precision_loss
    {"slug": "fee_truncation_to_zero", "name": "Fee Truncation to Zero", "parent_path": "smart_contract/math_and_precision/precision_loss", "depth": 4, "description": "Small transfer amount produces zero protocol fee due to integer division order."},

    # Level 4: Mechanisms under smart_contract/signature_and_auth/sig_replay
    {"slug": "cross_chain_permit_replay", "name": "Cross-Chain Permit Replay", "parent_path": "smart_contract/signature_and_auth/sig_replay", "depth": 4, "description": "ERC-2612 permit signature reused across chains lacking block.chainid check."}
]

def _resolve_table_prefix(cursor: sqlite3.Cursor) -> str:
    """Detects if vulnerability_taxonomy is in attached schema 'vuln' or default schema."""
    cursor.execute("PRAGMA database_list")
    dbs = [row[1] for row in cursor.fetchall()]
    if "vuln" in dbs:
        return "vuln."
    return ""

def seed_hybrid_vulnerability_taxonomy(conn: sqlite3.Connection) -> int:
    """
    Seeds baseline canonical 4-level taxonomy nodes into vulnerabilities.db
    and dynamically mines high-frequency tags from vulnerability_tags_index.
    Returns total count of seeded taxonomy nodes.
    """
    cursor = conn.cursor()
    table_prefix = _resolve_table_prefix(cursor)
    
    tax_table = f"{table_prefix}vulnerability_taxonomy"
    tags_table = f"{table_prefix}vulnerability_tags_index"

    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {tax_table} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        parent_id INTEGER REFERENCES vulnerability_taxonomy(id) ON DELETE CASCADE,
        path TEXT UNIQUE NOT NULL,
        depth INTEGER NOT NULL CHECK (depth BETWEEN 1 AND 4),
        description TEXT
    )
    """)

    path_to_id: Dict[str, int] = {}
    seeded_count = 0

    with DB_LOCK:
        # 1. Load existing taxonomy nodes
        cursor.execute(f"SELECT id, path FROM {tax_table}")
        for r in cursor.fetchall():
            path_to_id[r["path"]] = r["id"]

        # 2. Insert Canonical Hierarchy
        sorted_nodes = sorted(CANONICAL_TAXONOMY_NODES, key=lambda x: x["depth"])
        for node in sorted_nodes:
            parent_path = node["parent_path"]
            if parent_path is None:
                path = node["slug"]
                parent_id = None
            else:
                path = f"{parent_path}/{node['slug']}"
                parent_id = path_to_id.get(parent_path)

            if path not in path_to_id:
                cursor.execute(f"""
                INSERT OR IGNORE INTO {tax_table} (slug, name, parent_id, path, depth, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (node["slug"], node["name"], parent_id, path, node["depth"], node["description"]))
                
                cursor.execute(f"SELECT id FROM {tax_table} WHERE path = ?", (path,))
                row = cursor.fetchone()
                if row:
                    path_to_id[path] = row["id"]
                    seeded_count += 1
            else:
                cursor.execute(f"SELECT id FROM {tax_table} WHERE path = ?", (path,))
                row = cursor.fetchone()
                if row:
                    path_to_id[path] = row["id"]

        # 3. Dynamic Tag Frequency Mining
        try:
            cursor.execute(f"""
            SELECT tag, COUNT(*) as tag_count 
            FROM {tags_table} 
            GROUP BY tag 
            ORDER BY tag_count DESC 
            LIMIT 500
            """)
            mined_tags = cursor.fetchall()
            
            default_level2_parents = [
                ("reentrancy", "smart_contract/reentrancy"),
                ("oracle", "defi_protocol/oracle_manipulation"),
                ("access", "access_and_governance/access_control"),
                ("math", "smart_contract/math_and_precision"),
                ("signature", "smart_contract/signature_and_auth"),
                ("liquidity", "defi_protocol/tokenomics_and_liquidity")
            ]

            for row in mined_tags:
                tag_name = row["tag"]
                if not tag_name or len(tag_name) < 3:
                    continue

                tag_slug = slugify(tag_name)
                if not tag_slug:
                    continue

                matched_parent_path = "smart_contract/external_call_hazards"
                for kw, p_path in default_level2_parents:
                    if kw in tag_slug or kw in tag_name.lower():
                        matched_parent_path = p_path
                        break

                parent_id = path_to_id.get(matched_parent_path)
                if not parent_id:
                    continue

                parent_depth = 2
                if matched_parent_path.count("/") == 2:
                    parent_depth = 3
                elif matched_parent_path.count("/") == 1:
                    parent_depth = 2

                child_depth = parent_depth + 1
                if child_depth > 4:
                    continue

                mined_path = f"{matched_parent_path}/{tag_slug}"
                if mined_path not in path_to_id:
                    cursor.execute(f"""
                    INSERT OR IGNORE INTO {tax_table} (slug, name, parent_id, path, depth, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (tag_slug, tag_name.title(), parent_id, mined_path, child_depth, f"Mined pattern tag: {tag_name}"))
                    
                    cursor.execute(f"SELECT id FROM {tax_table} WHERE path = ?", (mined_path,))
                    r = cursor.fetchone()
                    if r:
                        path_to_id[mined_path] = r["id"]
                        seeded_count += 1
        except Exception:
            pass

        conn.commit()

    cursor.execute(f"SELECT COUNT(*) FROM {tax_table}")
    total_nodes = cursor.fetchone()[0]
    return total_nodes

if __name__ == "__main__":
    from core.database import get_vulnerabilities_connection
    conn = get_vulnerabilities_connection()
    count = seed_hybrid_vulnerability_taxonomy(conn)
    print(f"[+] Taxonomy seeder complete. Total nodes: {count}")
    conn.close()
