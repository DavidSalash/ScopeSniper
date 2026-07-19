#!/usr/bin/env python3
import os
import sys
import csv
import json
import argparse
import urllib.request
import urllib.error
import ssl
import re
import sqlite3
import markdown
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
if os.path.exists("/app"):
    DEFAULT_DB_PATH = "/app/data_store/sbb.db"
else:
    DEFAULT_DB_PATH = "C:/users/david/sbb.db"

def init_db_schema(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            slug TEXT PRIMARY KEY,
            id INTEGER,
            project TEXT,
            description TEXT,
            website_url TEXT,
            github_url TEXT,
            logo TEXT,
            launch_date TEXT,
            updated_date TEXT,
            max_bounty INTEGER,
            rewards_pool INTEGER,
            rewards_token TEXT,
            main_content TEXT,
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
            description TEXT,
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
            min_reward INTEGER,
            max_reward INTEGER,
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

def safe_int(v):
    if v is None:
        return None
    clean = re.sub(r'[^\d]', '', str(v))
    if not clean:
        return None
    try:
        return int(clean)
    except ValueError:
        return None

def sluggify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\-]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

def extract_website_url(markdown_text):
    if not markdown_text:
        return None
    # Match website: http...
    match = re.search(r'(?:website|site)\s*:\s*(https?://[^\s]+)', markdown_text, re.IGNORECASE)
    if match:
        return match.group(1).rstrip('/').rstrip(')').rstrip(']')
    # Match markdown link [Website](url)
    match = re.search(r'\[Website\]\((https?://[^\s)]+)\)', markdown_text, re.IGNORECASE)
    if match:
        return match.group(1).rstrip('/')
    return None

def extract_github_url(markdown_text):
    if not markdown_text:
        return None
    # Match codebase/github: http...
    match = re.search(r'(?:github|codebase|source)\s*:\s*(https?://github\.com/[^\s]+)', markdown_text, re.IGNORECASE)
    if match:
        return match.group(1).rstrip('/').rstrip(')').rstrip(']')
    # Match markdown link [Github](url)
    match = re.search(r'\[Github\]\((https?://github\.com/[^\s)]+)\)', markdown_text, re.IGNORECASE)
    if match:
        return match.group(1).rstrip('/')
    return None

def parse_rewards_from_markdown(markdown_text):
    rewards = []
    if not markdown_text:
        return rewards
    section_match = re.search(r'##\s*(?:Reward\s*Amounts|Rewards|Reward).*?\n(.*?)(?=\n##|$)', markdown_text, re.DOTALL | re.IGNORECASE)
    if section_match:
        section_content = section_match.group(1)
        table_lines = re.findall(r'\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', section_content)
        for level, payout in table_lines:
            level = level.strip()
            payout = payout.strip()
            if level.lower() in ('severity', 'level', '---', ':---', '---:', ':---:'):
                continue
            numbers = re.findall(r'[\d,]+', payout)
            max_reward = None
            min_reward = None
            if numbers:
                clean_numbers = []
                for n in numbers:
                    val = safe_int(n)
                    if val is not None:
                        clean_numbers.append(val)
                if len(clean_numbers) == 1:
                    max_reward = clean_numbers[0]
                elif len(clean_numbers) >= 2:
                    min_reward = clean_numbers[0]
                    max_reward = clean_numbers[1]
            rewards.append({
                "level": level,
                "payout": payout,
                "min_reward": min_reward,
                "max_reward": max_reward
            })
    return rewards

def extract_element_by_class_substring(html, class_sub):
    if not html:
        return ""
    pattern = rf'<([^>\s]+)\s+[^>]*class=["\'][^"\']*?{class_sub}[^"\']*?["\'][^>]*>'
    match = re.search(pattern, html, re.IGNORECASE)
    if not match:
        return ""
    start_idx = match.start()
    tag_name = match.group(1)
    
    depth = 0
    pos = start_idx
    open_tag_start = f"<{tag_name}"
    close_tag = f"</{tag_name}>"
    
    while pos < len(html):
        next_open = html.find(open_tag_start, pos)
        next_close = html.find(close_tag, pos)
        
        if next_close == -1:
            break
            
        if next_open != -1 and next_open < next_close:
            after_char = html[next_open + len(open_tag_start):next_open + len(open_tag_start) + 1]
            if after_char in (' ', '>', '/'):
                depth += 1
                pos = next_open + len(open_tag_start)
            else:
                pos = next_open + 1
        else:
            depth -= 1
            pos = next_close + len(close_tag)
            if depth == 0:
                return html[start_idx:pos]
    return ""

def extract_element_by_id(html, id_val):
    if not html:
        return ""
    pattern = rf'<([^>\s]+)\s+[^>]*id=["\']{id_val}["\'][^>]*>'
    match = re.search(pattern, html, re.IGNORECASE)
    if not match:
        return ""
    start_idx = match.start()
    tag_name = match.group(1)
    
    depth = 0
    pos = start_idx
    open_tag_start = f"<{tag_name}"
    close_tag = f"</{tag_name}>"
    
    while pos < len(html):
        next_open = html.find(open_tag_start, pos)
        next_close = html.find(close_tag, pos)
        
        if next_close == -1:
            break
            
        if next_open != -1 and next_open < next_close:
            after_char = html[next_open + len(open_tag_start):next_open + len(open_tag_start) + 1]
            if after_char in (' ', '>', '/'):
                depth += 1
                pos = next_open + len(open_tag_start)
            else:
                pos = next_open + 1
        else:
            depth -= 1
            pos = next_close + len(close_tag)
            if depth == 0:
                return html[start_idx:pos]
    return ""

def extract_main_content(html):
    if not html:
        return ""
    content = extract_element_by_class_substring(html, "markdown")
    if not content or not content.strip():
        content = extract_element_by_id(html, "main-content")
    return content

def fetch_and_parse_page(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error downloading {url}: {e}", file=sys.stderr)
        return None

    main_content = extract_main_content(html)

    # Concatenate NextJS self.__next_f.push scripts
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
    
    # Locate numeric ID in the URL to find the exact queryKey block
    bounty_id_match = re.search(r'/bug-bounties/(\d+)', url)
    if not bounty_id_match:
        return None
    bounty_id_str = bounty_id_match.group(1)
    
    key_pattern = f'"queryKey":["bug-bounty","{bounty_id_str}"'
    idx = full_stream.find(key_pattern)
    if idx == -1:
        # Fallback to general search
        idx = full_stream.find('"queryKey":["bug-bounty"')
        
    if idx == -1:
        print(f"Could not find bug-bounty queryKey in stream for {url}", file=sys.stderr)
        return None
        
    start_idx = full_stream.rfind('{"state":', 0, idx)
    if start_idx == -1:
        print(f"Could not find start of state object in stream for {url}", file=sys.stderr)
        return None
        
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
            
    clean_json_str = full_stream[start_idx:start_idx+json_len]
    try:
        query_data = json.loads(clean_json_str)
        bounty_data = query_data.get("state", {}).get("data", {})
        if not bounty_data:
            print(f"Empty data block extracted for {url}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Failed to parse query state JSON for {url}: {e}", file=sys.stderr)
        return None

    # Resolve description text token
    desc_token = bounty_data.get("description")
    description = ""
    if desc_token and desc_token.startswith("$"):
        token_num = desc_token[1:]
        desc_match = re.search(rf'{token_num}:[^,\n]+,(.*?(?=\n\d+:|\n\]|$))', full_stream, re.DOTALL)
        if desc_match:
            desc_text = desc_match.group(1)
            try:
                description = json.loads(f'"{desc_text}"')
            except:
                description = desc_text
        else:
            # Fallback scan for description
            desc_match = re.search(r'(\d+):[^,\n]+,(# About.*?(?=\n\d+:|\n\]|$))', full_stream, re.DOTALL)
            if desc_match:
                try:
                    description = json.loads(f'"{desc_match.group(2)}"')
                except:
                    description = desc_match.group(2)
    else:
        description = desc_token or ""

    if not main_content or not main_content.strip():
        html_desc = markdown.markdown(description)
        main_content = f'<div class="markdown">{html_desc}</div>'

    bounty_data["resolved_description"] = description
    bounty_data["main_content"] = main_content
    return bounty_data

def insert_or_replace_project(cursor, bounty_data, csv_info):
    title = bounty_data.get("title") or csv_info.get("title", "Unknown")
    bounty_id = bounty_data.get("id")
    cursor.execute("SELECT slug FROM projects WHERE id = ?", (bounty_id,))
    row = cursor.fetchone()
    if row:
        slug = row[0]
    else:
        slug = sluggify(title)
        if not slug:
            slug = str(bounty_id)
        cursor.execute("SELECT slug FROM projects WHERE slug = ? AND id != ?", (slug, bounty_id))
        if cursor.fetchone():
            slug = f"{slug}-{bounty_id}"
        
    payout = bounty_data.get("payout")
    currency = bounty_data.get("displayCurrency") or "USDC"
    
    # Parse rewards pool string from CSV
    rewards_pool_val = None
    csv_pool_str = csv_info.get("rewards_pool_str", "")
    if csv_pool_str:
        num_match = re.search(r'([\d,]+)', csv_pool_str)
        if num_match:
            rewards_pool_val = safe_int(num_match.group(1))
            
    # Format timestamps
    launch_date = None
    updated_date = None
    if bounty_data.get("liveSinceTimestamp"):
        launch_date = datetime.fromtimestamp(bounty_data.get("liveSinceTimestamp")).isoformat()
    if bounty_data.get("lastUpdatedTimestamp"):
        updated_date = datetime.fromtimestamp(bounty_data.get("lastUpdatedTimestamp")).isoformat()

    description = bounty_data.get("resolved_description", "")
    website_url = extract_website_url(description)
    github_url = extract_github_url(description)
    
    proj_row = (
        slug,
        bounty_data.get("id"),
        title,
        description,
        website_url,
        github_url,
        bounty_data.get("logoURL") or csv_info.get("logo_url"),
        launch_date,
        updated_date,
        payout,
        rewards_pool_val,
        currency,
        bounty_data.get("main_content", ""),
        json.dumps(bounty_data)
    )

    cursor.execute("""
        INSERT OR REPLACE INTO projects (
            slug, id, project, description, website_url, github_url, logo,
            launch_date, updated_date, max_bounty, rewards_pool, rewards_token, main_content, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, proj_row)

    # Clear existing child records
    cursor.execute("DELETE FROM assets WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM rewards WHERE project_slug = ?", (slug,))
    cursor.execute("DELETE FROM project_lists WHERE project_slug = ?", (slug,))

    # Ingest assets (contracts and repositories)
    scope = bounty_data.get("scope", {})
    contracts = scope.get("contracts", [])
    if isinstance(contracts, list):
        for network_group in contracts:
            if isinstance(network_group, list) and len(network_group) >= 2:
                network_name = network_group[0]
                contract_list = network_group[1]
                if isinstance(contract_list, list):
                    for contract in contract_list:
                        addr = contract.get("address")
                        if addr:
                            cursor.execute("""
                                INSERT INTO assets (project_slug, id, url, type, description)
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                slug,
                                addr,
                                f"https://etherscan.io/address/{addr}" if network_name == "ETHEREUM" else "",
                                "contract",
                                network_name
                            ))

    non_contracts = scope.get("nonContracts", [])
    if isinstance(non_contracts, list):
        for repo in non_contracts:
            repo_name = repo.get("repoName")
            if repo_name:
                cursor.execute("""
                    INSERT INTO assets (project_slug, id, url, type, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    slug,
                    repo_name,
                    f"https://github.com/{repo_name}",
                    "repository",
                    f"branch: {repo.get('branchName')}, commit: {repo.get('commitHash')}"
                ))

    # Ingest rewards from severity list and markdown parser
    markdown_rewards = parse_rewards_from_markdown(description)
    if markdown_rewards:
        for r_idx, r in enumerate(markdown_rewards):
            cursor.execute("""
                INSERT INTO rewards (project_slug, id, level, payout, min_reward, max_reward)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (slug, r_idx, r["level"], r["payout"], r["min_reward"], r["max_reward"]))
    else:
        # Fallback to severity list in JSON
        for sev in bounty_data.get("severities", []):
            cursor.execute("""
                INSERT INTO rewards (project_slug, id, level, payout, min_reward, max_reward)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                slug,
                sev.get("severityId"),
                sev.get("severityName"),
                f"Deposit: {sev.get('depositAmount')}",
                None,
                sev.get("depositAmount")
            ))

    # Ingest categories
    for cat in bounty_data.get("categories", []):
        cat_name = cat.get("name")
        if cat_name:
            cursor.execute("""
                INSERT INTO project_lists (project_slug, list_name, value)
                VALUES (?, ?, ?)
            """, (slug, "category", cat_name))

def sync_db(db_path, csv_path):
    url_web = 'https://audits.sherlock.xyz/bug-bounties'
    headers_web = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'max-age=0',
        'cookie': 'wagmi.store={"state":{"connections":{"__type":"Map","value":[]},"chainId":1,"current":null},"version":2}; pdfcc=1; _ga=GA1.1.648954890.1784030401; _ga_GDYH0NV24Z=GS2.1.s1784030400$o1$g0$t1784030400$j60$l0$h0',
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

    csv_projects = []

    # 1. Scrape from webpage to extract the programs
    print("Scraping Sherlock programs from bug-bounties page...")
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
                    if isinstance(q_key, list) and len(q_key) > 1 and q_key[0] == 'bug-bounties' and q_key[1] == 'all':
                        q_data = q.get("state", {}).get("data", {})
                        if isinstance(q_data, dict) and "items" in q_data:
                            for item in q_data["items"]:
                                bounty_id = item.get("id")
                                if not bounty_id:
                                    continue
                                
                                ts = item.get("lastUpdatedTimestamp")
                                date_str = ""
                                if ts:
                                    if ts > 10000000000:
                                        ts = ts / 1000
                                    date_str = datetime.fromtimestamp(ts).strftime('%b %d, %Y')
                                
                                last_updated_str = f"Last Updated • {date_str}" if date_str else ""
                                
                                payout = item.get("payout")
                                currency = item.get("displayCurrency") or "USDC"
                                payout_formatted = ""
                                if payout is not None:
                                    payout_formatted = f"{int(payout):,}"
                                rewards_pool_str = f"{payout_formatted} {currency}" if payout_formatted else ""

                                csv_projects.append({
                                    "url": f"https://audits.sherlock.xyz/bug-bounties/{bounty_id}",
                                    "logo_url": item.get("logoURL"),
                                    "title": item.get("title") or "Unknown",
                                    "last_updated_str": last_updated_str,
                                    "rewards_pool_str": rewards_pool_str,
                                    "date_str": date_str
                                })
            except Exception:
                pass
        print(f"Extracted {len(csv_projects)} programs from webpage NextJS stream.")
    except Exception as e:
        print(f"Error parsing opportunities page: {e}", file=sys.stderr)

    # Fallback to local CSV if scraping returned no results
    if not csv_projects:
        if csv_path and os.path.exists(csv_path):
            print(f"Reading Sherlock pages list from fallback CSV: {csv_path}...")
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)
                for row in reader:
                    if len(row) >= 6:
                        csv_projects.append({
                            "url": row[0],
                            "logo_url": row[1],
                            "title": row[2],
                            "last_updated_str": row[3],
                            "rewards_pool_str": row[4],
                            "date_str": row[5]
                        })
        else:
            print("Error: No projects extracted and CSV fallback is unavailable.", file=sys.stderr)
            return

    print(f"Found {len(csv_projects)} projects to sync. Starting scraping...")
    
    try:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        init_db_schema(cursor)
        
        results = [None] * len(csv_projects)
        
        def worker(idx, csv_info):
            url = csv_info["url"]
            bounty_data = fetch_and_parse_page(url)
            return idx, bounty_data
            
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_idx = {executor.submit(worker, idx, csv_info): idx for idx, csv_info in enumerate(csv_projects)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    _, bounty_data = future.result()
                    results[idx] = bounty_data
                    if bounty_data:
                        print(f"[{idx+1}/{len(csv_projects)}] Successfully scraped {csv_projects[idx]['url']}")
                    else:
                        print(f"[{idx+1}/{len(csv_projects)}] Failed to scrape {csv_projects[idx]['url']}", file=sys.stderr)
                except Exception as e:
                    print(f"[{idx+1}/{len(csv_projects)}] Exception scraping {csv_projects[idx]['url']}: {e}", file=sys.stderr)

        success_count = 0
        for idx, csv_info in enumerate(csv_projects):
            bounty_data = results[idx]
            if bounty_data:
                insert_or_replace_project(cursor, bounty_data, csv_info)
                success_count += 1
                
        conn.commit()
        conn.close()
        print(f"Sync complete. Successfully ingested {success_count}/{len(csv_projects)} projects.")
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
            return [r[0] for r in rows]
        except:
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
        except:
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
        description="Is like jq for Sherlock Bug Bounty. Search, filter and map structured data about bug bounty programs with ease.",
        epilog="""Examples:
  python sbb.py
  python sbb.py inverse-finance
  python sbb.py inverse-finance scope
  python sbb.py inverse-finance resolved_description
  python sbb.py --sync
  python sbb.py --db-query "SELECT slug, max_bounty, rewards_token FROM projects WHERE max_bounty > 200000"
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
        help='Synchronize database by scraping Sherlock pages'
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
        '--csv-path',
        type=str,
        default='sherlock.csv',
        help='Path to Sherlock CSV file (default: sherlock.csv)'
    )
    
    args = parser.parse_args()

    if args.sync:
        sync_db(args.db_path, args.csv_path)
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
