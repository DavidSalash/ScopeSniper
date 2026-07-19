#!/usr/bin/env python3
import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import sqlite3
import re
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_COOKIE = '_ga=GA1.1.1549337777.1783956490; cf_clearance=z6TwEabkfpIVSOjVybFlI5t.vU5CSEXyLxza6HgpwgY-1783968141-1.2.1.1-hztG3yexej03.bYby1Ny1JAAtmgYYrfDVH98AW66YWMYYxcXgkKKkKP4pGag6wAfSbbA1vklWe6v_CFSq2HtTJX3Tjvo4FpaFhMbbWDIZdO1W1cE7HpdoLrihhivmwMYbIDWC3Z_wEoicoqRHt1gFWQXpKrGZcI7mVDVUpbyJYDAqPUBSerebIJrcFDk5QhL8x6YD9hXzWnnIZCQQVtMuD17DyeDtxE2uupLRKRf._nRVy9BWvT1w707CqpNova5jtyJ6ffuce931YaTrqc0YVg0jfBBed6HqrqlQtoOKb0X1oSNSvOzcJ2Wlxu9fKGiLtHeRwlfop.18tb8C7F3.dQ7uqvmqD.BCAMHYmwwChlBnq_TFoXGchbf5iCezK9lFoPOvbwdvNo4CErq57Ruu2NdIJD77zul0sCUSy_b7GpUKQbfJZMUQyM2uXKkNt_j; pdfcc=11; _ga_S11XDQH3PJ=GS2.1.s1783964977$o3$g1$t1783968143$j55$l0$h0; _ga_8QL66761YT=GS2.1.s1783964977$o3$g1$t1783968143$j55$l0$h0'

DEFAULT_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en,es;q=0.9,zh-CN;q=0.8,zh;q=0.7',
    'cache-control': 'max-age=0',
    'sec-ch-ua': '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-bitness': '"64"',
    'sec-ch-ua-full-version': '"150.0.7871.101"',
    'sec-ch-ua-full-version-list': '"Not;A=Brand";v="8.0.0.0", "Chromium";v="150.0.7871.101", "Google Chrome";v="150.0.7871.101"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-platform-version': '"19.0.0"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
}
if os.path.exists("/app"):
    DEFAULT_DB_PATH = "/app/data_store/hbb.db"
else:
    DEFAULT_DB_PATH = "C:/users/david/hbb.db"

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

def parse_amount(val):
    if val is None:
        return None
    # Remove currency symbols, commas, and whitespace
    clean = re.sub(r'[^\d.]', '', str(val))
    if not clean:
        return None
    try:
        return int(float(clean))
    except ValueError:
        return None

def safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None

def safe_str(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)

def insert_or_replace_project(cursor, project):
    slug = project.get("slug")
    if not slug:
        return
    
    # Extract website_url and github_url from scopes
    website_url = None
    github_url = project.get("repo_url") or None
    scopes = project.get("scopes", [])
    if isinstance(scopes, list):
        for scope in scopes:
            if not isinstance(scope, dict):
                continue
            target = scope.get("target") or ""
            title = (scope.get("title") or "").lower()
            if target.startswith("http"):
                if "github.com" in target:
                    if not github_url:
                        github_url = target
                elif "web" in title:
                    if not website_url:
                        website_url = target
                        
    logo = project.get("logo")
    if logo and logo.startswith("/"):
        logo = "https://hackenproof.com" + logo

    max_bounty = parse_amount(project.get("max_bounty"))
    rewards_pool = parse_amount(project.get("total_rewards"))

    proj_row = (
        slug,
        safe_str(project.get("title")),
        safe_str(project.get("desc")),
        safe_str(website_url),
        safe_str(github_url),
        safe_str(logo),
        safe_str(project.get("published_date") or project.get("start_date")),
        safe_str(project.get("updated_at")),
        safe_str(project.get("end_date")),
        safe_str(project.get("end_date")), # evaluationEndDate
        max_bounty,
        rewards_pool,
        None, # primary_pool
        None, # all_stars_pool
        None, # podium_pool
        "USD", # rewards_token
        None, # primary_payment_wallet
        0, # immunefi_standard
        1 if project.get("private") else 0, # invite_only
        1 if project.get("kyc_required") else 0, # kyc
        0, # ten_percent_economic_rule
        None, # responsible_publication_category
        safe_str(project.get("desc")), # program_overview
        safe_str(project.get("program_rules")), # out_of_scope_and_rules
        safe_str(project.get("focus_area")), # prioritized_vulnerabilities
        None, # rewards_body
        None, # assets_body_v2
        None, # impacts_body
        None, # default_out_of_scope_blockchain
        None, # default_out_of_scope_smart_contract
        None, # default_out_of_scope_web_and_applications
        None, # default_out_of_scope_general
        None, # default_feasibility_limitations
        None, # default_prohibited_activities
        None, # custom_out_of_scope_information
        None, # boosted_intro_evaluating
        None, # boosted_intro_finished
        None, # boosted_intro_live
        None, # boosted_intro_starting_in
        None, # boosted_summary_report
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
    
    # Clear existing child records
    cursor.execute("DELETE FROM assets WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM impacts WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM rewards WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM audits WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM boosted_leaderboard WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM known_issues WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM project_lists WHERE project_slug = ?", (slug,))
    
    # Ingest assets (scopes)
    if isinstance(scopes, list):
        for scope in scopes:
            if not isinstance(scope, dict):
                continue
            asset_id = scope.get("id")
            target = scope.get("target") or ""
            title = scope.get("title") or ""
            target_desc = scope.get("target_description") or ""
            out_of_scope = scope.get("out_of_scope", False)
            criticality = scope.get("criticality")
            
            desc_parts = []
            if target_desc:
                desc_parts.append(target_desc)
            if criticality:
                desc_parts.append(f"Criticality: {criticality}")
            if out_of_scope:
                desc_parts.append("OUT OF SCOPE")
                
            description = " | ".join(desc_parts)

            cursor.execute("""
                INSERT INTO assets (
                    project_slug, id, url, type, added_at, revision, description, is_safe_harbor, is_primacy_of_impact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slug,
                safe_str(asset_id),
                safe_str(target),
                safe_str(title),
                None, # added_at
                None, # revision
                safe_str(description),
                0, # is_safe_harbor
                0  # is_primacy_of_impact
            ))

    # Ingest rewards
    rewards = project.get("rewards", {})
    if isinstance(rewards, dict):
        reward_id_counter = 1
        for level in ["critical", "high", "medium", "low"]:
            min_key = f"{level}_min"
            max_key = f"{level}_max"
            min_val = safe_int(rewards.get(min_key))
            max_val = safe_int(rewards.get(max_key))
            
            if min_val is not None or max_val is not None:
                payout_str = f"Max: {max_val} USD" if max_val is not None else ""
                if min_val is not None:
                    payout_str += f" (Min: {min_val} USD)"
                
                level_name = level.capitalize()
                
                cursor.execute("""
                    INSERT INTO rewards (
                        project_slug, id, level, payout, asset_type, poc_required, primacy, severity, max_reward, min_reward, reward_model, reward_calculation_percentage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    slug,
                    reward_id_counter,
                    safe_str(level_name),
                    safe_str(payout_str),
                    None, # asset_type
                    1 if project.get("poc_required") else 0,
                    None, # primacy
                    safe_str(level_name),
                    max_val,
                    min_val,
                    None,
                    None
                ))
                reward_id_counter += 1

    # Ingest lists (labels)
    labels = project.get("labels", {})
    if isinstance(labels, dict):
        for lang in labels.get("languages", []):
            cursor.execute("""
                INSERT INTO project_lists (project_slug, list_name, value) VALUES (?, ?, ?)
            """, (slug, "language", safe_str(lang)))
            
        for ptype in labels.get("types", []):
            cursor.execute("""
                INSERT INTO project_lists (project_slug, list_name, value) VALUES (?, ?, ?)
            """, (slug, "productType", safe_str(ptype)))
            
        for proj_type in labels.get("project_types", []):
            cursor.execute("""
                INSERT INTO project_lists (project_slug, list_name, value) VALUES (?, ?, ?)
            """, (slug, "projectType", safe_str(proj_type)))

def fetch_url_json(url, cookie, headers):
    req_headers = headers.copy()
    req_headers['cookie'] = cookie
    req = urllib.request.Request(url, headers=req_headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(req, context=ctx) as response:
        content = response.read().decode('utf-8')
        return json.loads(content)

def sync_db(db_path, cookie):
    print("Fetching active HackenProof programs list...")
    list_url = 'https://hackenproof.com/programs-api/programs?not_audits=true&search&page=1&per_page=200&order_by%5Bpublished_date%5D=desc&with_abilities%5B%5D=smart+contract'
    
    headers = DEFAULT_HEADERS.copy()
    try:
        list_data = fetch_url_json(list_url, cookie, headers)
        programs = list_data.get("programs", [])
    except Exception as e:
        print(f"Error fetching programs list: {e}", file=sys.stderr)
        return

    print(f"Found {len(programs)} programs to synchronize.")
    
    results = [None] * len(programs)
    
    def worker(idx, program):
        slug = program.get("slug")
        if not slug:
            return idx, None
        detail_url = f"https://hackenproof.com/programs-api/programs/{slug}"
        # Set referer header dynamically
        thread_headers = headers.copy()
        thread_headers['referer'] = f"https://hackenproof.com/programs/{slug}"
        try:
            detail_data = fetch_url_json(detail_url, cookie, thread_headers)
            return idx, detail_data
        except Exception as e:
            print(f"Error fetching details for '{slug}': {e}", file=sys.stderr)
            return idx, None

    print("Fetching details concurrently...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_idx = {executor.submit(worker, idx, prog): idx for idx, prog in enumerate(programs)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                _, detail_data = future.result()
                results[idx] = detail_data
                slug = programs[idx].get("slug")
                if detail_data:
                    print(f"[{idx+1}/{len(programs)}] Successfully fetched {slug}")
                else:
                    print(f"[{idx+1}/{len(programs)}] Failed to fetch {slug}", file=sys.stderr)
            except Exception as e:
                print(f"[{idx+1}/{len(programs)}] Exception fetching {programs[idx].get('slug')}: {e}", file=sys.stderr)

    success_count = 0
    try:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        init_db_schema(cursor)
        
        for idx, detail_data in enumerate(results):
            if detail_data:
                insert_or_replace_project(cursor, detail_data)
                success_count += 1
                
        conn.commit()
        conn.close()
        print(f"Database synchronization completed! Successfully ingested {success_count}/{len(programs)} programs.")
    except Exception as e:
        print(f"Database error: {e}", file=sys.stderr)

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
        description="Is like jq for HackenProof Bug Bounty REST API. Search, filter and map structured data about bug bounty programs with ease. Replicated in Python with database support.",
        epilog="""Examples:
  python hbb.py
  python hbb.py zynk-protocol
  python hbb.py zynk-protocol scopes
  python hbb.py zynk-protocol title
  python hbb.py --sync
  python hbb.py --db-query "SELECT slug, max_bounty FROM projects WHERE max_bounty > 20000 ORDER BY max_bounty DESC LIMIT 5"
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'query',
        nargs='*',
        help='[slug] [field] [another_field] ...'
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Synchronize database by fetching from HackenProof API'
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
    parser.add_argument(
        '--cookie',
        type=str,
        default=DEFAULT_COOKIE,
        help='Cookie header to pass to the HackenProof API'
    )
    
    args = parser.parse_args()

    if args.sync:
        sync_db(args.db_path, args.cookie)
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
