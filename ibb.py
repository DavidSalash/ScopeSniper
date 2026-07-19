#!/usr/bin/env python3
import os
import sys
import json
import argparse
import urllib.request
import sqlite3
if os.path.exists("/app"):
    DEFAULT_DB_PATH = "/app/data_store/ibb.db"
else:
    DEFAULT_DB_PATH = "C:/users/david/ibb.db"

def init_db_schema(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            slug TEXT PRIMARY KEY,
            project TEXT,
            description TEXT,
            website_url TEXT,
            github_url TEXT,
            logo TEXT,
            launch_date TEXT,
            updated_date TEXT,
            end_date TEXT,
            evaluation_end_date TEXT,
            max_bounty INTEGER,
            rewards_pool INTEGER,
            primary_pool INTEGER,
            all_stars_pool INTEGER,
            podium_pool INTEGER,
            rewards_token TEXT,
            primary_payment_wallet TEXT,
            immunefi_standard INTEGER,
            invite_only INTEGER,
            kyc INTEGER,
            ten_percent_economic_rule INTEGER,
            responsible_publication_category TEXT,
            program_overview TEXT,
            out_of_scope_and_rules TEXT,
            prioritized_vulnerabilities TEXT,
            rewards_body TEXT,
            assets_body_v2 TEXT,
            impacts_body TEXT,
            default_out_of_scope_blockchain TEXT,
            default_out_of_scope_smart_contract TEXT,
            default_out_of_scope_web_and_applications TEXT,
            default_out_of_scope_general TEXT,
            default_feasibility_limitations TEXT,
            default_prohibited_activities TEXT,
            custom_out_of_scope_information TEXT,
            boosted_intro_evaluating TEXT,
            boosted_intro_finished TEXT,
            boosted_intro_live TEXT,
            boosted_intro_starting_in TEXT,
            boosted_summary_report TEXT,
            raw_json TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT,
            id TEXT,
            url TEXT,
            type TEXT,
            added_at TEXT,
            revision INTEGER,
            description TEXT,
            is_safe_harbor INTEGER,
            is_primacy_of_impact INTEGER,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS impacts (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT,
            id INTEGER,
            type TEXT,
            severity TEXT,
            title TEXT,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT,
            id INTEGER,
            level TEXT,
            payout TEXT,
            asset_type TEXT,
            poc_required INTEGER,
            primacy TEXT,
            severity TEXT,
            max_reward INTEGER,
            min_reward INTEGER,
            reward_model TEXT,
            reward_calculation_percentage REAL,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT,
            id TEXT,
            url TEXT,
            auditor TEXT,
            date TEXT,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS boosted_leaderboard (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT,
            name TEXT,
            high INTEGER,
            critical INTEGER,
            medium_low INTEGER,
            earnings INTEGER,
            insights INTEGER,
            asp_rank INTEGER,
            all_star_tier TEXT,
            total_earnings INTEGER,
            total_valid_bugs INTEGER,
            asp_pool_earnings INTEGER,
            podium_pool_earnings INTEGER,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS known_issues (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT,
            id INTEGER,
            link TEXT,
            description TEXT,
            last_updated_at TEXT,
            related_impact_in_scope TEXT,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_lists (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT,
            list_name TEXT,
            value TEXT,
            FOREIGN KEY(project_slug) REFERENCES projects(slug) ON DELETE CASCADE
        );
    """)

def insert_or_replace_project(cursor, project):
    slug = project.get("slug")
    if not slug:
        return
    
    # Helper to safe get integer
    def safe_int(v):
        if v is None:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    # Helper to safe get float
    def safe_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    # Helper to safe get boolean as int
    def safe_bool(v):
        if v is None:
            return None
        return 1 if v else 0

    # Helper to safe get string
    def safe_str(v):
        if v is None:
            return None
        if isinstance(v, (dict, list)):
            return json.dumps(v)
        return str(v)

    max_bounty = safe_int(project.get("maxBounty"))
    rewards_pool = safe_int(project.get("rewardsPool"))
    primary_pool = safe_int(project.get("primaryPool"))
    all_stars_pool = safe_int(project.get("allStarsPool"))
    podium_pool = safe_int(project.get("podiumPool"))

    proj_row = (
        slug,
        safe_str(project.get("project")),
        safe_str(project.get("description")),
        safe_str(project.get("websiteUrl")),
        safe_str(project.get("githubUrl")),
        safe_str(project.get("logo")),
        safe_str(project.get("launchDate")),
        safe_str(project.get("updatedDate")),
        safe_str(project.get("endDate")),
        safe_str(project.get("evaluationEndDate")),
        max_bounty,
        rewards_pool,
        primary_pool,
        all_stars_pool,
        podium_pool,
        safe_str(project.get("rewardsToken")),
        safe_str(project.get("primaryPaymentWallet")),
        safe_bool(project.get("immunefiStandard")),
        safe_bool(project.get("inviteOnly")),
        safe_bool(project.get("kyc")),
        safe_bool(project.get("tenPercentEconomicRule")),
        safe_str(project.get("responsiblePublicationCategory")),
        safe_str(project.get("programOverview")),
        safe_str(project.get("outOfScopeAndRules")),
        safe_str(project.get("prioritizedVulnerabilities")),
        safe_str(project.get("rewardsBody")),
        safe_str(project.get("assetsBodyV2")),
        safe_str(project.get("impactsBody")),
        safe_str(project.get("defaultOutOfScopeBlockchain")),
        safe_str(project.get("defaultOutOfScopeSmartContract")),
        safe_str(project.get("defaultOutOfScopeWebAndApplications")),
        safe_str(project.get("defaultOutOfScopeGeneral")),
        safe_str(project.get("defaultFeasibilityLimitations")),
        safe_str(project.get("defaultProhibitedActivities")),
        safe_str(project.get("customOutOfScopeInformation")),
        safe_str(project.get("boostedIntroEvaluating")),
        safe_str(project.get("boostedIntroFinished")),
        safe_str(project.get("boostedIntroLive")),
        safe_str(project.get("boostedIntroStartingIn")),
        safe_str(project.get("boostedSummaryReport")),
        json.dumps(project)  # raw_json
    )
    
    cursor.execute("""
        INSERT OR REPLACE INTO projects (
            slug, project, description, website_url, github_url, logo, launch_date, updated_date,
            end_date, evaluation_end_date, max_bounty, rewards_pool, primary_pool, all_stars_pool, podium_pool,
            rewards_token, primary_payment_wallet, immunefi_standard, invite_only, kyc, ten_percent_economic_rule,
            responsible_publication_category, program_overview, out_of_scope_and_rules, prioritized_vulnerabilities,
            rewards_body, assets_body_v2, impacts_body, default_out_of_scope_blockchain, default_out_of_scope_smart_contract,
            default_out_of_scope_web_and_applications, default_out_of_scope_general, default_feasibility_limitations,
            default_prohibited_activities, custom_out_of_scope_information, boosted_intro_evaluating, boosted_intro_finished,
            boosted_intro_live, boosted_intro_starting_in, boosted_summary_report, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, proj_row)
    
    # Clear existing child records manually for clean synchronization
    cursor.execute("DELETE FROM assets WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM impacts WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM rewards WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM audits WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM boosted_leaderboard WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM known_issues WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM project_lists WHERE project_slug = ?", (slug,))
    
    # 2. Ingest assets
    assets = project.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict):
                cursor.execute("""
                    INSERT INTO assets (
                        project_slug, id, url, type, added_at, revision, description, is_safe_harbor, is_primacy_of_impact
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    slug,
                    safe_str(asset.get("id")),
                    safe_str(asset.get("url")),
                    safe_str(asset.get("type")),
                    safe_str(asset.get("addedAt")),
                    safe_int(asset.get("revision")),
                    safe_str(asset.get("description")),
                    safe_bool(asset.get("isSafeHarbor")),
                    safe_bool(asset.get("isPrimacyOfImpact"))
                ))

    # 3. Ingest impacts
    impacts = project.get("impacts", [])
    if isinstance(impacts, list):
        for imp in impacts:
            if isinstance(imp, dict):
                cursor.execute("""
                    INSERT INTO impacts (
                        project_slug, id, type, severity, title
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    slug,
                    safe_int(imp.get("id")),
                    safe_str(imp.get("type")),
                    safe_str(imp.get("severity")),
                    safe_str(imp.get("title"))
                ))

    # 4. Ingest rewards
    rewards = project.get("rewards", [])
    if isinstance(rewards, list):
        for rew in rewards:
            if isinstance(rew, dict):
                cursor.execute("""
                    INSERT INTO rewards (
                        project_slug, id, level, payout, asset_type, poc_required, primacy, severity, max_reward, min_reward, reward_model, reward_calculation_percentage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    slug,
                    safe_int(rew.get("id")),
                    safe_str(rew.get("level")),
                    safe_str(rew.get("payout")),
                    safe_str(rew.get("assetType")),
                    safe_bool(rew.get("pocRequired")),
                    safe_str(rew.get("primacy")),
                    safe_str(rew.get("severity")),
                    safe_int(rew.get("maxReward") if rew.get("maxReward") is not None else rew.get("fixedReward")),
                    safe_int(rew.get("minReward")),
                    safe_str(rew.get("rewardModel")),
                    safe_float(rew.get("rewardCalculationPercentage"))
                ))

    # 5. Ingest audits
    audits = project.get("audits", [])
    if isinstance(audits, list):
        for aud in audits:
            if isinstance(aud, dict):
                cursor.execute("""
                    INSERT INTO audits (
                        project_slug, id, url, auditor, date
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    slug,
                    safe_str(aud.get("id")),
                    safe_str(aud.get("url")),
                    safe_str(aud.get("auditor")),
                    safe_str(aud.get("date"))
                ))

    # 6. Ingest boostedLeaderboard
    leaderboard = project.get("boostedLeaderboard", [])
    if isinstance(leaderboard, list):
        for lb in leaderboard:
            if isinstance(lb, dict):
                cursor.execute("""
                    INSERT INTO boosted_leaderboard (
                        project_slug, name, high, critical, medium_low, earnings, insights, asp_rank, all_star_tier, total_earnings, total_valid_bugs, asp_pool_earnings, podium_pool_earnings
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    slug,
                    safe_str(lb.get("name")),
                    safe_int(lb.get("high")),
                    safe_int(lb.get("critical")),
                    safe_int(lb.get("mediumLow")),
                    safe_int(lb.get("earnings")),
                    safe_int(lb.get("insights")),
                    safe_int(lb.get("aspRank")),
                    safe_str(lb.get("allStarTier")),
                    safe_int(lb.get("totalEarnings")),
                    safe_int(lb.get("totalValidBugs")),
                    safe_int(lb.get("aspPoolEarnings")),
                    safe_int(lb.get("podiumPoolEarnings"))
                ))

    # 7. Ingest knownIssues
    known_issues = project.get("knownIssues", [])
    if isinstance(known_issues, list):
        for ki in known_issues:
            if isinstance(ki, dict):
                cursor.execute("""
                    INSERT INTO known_issues (
                        project_slug, id, link, description, last_updated_at, related_impact_in_scope
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    slug,
                    safe_int(ki.get("id")),
                    safe_str(ki.get("link")),
                    safe_str(ki.get("description")),
                    safe_str(ki.get("lastUpdatedAt")),
                    safe_str(ki.get("relatedImpactInScope"))
                ))

    # 8. Ingest lists of strings
    list_fields = [
        "customProhibitedActivities", "ecosystem", "eligibilityCriteria", "features",
        "language", "pocPerTypeAndSeverity", "productType", "programType", "projectType"
    ]
    for field in list_fields:
        items = project.get(field, [])
        if isinstance(items, list):
            for item in items:
                if item is not None:
                    cursor.execute("""
                        INSERT INTO project_lists (project_slug, list_name, value) VALUES (?, ?, ?)
                    """, (slug, field, safe_str(item)))

def sync_db(db_path):
    print("Fetching projects from unofficial Immunefi endpoint...")
    url = "https://cdn.jsdelivr.net/gh/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial/projects.json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
            projects_data = json.loads(content)
    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        return

    print(f"Loaded {len(projects_data)} projects. Writing to SQLite database at {db_path}...")
    
    try:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        
        init_db_schema(cursor)
        
        for project in projects_data:
            insert_or_replace_project(cursor, project)
            
        conn.commit()
        conn.close()
        print("Database synchronization successfully completed!")
    except Exception as e:
        print(f"Database error during sync: {e}", file=sys.stderr)

def cache_project_in_db(db_path, project):
    try:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        init_db_schema(cursor)
        insert_or_replace_project(cursor, project)
        conn.commit()
        conn.close()
    except Exception:
        pass

def extract_slugs(value, ids):
    if isinstance(value, dict):
        if "slug" in value and isinstance(value["slug"], str):
            ids.append(value["slug"])
        else:
            for v in value.values():
                extract_slugs(v, ids)
    elif isinstance(value, list):
        for v in value:
            extract_slugs(v, ids)

def get_all_slugs(db_path):
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT slug FROM projects ORDER BY slug ASC")
            rows = cursor.fetchall()
            conn.close()
            if rows:
                return [r[0] for r in rows]
        except Exception:
            pass

    # Fallback to fetching online
    url = "https://cdn.jsdelivr.net/gh/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial/projects.json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
            projects_data = json.loads(content)
            slugs = []
            extract_slugs(projects_data, slugs)
            return sorted(list(set(slugs)))
    except Exception as e:
        print(f"Error fetching slugs: {e}", file=sys.stderr)
        return []

def get_project(db_path, slug):
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT raw_json FROM projects WHERE slug = ?", (slug,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
        except Exception:
            pass
            
    # Fallback to fetching online
    url = f"https://cdn.jsdelivr.net/gh/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial/project/{slug}.json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
            project_data = json.loads(content)
            cache_project_in_db(db_path, project_data)
            return project_data
    except Exception:
        return None

def find_values_by_keys(value, keys):
    if not keys:
        return None
    
    first_key = keys[0]
    remaining_keys = keys[1:]
    
    if isinstance(value, dict):
        results = []
        for key, sub_value in value.items():
            if key == first_key:
                if not remaining_keys:
                    if isinstance(sub_value, list):
                        return sub_value
                    else:
                        results.append(sub_value)
                else:
                    found_value = find_values_by_keys(sub_value, remaining_keys)
                    if isinstance(found_value, list) and len(found_value) > 0:
                        results.extend(found_value)
            else:
                found_value = find_values_by_keys(sub_value, keys)
                if isinstance(found_value, list) and len(found_value) > 0:
                    results.extend(found_value)
        return results if results else None
        
    elif isinstance(value, list):
        results = []
        for item in value:
            found_value = find_values_by_keys(item, keys)
            if isinstance(found_value, list) and len(found_value) > 0:
                results.extend(found_value)
        return results if results else None
        
    return None

def run_db_query(db_path, sql_query):
    if not os.path.exists(db_path):
        print(f"Database file not found at '{db_path}'. Please run '--sync' first.", file=sys.stderr)
        sys.exit(1)
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        description = cursor.description
        if description is None:
            # Command didn't return rows (e.g. UPDATE, INSERT)
            conn.commit()
            print(f"Query executed successfully. Rows affected: {cursor.rowcount}")
        else:
            columns = [col[0] for col in description]
            rows = cursor.fetchall()
            results = [dict(zip(columns, row)) for row in rows]
            print(json.dumps(results, indent=2))
        conn.close()
    except Exception as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Is like jq for Immunefi REST API. Search, filter and map structured data about bug bounty programs with ease. Replicated in Python with database support.",
        epilog="""Examples:
  python ibb.py
  python ibb.py moonbeamnetwork
  python ibb.py moonbeamnetwork assets
  python ibb.py moonbeamnetwork assets url
  python ibb.py --sync
  python ibb.py --db-query "SELECT slug, max_bounty FROM projects WHERE max_bounty > 1000000 ORDER BY max_bounty DESC LIMIT 5"
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'query',
        nargs='*',
        help='[protocol_name] [field] [another_field] ...'
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Synchronize database with unofficial Immunefi CDN'
    )
    parser.add_argument(
        '--db-query',
        type=str,
        help='Execute a direct SQL query against the SQLite database'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=DEFAULT_DB_PATH,
        help=f'Path to SQLite database (default: {DEFAULT_DB_PATH})'
    )
    
    args = parser.parse_args()

    if args.sync:
        sync_db(args.db_path)
    elif args.db_query:
        run_db_query(args.db_path, args.db_query)
    else:
        if not args.query:
            slugs = get_all_slugs(args.db_path)
            print(json.dumps(slugs))
        else:
            slug = args.query[0]
            project_data = get_project(args.db_path, slug)
            if not project_data:
                print(f"Error: Program '{slug}' not found", file=sys.stderr)
                sys.exit(1)
                
            if len(args.query) > 1:
                result = find_values_by_keys(project_data, args.query[1:])
                if result is None:
                    print("null")
                else:
                    print(json.dumps(result, indent=2))
            else:
                print(json.dumps(project_data))

if __name__ == "__main__":
    main()
