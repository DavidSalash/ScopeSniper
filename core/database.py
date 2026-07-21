import sqlite3
import threading
from pathlib import Path

DB_LOCK = threading.Lock()
DB_FILE = Path("/app/data_store/unified_bug_bounties.db") if Path("/app").exists() else Path("C:/users/david/unified_bug_bounties.db")
VULNERABILITIES_DB_FILE = Path("/app/data_store/vulnerabilities.db") if Path("/app").exists() else Path("C:/users/david/vulnerabilities.db")

def get_unified_connection():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def get_vulnerabilities_connection():
    VULNERABILITIES_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(VULNERABILITIES_DB_FILE), timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_vulnerabilities_db():
    conn = get_vulnerabilities_connection()
    cursor = conn.cursor()
    with conn:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS normalized_findings (
            id TEXT PRIMARY KEY,
            source_pool TEXT NOT NULL,
            protocol_name TEXT,
            title TEXT,
            content_markdown TEXT,
            severity TEXT,
            loss_usd REAL,
            file_paths TEXT,
            fix_commit TEXT,
            root_cause_keywords TEXT,
            raw_solidity_code TEXT,
            source_repo TEXT
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_pool ON normalized_findings (source_pool);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_severity ON normalized_findings (severity);")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vulnerability_tags_index (
            finding_id TEXT,
            source_pool TEXT,
            tag TEXT,
            PRIMARY KEY(finding_id, tag)
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_lookup ON vulnerability_tags_index(tag);")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vulnerability_taxonomy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES vulnerability_taxonomy(id) ON DELETE CASCADE,
            path TEXT UNIQUE NOT NULL,
            depth INTEGER NOT NULL CHECK (depth BETWEEN 1 AND 4),
            description TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS enriched_findings_metadata (
            finding_id TEXT PRIMARY KEY,
            taxonomy_path TEXT NOT NULL,
            vulnerability_summary TEXT,
            root_cause_explanation TEXT,
            attack_vector_steps_json TEXT,
            preconditions_json TEXT,
            impact_scope TEXT,
            affected_constructs_json TEXT,
            remediation_pattern TEXT,
            training_suitability_score REAL,
            training_suitability_reason TEXT,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(finding_id) REFERENCES normalized_findings(id) ON DELETE CASCADE,
            FOREIGN KEY(taxonomy_path) REFERENCES vulnerability_taxonomy(path)
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enrich_path ON enriched_findings_metadata(taxonomy_path);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enrich_impact ON enriched_findings_metadata(impact_scope);")

        # Dynamic migrations for missing columns in pre-existing DB schemas
        try:
            cursor.execute("ALTER TABLE enriched_findings_metadata ADD COLUMN training_suitability_score REAL;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE enriched_findings_metadata ADD COLUMN training_suitability_reason TEXT;")
        except sqlite3.OperationalError:
            pass
    conn.close()

def attach_vulnerabilities_db(conn: sqlite3.Connection) -> None:
    """
    Dynamically mounts the historical vulnerabilities tracking ledger ('vulnerabilities.db')
    as schema alias 'vuln' on the given active SQLite connection.
    Safely intercepts OperationalError if already attached in the active thread connection session.
    Enforces row factory mapping (conn.row_factory = sqlite3.Row).
    """
    init_vulnerabilities_db()
    conn.row_factory = sqlite3.Row
    resolved_path = str(VULNERABILITIES_DB_FILE).replace("\\", "/")
    try:
        conn.execute(f"ATTACH DATABASE '{resolved_path}' AS vuln;")
    except sqlite3.OperationalError as e:
        err_str = str(e).lower()
        if "already" in err_str and ("attached" in err_str or "in use" in err_str):
            pass
        else:
            raise e


def init_unified_db():
    conn = get_unified_connection()
    cursor = conn.cursor()
    with conn:
        # Master Program Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            slug TEXT PRIMARY KEY,
            source_platform TEXT NOT NULL CHECK (source_platform IN ('cantina', 'hackenproof', 'immunefi', 'sherlock')),
            native_id TEXT NOT NULL,
            project_name TEXT NOT NULL,
            description TEXT,
            program_overview TEXT,
            out_of_scope_and_rules TEXT,
            prioritized_vulnerabilities TEXT,
            website_url TEXT,
            github_url TEXT,
            logo_url TEXT,
            launch_date TEXT,
            updated_date TEXT,
            end_date TEXT,
            evaluation_end_date TEXT,
            max_bounty_usd INTEGER,
            rewards_pool INTEGER,
            rewards_token TEXT,
            invite_only INTEGER DEFAULT 0 CHECK (invite_only IN (0, 1)),
            kyc_required INTEGER DEFAULT 0 CHECK (kyc_required IN (0, 1)),
            kyc_type TEXT DEFAULT 'none' CHECK (kyc_type IN ('none', 'light', 'full_aml')),
            immunefi_standard INTEGER DEFAULT 0 CHECK (immunefi_standard IN (0, 1)),
            primacy_model TEXT DEFAULT 'rules' CHECK (primacy_model IN ('impact', 'rules', 'mixed')),
            scaling_percentage REAL,
            scaling_base_metric TEXT,
            exploit_window_seconds INTEGER DEFAULT 3600,
            known_issue_assurance INTEGER DEFAULT 0 CHECK (known_issue_assurance IN (0, 1)),
            raw_json TEXT NOT NULL
        )""")

        # Targets Boundary Assets
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT NOT NULL,
            asset_identifier TEXT,
            url TEXT,
            type TEXT NOT NULL,
            description TEXT,
            is_safe_harbor INTEGER CHECK (is_safe_harbor IN (0, 1, NULL)),
            FOREIGN KEY (project_slug) REFERENCES projects (slug) ON DELETE CASCADE
        )""")

        # Standardized Severity Matrix & Reward Constraints
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT NOT NULL,
            severity_level TEXT NOT NULL,
            payout_description TEXT,
            asset_group_scope TEXT,
            min_reward INTEGER,
            max_reward INTEGER,
            poc_required INTEGER CHECK (poc_required IN (0, 1, NULL)),
            reward_model TEXT,
            impact_type_normalized TEXT,
            min_loss_threshold_usd INTEGER DEFAULT 0,
            min_freeze_duration_seconds INTEGER DEFAULT 0,
            privilege_escalation_tier TEXT DEFAULT 'unprivileged' CHECK (privilege_escalation_tier IN ('unprivileged', 'moderator', 'admin', 'trusted_multisig')),
            FOREIGN KEY (project_slug) REFERENCES projects (slug) ON DELETE CASCADE
        )""")

        # Auxiliary Meta Tables
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS impacts (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT NOT NULL,
            native_id TEXT,
            type TEXT,
            severity TEXT,
            title TEXT,
            FOREIGN KEY (project_slug) REFERENCES projects (slug) ON DELETE CASCADE
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS known_issues (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT NOT NULL,
            native_id TEXT,
            link TEXT,
            description TEXT,
            last_updated_at TEXT,
            related_impact_in_scope TEXT,
            FOREIGN KEY (project_slug) REFERENCES projects (slug) ON DELETE CASCADE
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_metadata (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT NOT NULL,
            meta_key TEXT NOT NULL,
            meta_value TEXT NOT NULL,
            FOREIGN KEY (project_slug) REFERENCES projects (slug) ON DELETE CASCADE,
            UNIQUE(project_slug, meta_key, meta_value)
        )""")

        # Context Window Staging Queue for RTX 5090 Cluster Autopilot
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS preflight_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pool TEXT NOT NULL,
            source_identifier TEXT NOT NULL,
            request_type TEXT NOT NULL,
            system_prompt_payload TEXT NOT NULL,
            user_prompt_payload TEXT NOT NULL,
            refusal_prompt_payload TEXT,
            character_count INTEGER NOT NULL,
            estimated_tokens INTEGER NOT NULL,
            token_bucket_tier TEXT NOT NULL,
            dispatch_status TEXT DEFAULT 'PENDING' CHECK (dispatch_status IN ('PENDING', 'RUNNING', 'DISPATCHED', 'FAILED', 'INVALID', 'INVALID_INPUT', 'PROSE_REFUSAL', 'MALFORMED_JSON', 'SKIPPED_METADATA', 'NO CONTENT')),
            error_log TEXT,
            response_payload TEXT
        )""")

        # Differential Mutation Telemetry Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bounty_state_mutations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT NOT NULL,
            source_platform TEXT NOT NULL,
            mutation_type TEXT NOT NULL CHECK (mutation_type IN ('MAX_REWARD_DRIFT', 'STRUCTURAL_SCOPE_DRIFT', 'LEGAL_ACCESS_DRIFT')),
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            log_message TEXT NOT NULL,
            detected_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        # AST Metrics Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ast_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT NOT NULL,
            asset_identifier TEXT NOT NULL,
            total_functions INTEGER DEFAULT 0,
            max_loop_depth INTEGER DEFAULT 0,
            external_calls_count INTEGER DEFAULT 0,
            state_mutations_count INTEGER DEFAULT 0,
            scanned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE,
            UNIQUE(project_slug, asset_identifier)
        );""")

        # Performance Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ast_lookup ON ast_metrics (project_slug, asset_identifier);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_platform ON projects (source_platform);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_max_bounty ON projects (max_bounty_usd) WHERE max_bounty_usd IS NOT NULL;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assets_slug ON assets (project_slug, type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rewards_matrix ON rewards (project_slug, severity_level, max_reward);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meta_lookup ON project_metadata (meta_key, meta_value);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_status ON preflight_queue (dispatch_status, token_bucket_tier);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mutations_slug ON bounty_state_mutations (project_slug, detected_at);")

    print(f"[+] Unified Database initialized at: {DB_FILE}")

if __name__ == "__main__":
    init_unified_db()
