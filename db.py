import sqlite3
import json
import os
import threading
from pathlib import Path

# Thread lock to synchronize SQLite batch insertions across worker threads
db_lock = threading.Lock()

# Route database path dynamically:
# Use container path if inside Docker, otherwise use local Windows path (outside Dropbox)
if os.path.exists("/app"):
    DB_FILE = Path("/app/data_store/vulnerabilities.db")
else:
    DB_FILE = Path("C:/users/david/vulnerabilities.db")

def get_connection():
    """Returns a connection to the SQLite database, ensuring directory exists."""
    os.makedirs(DB_FILE.parent, exist_ok=True)
    # timeout=60.0 instructs SQLite to wait for locks to clear instead of throwing database locked errors
    conn = sqlite3.connect(str(DB_FILE), timeout=60.0)
    # Enable WAL mode for high concurrency write/read performance
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    # Enable dict-like rows for easy mapping
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database and creates the unified findings table."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create the unified normalized schema table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS normalized_findings (
        id TEXT PRIMARY KEY,
        source_pool TEXT NOT NULL,
        protocol_name TEXT,
        title TEXT,
        content_markdown TEXT,
        severity TEXT,
        loss_usd REAL,
        file_paths TEXT, -- JSON-serialized list of paths
        fix_commit TEXT,
        root_cause_keywords TEXT -- JSON-serialized list of keywords
    )
    """)
    
    # Create indexes for performance optimization
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_pool ON normalized_findings (source_pool);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_severity ON normalized_findings (severity);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_loss ON normalized_findings (loss_usd) WHERE loss_usd IS NOT NULL;")

    # Create vulnerability_tags_index table and its index
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vulnerability_tags_index (
        finding_id TEXT,
        source_pool TEXT,
        tag TEXT,
        PRIMARY KEY(finding_id, tag)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_lookup ON vulnerability_tags_index(tag);")

    # Self-healing Schema Migration: PRAGMA table_info to verify and safely alter table
    cursor.execute("PRAGMA table_info(normalized_findings)")
    columns = [row["name"] for row in cursor.fetchall()]
    
    if "raw_solidity_code" not in columns:
        try:
            cursor.execute("ALTER TABLE normalized_findings ADD COLUMN raw_solidity_code TEXT")
            print("Successfully added column 'raw_solidity_code' to normalized_findings table.")
        except Exception as e:
            print(f"Error adding column 'raw_solidity_code': {e}")
            
    if "source_repo" not in columns:
        try:
            cursor.execute("ALTER TABLE normalized_findings ADD COLUMN source_repo TEXT")
            print("Successfully added column 'source_repo' to normalized_findings table.")
        except Exception as e:
            print(f"Error adding column 'source_repo': {e}")
            
    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_FILE}")

def insert_findings_batch(findings_list):
    """
    Inserts a batch of normalized findings in a single transaction for maximum throughput.
    Uses thread lock to prevent SQLite busy/locking conflicts under high concurrency.
    """
    if not findings_list:
        return
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            with conn:
                for finding_data in findings_list:
                    file_paths_str = json.dumps(finding_data.get("file_paths", []))
                    keywords_str = json.dumps(finding_data.get("root_cause_keywords", []))
                    
                    cursor.execute("""
                    INSERT OR REPLACE INTO normalized_findings (
                        id, source_pool, protocol_name, title, content_markdown, 
                        severity, loss_usd, file_paths, fix_commit, root_cause_keywords,
                        raw_solidity_code, source_repo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        finding_data["id"],
                        finding_data["source_pool"],
                        finding_data.get("protocol_name"),
                        finding_data.get("title"),
                        finding_data.get("content_markdown"),
                        finding_data.get("severity"),
                        finding_data.get("loss_usd"),
                        file_paths_str,
                        finding_data.get("fix_commit"),
                        keywords_str,
                        finding_data.get("raw_solidity_code"),
                        finding_data.get("source_repo")
                    ))
                    
                    cursor.execute("DELETE FROM vulnerability_tags_index WHERE finding_id = ?", (finding_data["id"],))
                    keywords = finding_data.get("root_cause_keywords", [])
                    if isinstance(keywords, list):
                        seen_tags = set()
                        for kw in keywords:
                            if kw:
                                tag = str(kw).strip().lower()
                                if tag and tag not in seen_tags:
                                    seen_tags.add(tag)
                                    cursor.execute("""
                                    INSERT OR IGNORE INTO vulnerability_tags_index (finding_id, source_pool, tag)
                                    VALUES (?, ?, ?)
                                    """, (finding_data["id"], finding_data["source_pool"], tag))
        except Exception as e:
            print(f"Error in batch insert: {e}")
        finally:
            conn.close()

def insert_finding(finding_data):
    """
    Inserts or replaces a single normalized finding in the database.
    """
    insert_findings_batch([finding_data])

def is_repo_already_processed(source_repo):
    """Checks the database to see if a repository's findings have already been ingested."""
    if not DB_FILE.exists():
        return False
    try:
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM normalized_findings WHERE source_repo = ? LIMIT 1", (source_repo,))
        row = cursor.fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        print(f"Error checking if repo was processed: {e}")
        return False

if __name__ == "__main__":
    init_db()

