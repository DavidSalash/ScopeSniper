#!/usr/bin/env python3
import os
import sys
import json
import argparse
import urllib.request
import sqlite3
import re
import ssl

if os.path.exists("/app"):
    DEFAULT_DB_PATH = "/app/data_store/cbb.db"
else:
    DEFAULT_DB_PATH = "C:/users/david/cbb.db"

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

def safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None

def safe_bool(v):
    if v is None:
        return None
    return 1 if v else 0

def safe_str(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)

def insert_or_replace_project(cursor, project):
    slug = project.get("id")
    if not slug:
        return
    
    company = project.get("company") or {}
    timeframe = project.get("timeframe") or {}
    
    # Calculate max bounty
    max_bounty = parse_amount(project.get("totalRewardPot"))
    
    # Format github url
    gh_handle = company.get("github")
    github_url = None
    if gh_handle:
        if gh_handle.startswith("http"):
            github_url = gh_handle
        else:
            github_url = f"https://github.com/{gh_handle}"
            
    currency_code = project.get("currencyCode", "USDC")

    proj_row = (
        slug,
        safe_str(project.get("name")),
        safe_str(project.get("instructions")),
        safe_str(company.get("website")),
        safe_str(github_url),
        safe_str(company.get("logo")),
        safe_str(timeframe.get("start")),
        safe_str(project.get("createdAt")),
        safe_str(timeframe.get("end")),
        safe_str(timeframe.get("end")), # evaluationEndDate
        max_bounty,
        max_bounty, # rewards_pool
        None, # primary_pool
        None, # all_stars_pool
        None, # podium_pool
        safe_str(currency_code),
        None, # primary_payment_wallet
        0, # immunefi_standard
        1 if project.get("joined") == "restricted" else 0, # invite_only
        1 if project.get("kycRequired") else 0, # kyc
        0, # ten_percent_economic_rule
        None, # responsible_publication_category
        safe_str(project.get("instructions")), # program_overview
        None, # out_of_scope_and_rules
        None, # prioritized_vulnerabilities
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
    
    # 2. Ingest assets
    asset_groups = project.get("assetGroups", [])
    if isinstance(asset_groups, list):
        for group in asset_groups:
            if not isinstance(group, dict):
                continue
            group_name = group.get("name", "Asset Group")
            assets = group.get("assets", [])
            if isinstance(assets, list):
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    asset_id = asset.get("id")
                    asset_name = asset.get("name") or ""
                    asset_desc = asset.get("description") or ""
                    asset_ref = asset.get("reference") or ""
                    
                    url = ""
                    if asset_desc.startswith("http"):
                        url = asset_desc
                    elif asset_ref.startswith("http"):
                        url = asset_ref
                    
                    # Combine descriptions
                    desc_parts = []
                    if asset_name:
                        desc_parts.append(f"Name: {asset_name}")
                    if asset_desc and not asset_desc.startswith("http"):
                        desc_parts.append(f"Desc: {asset_desc}")
                    if asset_ref and not asset_ref.startswith("http"):
                        desc_parts.append(f"Ref: {asset_ref}")
                    description = " | ".join(desc_parts)
                    
                    cursor.execute("""
                        INSERT INTO assets (
                            project_slug, id, url, type, added_at, revision, description, is_safe_harbor, is_primacy_of_impact
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        slug,
                        safe_str(asset_id),
                        safe_str(url),
                        safe_str(group_name),
                        None, # added_at
                        None, # revision
                        safe_str(description),
                        0, # is_safe_harbor
                        0  # is_primacy_of_impact
                    ))

    # 3. Ingest rewards
    reward_id_counter = 1
    if isinstance(asset_groups, list):
        for group in asset_groups:
            if not isinstance(group, dict):
                continue
            group_name = group.get("name", "Asset Group")
            rewards = group.get("rewards", [])
            if isinstance(rewards, list):
                for rew in rewards:
                    if not isinstance(rew, dict):
                        continue
                    severity = rew.get("severity")
                    min_reward_val = parse_amount(rew.get("minReward"))
                    max_reward_val = parse_amount(rew.get("maxReward"))
                    
                    payout_str = ""
                    if max_reward_val is not None:
                        payout_str = f"Max: {max_reward_val} {currency_code}"
                    if min_reward_val is not None:
                        payout_str += f" (Min: {min_reward_val} {currency_code})"
                        
                    cursor.execute("""
                        INSERT INTO rewards (
                            project_slug, id, level, payout, asset_type, poc_required, primacy, severity, max_reward, min_reward, reward_model, reward_calculation_percentage
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        slug,
                        reward_id_counter,
                        safe_str(severity),
                        safe_str(payout_str),
                        safe_str(group_name),
                        None,
                        None,
                        safe_str(severity),
                        max_reward_val,
                        min_reward_val,
                        None,
                        None
                    ))
                    reward_id_counter += 1

    # 4. Ingest lists
    cursor.execute("""
        INSERT INTO project_lists (project_slug, list_name, value) VALUES (?, ?, ?)
    """, (slug, "projectType", safe_str(project.get("kind"))))
    
    # Simple programming language finder
    languages_found = []
    text_to_search = (project.get("instructions") or "").lower()
    if "solidity" in text_to_search:
        languages_found.append("Solidity")
    if "rust" in text_to_search:
        languages_found.append("Rust")
    if "vyper" in text_to_search:
        languages_found.append("Vyper")
    if "yul" in text_to_search:
        languages_found.append("Yul")
    
    for lang in languages_found:
        cursor.execute("""
            INSERT INTO project_lists (project_slug, list_name, value) VALUES (?, ?, ?)
        """, (slug, "language", lang))

def sync_db(db_path):
    print("Fetching live bug bounties from Cantina opportunities page...")
    url_web = 'https://cantina.xyz/opportunities'
    headers_web = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en,es;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'cache-control': 'max-age=0',
        'cookie': 'ajs_anonymous_id=fe7fe9ad-d84e-43ba-9c43-d6c49ef05d3f; ajs_user_id=7ff6d3f5-a75e-47a7-847c-53579d3cb666; _gcl_au=1.1.1673389980.1783353726; _ga=GA1.1.888342415.1783353720; utm_attribution=%7B%22source%22%3A%22direct%22%2C%22medium%22%3A%22none%22%2C%22campaign%22%3A%22direct%22%2C%22content%22%3A%22%22%2C%22term%22%3A%22%22%2C%22referrer%22%3A%22%22%2C%22referrerDomain%22%3A%22%22%2C%22initialLandingPage%22%3A%22https%3A%2F%2Fcantina.xyz%2Fopportunities%22%2C%22currentPage%22%3A%22https%3A%2F%2Fcantina.xyz%2Fopportunities%22%2C%22firstVisit%22%3A%222026-07-06T16%3A02%3A06.276Z%22%2C%22timestamp%22%3A%222026-07-06T16%3A02%3A06.276Z%22%2C%22visits%22%3A1%7D; hubspotutk=acb25f1140df16abda95d4d676c8b046; _hjSessionUser_5337538=eyJpZCI6IjlmM2UxM2UzLWNlMDktNTU2OC1hNzlhLWY0ODUxNWQzZmYzYyIsImNyZWF0ZWQiOjE3ODMzNTM3MjY0ODksImV4aXN0aW5nIjp0cnVlfQ==; auth_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiJ9.eyJpc3MiOiJodHRwczovL2NhbnRpbmEueHl6Iiwic3ViIjoiMmVjZjVkMzItMTRjMC00YjllLWI5YjAtNTE0ZTk4YTQxNDI2IiwiYXVkIjoiaHR0cHM6Ly9jYW50aW5hLnh5eiIsImlhdCI6MTc4Mzk2MjAyMywiZXhwIjoxNzg2NTU0MDIzLCJwYXlsb2FkIjp7InVzZXJfaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAiLCJlbWFpbCI6ImRhdmlkemd6LmRzZ0BnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiYXV0aDBfaWQiOiJnb29nbGUtb2F1dGgyfDEwODc2OTgwNTY1NjkyNDQ2NjAzMSJ9fQ.5Ohq09a6Fn90BRC9eomMAb2KIoPPgxs_okcNlzd0RNhx-9q8elYKzCxkycl9CSLcomXzNQ3GCFux_qHU43m2Pg; user_authenticated=true; pdfcc=1; session_id=019f6075-266b-75f8-b060-aecee509838d; analytics_session_id=1784029718124; utm_session_attribution=%7B%22source%22%3A%22direct%22%2C%22medium%22%3A%22none%22%2C%22campaign%22%3A%22direct%22%2C%22content%22%3A%22%22%2C%22term%22%3A%22%22%2C%22referrer%22%3A%22%22%2C%22referrerDomain%22%3A%22%22%2C%22initialLandingPage%22%3A%22https%3A%2F%2Fcantina.xyz%2Fopportunities%22%2C%22firstVisit%22%3A%222026-07-06T16%3A02%3A06.276Z%22%2C%22sessionLandingPage%22%3A%22https%3A%2F%2Fcantina.xyz%2Fopportunities%22%2C%22currentPage%22%3A%22https%3A%2F%2Fcantina.xyz%2Fopportunities%22%2C%22sessionStart%22%3A%222026-07-14T11%3A48%3A42.092Z%22%2C%22timestamp%22%3A%222026-07-14T11%3A48%3A42.092Z%22%7D; _hjSession_5337538=eyJpZCI6IjE5MTU4MGEyLTM2ZTMtNDcxNS04ZDdhLTdkMTE2NTE2MzcwYSIsImMiOjE3ODQwMjk3MjIyMDgsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowLCJzcCI6MX0=; _ga_1D74YYQDX5=GS2.1.s1784029722$o4$g0$t1784029722$j60$l0$h0; _ga_HX2Y7W1ZJN=GS2.1.s1784029722$o4$g0$t1784029722$j60$l0$h1921406608; __hstc=129616339.acb25f1140df16abda95d4d676c8b046.1783353727001.1783982882626.1784029722391.5; __hssrc=1; __hssc=129616339.1.1784029722391; analytics_session_id.last_access=1784029747372',
        'priority': 'u=0, i',
        'sec-ch-ua': '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    projects_data = []

    # 1. Scrape from webpage to extract the initial programs
    try:
        req = urllib.request.Request(url_web, headers=headers_web)
        with urllib.request.urlopen(req, context=ctx) as response:
            html = response.read().decode('utf-8')
        
        chunks = []
        pos = 0
        while True:
            idx = html.find('self.__next_f.push([1,"', pos)
            if idx == -1:
                break
            start = idx + len('self.__next_f.push([1,"')
            end = start
            while True:
                end = html.find('"])', end)
                if end == -1:
                    break
                backslash_count = 0
                temp = end - 1
                while temp >= start and html[temp] == '\\':
                    backslash_count += 1
                    temp -= 1
                if backslash_count % 2 == 0:
                    break
                else:
                    end += 3
            
            if end != -1:
                chunk = html[start:end]
                try:
                    decoded = json.loads(f'"{chunk}"')
                    chunks.append(decoded)
                except:
                    pass
                pos = end + 3
            else:
                break

        full_stream = "".join(chunks)
        matches = list(re.finditer(r'\{"state":\{"mutations":\[\],"queries":', full_stream))
        for match in matches:
            start_idx = match.start()
            brace_count = 0
            json_len = 0
            for i in range(start_idx, len(full_stream)):
                char = full_stream[i]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                json_len += 1
                if brace_count == 0 and json_len > 10:
                    break
            json_str = full_stream[start_idx:start_idx+json_len]
            try:
                data = json.loads(json_str)
                queries = data.get("state", {}).get("queries", [])
                for q in queries:
                    q_key = q.get("queryKey")
                    if isinstance(q_key, list) and len(q_key) > 1 and q_key[1] == 'opportunities.listOpportunities':
                        q_data = q.get("state", {}).get("data", {})
                        if isinstance(q_data, dict) and "pages" in q_data:
                            for page in q_data["pages"]:
                                if isinstance(page, dict) and "items" in page:
                                    projects_data.extend(page["items"])
            except Exception:
                pass
        print(f"Extracted {len(projects_data)} programs from webpage NextJS stream.")
    except Exception as e:
        print(f"Error parsing opportunities page: {e}", file=sys.stderr)

    # 2. Fetch from REST API to make sure we load all projects (since initial HTML only renders a portion)
    print("Fetching live bug bounties from Cantina REST API...")
    url_api = 'https://api.cantina.xyz/api/v0/opportunities?status=live&limit=100'
    headers_api = {
        'accept': '*/*',
        'accept-language': headers_web['accept-language'],
        'cookie': headers_web['cookie'],
        'origin': 'https://cantina.xyz',
        'user-agent': headers_web['user-agent']
    }

    try:
        req_api = urllib.request.Request(url_api, headers=headers_api)
        with urllib.request.urlopen(req_api, context=ctx) as response:
            content = response.read().decode('utf-8')
            data = json.loads(content)
            api_items = data.get("items", [])
            print(f"Fetched {len(api_items)} programs from API.")
            
            # Combine/merge projects. The API contains fully resolved fields (without Next.js RSC references),
            # so we overwrite any scraped items from projects_data with their API counterparts.
            scraped_by_id = {p.get("id"): idx for idx, p in enumerate(projects_data) if p.get("id")}
            for item in api_items:
                item_id = item.get("id")
                if item_id in scraped_by_id:
                    idx = scraped_by_id[item_id]
                    projects_data[idx] = item
                else:
                    projects_data.append(item)
    except Exception as e:
        print(f"Error fetching data from Cantina API: {e}", file=sys.stderr)

    if not projects_data:
        print("No projects loaded. Sync aborted.", file=sys.stderr)
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
        description="Is like jq for Cantina Bug Bounty REST API. Search, filter and map structured data about bug bounty programs with ease. Replicated in Python with database support.",
        epilog="""Examples:
  python cbb.py
  python cbb.py f9df94db-c7b1-434b-bb06-d1360abdd1be
  python cbb.py f9df94db-c7b1-434b-bb06-d1360abdd1be assetGroups
  python cbb.py f9df94db-c7b1-434b-bb06-d1360abdd1be name
  python cbb.py --sync
  python cbb.py --db-query "SELECT slug, max_bounty FROM projects WHERE max_bounty > 1000000 ORDER BY max_bounty DESC LIMIT 5"
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'query',
        nargs='*',
        help='[uuid] [field] [another_field] ...'
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Synchronize database by fetching from Cantina API'
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
