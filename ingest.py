# ingest.py
import os
import sys
import json
import time
import re
import urllib.request
import subprocess
from pathlib import Path
import sqlite3
import db

# Helper to load .env file
def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key not in os.environ:
                        os.environ[key] = val

load_env()

SOLODIT_API_KEY = os.environ.get("SOLODIT_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

WORKSPACE_DIR = Path(__file__).parent.resolve()
REPOS_DIR = WORKSPACE_DIR / "vulnerability_repos"
CACHE_DIR = REPOS_DIR / "findings_cache"
SOL_CACHE_DIR = REPOS_DIR / "solidity_cache"

def save_finding_to_disk_cache(finding_data):
    """Saves a normalized finding as a plain text JSON file on disk."""
    try:
        pool_name = finding_data.get("source_pool", "misc")
        source_repo = finding_data.get("source_repo", "").replace("/", "_") or "general"
        target_dir = CACHE_DIR / pool_name / source_repo
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{finding_data['id']}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(finding_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass

def get_repo_cached_findings(source_pool, repo_name):
    """Loads all plain text cached findings for a given repository from disk if present."""
    source_repo_clean = repo_name.replace("/", "_")
    target_dir = CACHE_DIR / source_pool / source_repo_clean
    if not target_dir.exists():
        return []
    findings = []
    for json_file in target_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
                findings.append(data)
        except Exception:
            pass
    return findings

def make_request(url, headers=None, data=None, method="GET", timeout=30):
    """Utility function to make HTTP requests with proper headers and error handling."""
    if headers is None:
        headers = {}
    
    req_data = None
    if data is not None:
        if isinstance(data, dict) or isinstance(data, list):
            req_data = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            req_data = data
            
    req = urllib.request.Request(url, headers=headers, data=req_data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"HTTP Error {e.code} for URL {url}: {body[:500]}")
        raise e
    except Exception as e:
        print(f"Error requesting URL {url}: {e}")
        raise e

# ==========================================
# PHASE 1: SOLODIT INTEGRATION
# ==========================================

def sparse_checkout_solodit_content():
    """Performs a shallow sparse checkout of the solodit/solodit_content repository reports folder."""
    target_dir = REPOS_DIR / "solodit_content"
    print(f"Starting Solodit Content sparse checkout at {target_dir}...")
    
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["git", "init"], cwd=str(target_dir), check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/solodit/solodit_content.git"], cwd=str(target_dir), check=True)
            subprocess.run(["git", "config", "core.sparseCheckout", "true"], cwd=str(target_dir), check=True)
            
            # Setup sparse checkout path
            sparse_file = target_dir / ".git" / "info" / "sparse-checkout"
            sparse_file.parent.mkdir(parents=True, exist_ok=True)
            with open(sparse_file, "w") as f:
                f.write("reports/\n")
            
            # Pull from default branch (master or main)
            # Try main first, fallback to master
            try:
                subprocess.run(["git", "pull", "--depth", "1", "origin", "main"], cwd=str(target_dir), check=True)
            except subprocess.CalledProcessError:
                subprocess.run(["git", "pull", "--depth", "1", "origin", "master"], cwd=str(target_dir), check=True)
        except Exception as e:
            print(f"Failed to sparse clone Solodit Content repo: {e}")
            return False
    else:
        print("Solodit Content directory already exists, pulling updates...")
        try:
            try:
                subprocess.run(["git", "pull", "origin", "main"], cwd=str(target_dir), check=True)
            except subprocess.CalledProcessError:
                subprocess.run(["git", "pull", "origin", "master"], cwd=str(target_dir), check=True)
        except Exception as e:
            print(f"Failed to update Solodit Content repo: {e}")
    return True

def parse_solodit_markdown_reports():
    """Parses markdown report files inside solodit_content/reports/."""
    reports_dir = REPOS_DIR / "solodit_content" / "reports"
    if not reports_dir.exists():
        print("Solodit reports directory not found.")
        return 0
    
    findings_count = 0
    print("Parsing Solodit Content markdown reports...")
    
    # Recursively find markdown files
    md_files = list(reports_dir.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files in reports/.")
    
    solodit_findings = []
    
    for md_path in md_files:
        auditor = md_path.parent.name
        filename = md_path.name
        
        date_protocol_match = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", filename)
        if date_protocol_match:
            date_str = date_protocol_match.group(1)
            protocol = date_protocol_match.group(2)
        else:
            date_str = "Unknown"
            protocol = filename.replace(".md", "")
            
        try:
            with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                
            pattern = r"(?m)^(?:#|##)\s+(Critical Risk|High Risk|Medium Risk|Low Risk|Gas Optimizations|Informational)"
            sections = re.split(pattern, content)
            
            if len(sections) < 2:
                continue
                
            for i in range(1, len(sections), 2):
                severity = sections[i]
                sec_content = sections[i+1]
                
                finding_splits = re.split(r"(?m)^###\s+(.+)$", sec_content)
                if len(finding_splits) < 2:
                    continue
                    
                for j in range(1, len(finding_splits), 2):
                    title = finding_splits[j].strip()
                    desc = finding_splits[j+1].strip()
                    
                    finding_id = f"solodit-content-{auditor}-{protocol}-{severity}-{title[:30]}".replace(" ", "-").lower()
                    finding_id = re.sub(r"[^a-z0-9_-]", "", finding_id)
                    
                    finding_entry = {
                        "id": finding_id,
                        "source_pool": "solodit",
                        "protocol_name": protocol,
                        "title": f"[{severity}] {title}",
                        "content_markdown": desc,
                        "severity": severity,
                        "loss_usd": None,
                        "file_paths": [],
                        "fix_commit": None,
                        "root_cause_keywords": [severity, auditor]
                    }
                    save_finding_to_disk_cache(finding_entry)
                    solodit_findings.append(finding_entry)
        except Exception as e:
            print(f"Error parsing file {md_path}: {e}")
            
    db.insert_findings_batch(solodit_findings)
    findings_count = len(solodit_findings)
    print(f"Parsed {findings_count} findings from Solodit Content markdown reports.")
    return findings_count

def fetch_solodit_api_findings(tag_slugs=None):
    """Queries Solodit REST API for findings, paginating by tag slugs until no findings remain."""
    if not SOLODIT_API_KEY:
        print("SOLODIT_API_KEY environment variable is missing. Skipping Solodit API ingestion.")
        return 0
    
    if tag_slugs is None:
        tag_slugs = ["Reentrancy", "Access Control"]
        
    api_url = "https://solodit.cyfrin.io/api/v1/solodit/findings"
    headers = {
        "X-Cyfrin-API-Key": SOLODIT_API_KEY,
        "Content-Type": "application/json"
    }
    
    findings_count = 0
    print(f"Fetching findings from Solodit REST API for tags: {tag_slugs}...")
    
    for tag in tag_slugs:
        page = 1
        while True:
            payload = {
                "page": page,
                "pageSize": 20,
                "filters": {
                    "tags": [{"value": tag}]
                }
            }
            try:
                print(f"Querying Solodit API for tag '{tag}', page {page}...")
                body_bytes, resp_headers = make_request(api_url, headers=headers, data=payload, method="POST")
                response = json.loads(body_bytes.decode("utf-8"))
                
                findings = response.get("findings", [])
                if not findings:
                    print(f"No more findings returned for tag '{tag}' starting from page {page}.")
                    break
                    
                for f in findings:
                    finding_id = f"solodit-api-{f['id']}"
                    tags_extracted = [t["tags_tag"]["title"] for t in f.get("issues_issuetagscore", []) if "tags_tag" in t]
                    
                    finding_data = {
                        "id": finding_id,
                        "source_pool": "solodit",
                        "protocol_name": f.get("protocol_name"),
                        "title": f.get("title"),
                        "content_markdown": f.get("content"),
                        "severity": f.get("impact"),
                        "loss_usd": None,
                        "file_paths": [],
                        "fix_commit": f.get("github_link") or f.get("source_link"),
                        "root_cause_keywords": tags_extracted
                    }
                    save_finding_to_disk_cache(finding_data)
                    db.insert_finding(finding_data)
                    findings_count += 1
                
                page += 1
                # Respect rate limits: 20 requests per 60 seconds (1 request per 3 seconds)
                time.sleep(3)
            except Exception as e:
                print(f"Error querying Solodit API for tag {tag} at page {page}: {e}")
                break
                
    print(f"Ingested {findings_count} findings from Solodit REST API.")
    return findings_count

# ==========================================
# PHASE 2: CODE4RENA SCRAPING ARCHITECTURE
# ==========================================

def run_github_graphql(query_str, variables=None):
    """Executes a GraphQL query against the GitHub API."""
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN is required for Code4rena scraping.")
        
    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Antigravity-Pipeline"
    }
    payload = {"query": query_str}
    if variables:
        payload["variables"] = variables
        
    body_bytes, _ = make_request(url, headers=headers, data=payload, method="POST")
    return json.loads(body_bytes.decode("utf-8"))

def extract_sol_paths(body_text):
    """Parses text body to extract unique smart contract file paths ending in .sol."""
    if not body_text:
        return []
    
    # Extract anything that looks like a path or URL ending in .sol
    # We will match characters including slashes, colons, words, hyphens, and dots.
    raw_paths = re.findall(r"[\w\d\-_\.\/\\:]+\.sol\b", body_text)
    
    resolved = []
    for p in raw_paths:
        p_clean = p.strip("`*\"' ()[]{}").replace("\\", "/")
        
        # If it is a full or partial URL pointing to a file on GitHub, let's extract the relative path:
        # e.g., https://github.com/owner/repo/blob/branch/path/to/file.sol
        # or github.com/owner/repo/blob/branch/path/to/file.sol
        if "github.com/" in p_clean:
            # Match after the branch name (e.g. /blob/[branch]/ or /tree/[branch]/ or /raw/[branch]/)
            match = re.search(r"github\.com/[^/]+/[^/]+/(?:blob|tree|raw)/[^/]+/(.+\.sol)", p_clean)
            if match:
                p_clean = match.group(1)
            else:
                # Fallback: remove the domain/owner/repo if it's there
                p_clean = re.sub(r"^(?:https?:\/\/)?(?:www\.)?github\.com\/[^\/]+\/[^\/]+\/?", "", p_clean)
                
        # Clean potential double slashes at the start
        p_clean = p_clean.lstrip("/")
        
        # Avoid adding generic files or library names that don't have actual paths (like SafeERC20.sol) if we already have detailed paths,
        # but let's keep them if they are valid paths or the only ones.
        if p_clean and p_clean not in resolved:
            resolved.append(p_clean)
            
    return resolved

# Globally cache repository trees to avoid redundant API queries
repo_trees = {}

def get_repo_file_tree(owner, repo):
    """Fetches the recursive file tree of the repository from GitHub API and returns a list of paths."""
    key = f"{owner}/{repo}"
    if key in repo_trees:
        return repo_trees[key]
        
    headers = {
        "User-Agent": "Antigravity-Pipeline"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
        
    for branch in ["main", "master"]:
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        try:
            body_bytes, _ = make_request(url, headers=headers)
            tree_data = json.loads(body_bytes.decode("utf-8"))
            paths = [item["path"] for item in tree_data.get("tree", []) if item.get("type") == "blob"]
            repo_trees[key] = (branch, paths)
            return branch, paths
        except Exception as e:
            print(f"Failed to fetch file tree for {key} on branch {branch}: {e}")
            
    repo_trees[key] = (None, [])
    return None, []

def fetch_raw_solidity_files(owner, repo, file_paths):
    """Fetches raw solidity file content from raw.githubusercontent.com for a list of file paths in parallel, using local disk cache if present."""
    if not file_paths:
        return ""
        
    branch, tree_paths = get_repo_file_tree(owner, repo)
    if not branch:
        branch = "main"
        
    path_map = {}
    for tp in tree_paths:
        filename = tp.split("/")[-1]
        path_map[filename.lower()] = tp
        
    harvested_blocks = []
    resolved_paths_downloaded = set()
    
    def fetch_single_file(fp):
        target_path = fp
        filename_key = fp.split("/")[-1].lower()
        if fp not in tree_paths and filename_key in path_map:
            target_path = path_map[filename_key]
        if target_path in resolved_paths_downloaded:
            return None
        resolved_paths_downloaded.add(target_path)
        
        # Check local disk cache for solidity source code
        clean_name = re.sub(r"[^a-zA-Z0-9_\.-]", "_", f"{owner}_{repo}_{target_path}")
        sol_cache_file = SOL_CACHE_DIR / clean_name
        if sol_cache_file.exists():
            try:
                with open(sol_cache_file, "r", encoding="utf-8", errors="ignore") as sf:
                    content = sf.read()
                if content:
                    return f"// File: {target_path}\n{content}\n"
            except Exception:
                pass
        
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{target_path}"
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        content = ""
        try:
            content_bytes, _ = make_request(raw_url, headers=headers)
            content = content_bytes.decode("utf-8", errors="ignore")
        except Exception:
            if branch == "main":
                try:
                    raw_url_master = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{target_path}"
                    content_bytes, _ = make_request(raw_url_master, headers=headers)
                    content = content_bytes.decode("utf-8", errors="ignore")
                except Exception:
                    pass
        if content:
            try:
                SOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                with open(sol_cache_file, "w", encoding="utf-8") as sf:
                    sf.write(content)
            except Exception:
                pass
            return f"// File: {target_path}\n{content}\n"
        return None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, len(file_paths))) as executor:
        results = executor.map(fetch_single_file, file_paths)
        for r in results:
            if r:
                harvested_blocks.append(r)
                
    return "\n".join(harvested_blocks) if harvested_blocks else ""

def get_org_repos_cursor_paginated(org_name, suffix):
    """Fetch all repositories matching an organization and suffix recursively using cursor-based pagination."""
    repos = []
    has_next = True
    cursor = None
    
    while has_next:
        cursor_str = f', after: "{cursor}"' if cursor else ""
        query = f"""
        query {{
          organization(login: "{org_name}") {{
            repositories(first: 100{cursor_str}) {{
              pageInfo {{
                hasNextPage
                endCursor
              }}
              nodes {{
                name
              }}
            }}
          }}
        }}
        """
        try:
            res = run_github_graphql(query)
            org_data = res.get("data", {}).get("organization")
            if not org_data:
                print(f"Failed to get organization data for {org_name}: {res}")
                break
                
            repo_nodes = org_data.get("repositories", {}).get("nodes", [])
            for r in repo_nodes:
                name = r["name"]
                if name.endswith(suffix):
                    repos.append(name)
                    
            page_info = org_data.get("repositories", {}).get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")
        except Exception as e:
            print(f"Error fetching paginated repos for {org_name}: {e}")
            break
            
    return repos

import threading

def fetch_code4rena_findings():
    """Scrapes Code4rena findings repositories using high-concurrency parallel threads, disk caching, and batch inserts."""
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN environment variable is missing. Skipping Code4rena ingestion.")
        return 0
        
    print("Scraping Code4rena repositories recursively in parallel...")
    repos = get_org_repos_cursor_paginated("code-423n4", "-findings")
    print(f"Found {len(repos)} Code4rena findings repositories.")
    
    total_count = [0]
    count_lock = threading.Lock()
    
    def process_repo(repo):
        source_repo = repo.replace("-findings", "")
        source_repo_key = f"code-423n4/{source_repo}"
        
        # 1. Check local plain text disk cache first!
        cached_findings = get_repo_cached_findings("code4rena", source_repo_key)
        if cached_findings:
            db.insert_findings_batch(cached_findings)
            with count_lock:
                total_count[0] += len(cached_findings)
                print(f"Loaded {len(cached_findings)} findings from disk cache for {repo}. (Total Code4rena: {total_count[0]})")
            return len(cached_findings)

        if db.is_repo_already_processed(source_repo_key):
            return 0
            
        protocol_match = re.match(r"^\d{4}-\d{2}-(.+)-findings$", repo)
        protocol_name = protocol_match.group(1) if protocol_match else repo.replace("-findings", "")
        
        mitigation_repo = repo.replace("-findings", "-mitigation")
        mitigation_map = {}
        mitigation_query = f"""
        query {{
          repository(owner: "code-423n4", name: "{mitigation_repo}") {{
            object(expression: "main:README.md") {{
              ... on Blob {{
                text
              }}
            }}
          }}
        }}
        """
        try:
            mit_res = run_github_graphql(mitigation_query)
            repo_obj = mit_res.get("data", {}).get("repository")
            if not repo_obj:
                mit_res = run_github_graphql(mitigation_query.replace("main:README.md", "master:README.md"))
                repo_obj = mit_res.get("data", {}).get("repository")
                
            if repo_obj and repo_obj.get("object"):
                readme_text = repo_obj["object"]["text"]
                for row in readme_text.split("\n"):
                    if "|" in row and ("issues/" in row or "commit/" in row or "pull/" in row):
                        urls = re.findall(r"https://github\.com/[^\s\)\|\s]+", row)
                        issue_urls = [u for u in urls if "/issues/" in u]
                        fix_urls = [u for u in urls if "/pull/" in u or "/commit/" in u]
                        if issue_urls and fix_urls:
                            for issue_url in issue_urls:
                                num_match = re.search(r"/issues/(\d+)", issue_url)
                                if num_match:
                                    mitigation_map[int(num_match.group(1))] = fix_urls[0]
        except Exception:
            pass
            
        has_next_issues = True
        issues_cursor = None
        repo_findings = []
        
        while has_next_issues:
            cursor_str = f', after: "{issues_cursor}"' if issues_cursor else ""
            issues_query = f"""
            query {{
              repository(owner: "code-423n4", name: "{repo}") {{
                issues(first: 100{cursor_str}, orderBy: {{field: CREATED_AT, direction: DESC}}) {{
                  pageInfo {{
                    hasNextPage
                    endCursor
                  }}
                  nodes {{
                    number
                    title
                    body
                    labels(first: 10) {{
                      nodes {{
                        name
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """
            try:
                issues_res = run_github_graphql(issues_query)
                repo_data = issues_res.get("data", {}).get("repository")
                if not repo_data:
                    break
                issues_page = repo_data.get("issues", {})
                issues_nodes = issues_page.get("nodes", [])
                
                for issue in issues_nodes:
                    labels = [l["name"] for l in issue["labels"]["nodes"]]
                    severity = None
                    for l in labels:
                        if "High Risk" in l or "3 (" in l:
                            severity = "High"
                        elif "Med Risk" in l or "2 (" in l:
                            severity = "Medium"
                    if not severity:
                        continue
                        
                    issue_num = issue["number"]
                    finding_id = f"c4-{repo}-{issue_num}"
                    fix_commit = mitigation_map.get(issue_num)
                    body_text = issue["body"] or ""
                    sol_paths = extract_sol_paths(body_text)
                    raw_solidity_code = fetch_raw_solidity_files("code-423n4", source_repo, sol_paths)
                    
                    finding_entry = {
                        "id": finding_id,
                        "source_pool": "code4rena",
                        "protocol_name": protocol_name,
                        "title": issue["title"],
                        "content_markdown": body_text,
                        "severity": severity,
                        "loss_usd": None,
                        "file_paths": sol_paths,
                        "fix_commit": fix_commit,
                        "root_cause_keywords": labels,
                        "raw_solidity_code": raw_solidity_code,
                        "source_repo": f"code-423n4/{source_repo}"
                    }
                    save_finding_to_disk_cache(finding_entry)
                    repo_findings.append(finding_entry)
                    
                page_info = issues_page.get("pageInfo", {})
                has_next_issues = page_info.get("hasNextPage", False)
                issues_cursor = page_info.get("endCursor")
            except Exception as e:
                print(f"Error querying issues for repo {repo}: {e}")
                break
                
        if repo_findings:
            db.insert_findings_batch(repo_findings)
            with count_lock:
                total_count[0] += len(repo_findings)
                print(f"Ingested {len(repo_findings)} findings from {repo}. (Total Code4rena: {total_count[0]})")
        return len(repo_findings)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=16) as executor:
        executor.map(process_repo, repos)
        
    print(f"Ingested {total_count[0]} findings from Code4rena.")
    return total_count[0]

def fetch_sherlock_findings():
    """Scrapes Sherlock judging repositories using high-concurrency parallel threads, disk caching, and batch inserts."""
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN environment variable is missing. Skipping Sherlock ingestion.")
        return 0
        
    print("Scraping Sherlock judging repositories recursively in parallel...")
    repos = get_org_repos_cursor_paginated("sherlock-audit", "-judging")
    print(f"Found {len(repos)} Sherlock judging repositories.")
    
    total_count = [0]
    count_lock = threading.Lock()
    
    def process_repo(repo):
        source_repo = repo.replace("-judging", "")
        source_repo_key = f"sherlock-audit/{source_repo}"
        
        # 1. Check local plain text disk cache first!
        cached_findings = get_repo_cached_findings("sherlock", source_repo_key)
        if cached_findings:
            db.insert_findings_batch(cached_findings)
            with count_lock:
                total_count[0] += len(cached_findings)
                print(f"Loaded {len(cached_findings)} findings from disk cache for {repo}. (Total Sherlock: {total_count[0]})")
            return len(cached_findings)

        if db.is_repo_already_processed(source_repo_key):
            return 0
            
        protocol_match = re.match(r"^\d{4}-\d{2}-(.+)-judging$", repo)
        protocol_name = protocol_match.group(1) if protocol_match else repo.replace("-judging", "")
        
        has_next_issues = True
        issues_cursor = None
        repo_findings = []
        
        while has_next_issues:
            cursor_str = f', after: "{issues_cursor}"' if issues_cursor else ""
            issues_query = f"""
            query {{
              repository(owner: "sherlock-audit", name: "{repo}") {{
                issues(first: 100{cursor_str}, orderBy: {{field: CREATED_AT, direction: DESC}}) {{
                  pageInfo {{
                    hasNextPage
                    endCursor
                  }}
                  nodes {{
                    number
                    title
                    body
                    labels(first: 10) {{
                      nodes {{
                        name
                      }}
                    }}
                  }}
                }}
              }}
            }}
            """
            try:
                issues_res = run_github_graphql(issues_query)
                repo_data = issues_res.get("data", {}).get("repository")
                if not repo_data:
                    break
                issues_page = repo_data.get("issues", {})
                issues_nodes = issues_page.get("nodes", [])
                
                for issue in issues_nodes:
                    labels = [l["name"] for l in issue["labels"]["nodes"]]
                    severity = None
                    for l in labels:
                        if l.strip().lower() == "high":
                            severity = "High"
                        elif l.strip().lower() == "medium":
                            severity = "Medium"
                    if not severity:
                        continue
                        
                    issue_num = issue["number"]
                    finding_id = f"sherlock-{repo}-{issue_num}"
                    body_text = issue["body"] or ""
                    sol_paths = extract_sol_paths(body_text)
                    raw_solidity_code = fetch_raw_solidity_files("sherlock-audit", source_repo, sol_paths)
                    
                    finding_entry = {
                        "id": finding_id,
                        "source_pool": "sherlock",
                        "protocol_name": protocol_name,
                        "title": issue["title"],
                        "content_markdown": body_text,
                        "severity": severity,
                        "loss_usd": None,
                        "file_paths": sol_paths,
                        "fix_commit": None,
                        "root_cause_keywords": labels,
                        "raw_solidity_code": raw_solidity_code,
                        "source_repo": f"sherlock-audit/{source_repo}"
                    }
                    save_finding_to_disk_cache(finding_entry)
                    repo_findings.append(finding_entry)
                    
                page_info = issues_page.get("pageInfo", {})
                has_next_issues = page_info.get("hasNextPage", False)
                issues_cursor = page_info.get("endCursor")
            except Exception as e:
                print(f"Error querying issues for Sherlock repo {repo}: {e}")
                break
                
        if repo_findings:
            db.insert_findings_batch(repo_findings)
            with count_lock:
                total_count[0] += len(repo_findings)
                print(f"Ingested {len(repo_findings)} findings from {repo}. (Total Sherlock: {total_count[0]})")
        return len(repo_findings)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=16) as executor:
        executor.map(process_repo, repos)
        
    print(f"Ingested {total_count[0]} findings from Sherlock.")
    return total_count[0]

# ==========================================
# PHASE 3: DEFIHACKLABS TARGET PROCESSING
# ==========================================

def ingest_defihacklabs():
    """Clones DeFiHackLabs and processes exploit files and incident explorer records."""
    target_dir = REPOS_DIR / "defihacklabs"
    print(f"Starting DeFiHackLabs ingestion at {target_dir}...")
    
    # 1. Clone DeFiHackLabs repository
    if not target_dir.exists():
        print("Cloning DeFiHackLabs repository (shallow)...")
        try:
            subprocess.run(["git", "clone", "--depth", "1", "https://github.com/SunWeb3Sec/DeFiHackLabs.git", str(target_dir)], check=True)
            print("Initializing submodules...")
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], cwd=str(target_dir), check=True)
        except Exception as e:
            print(f"Failed to clone DeFiHackLabs repository: {e}")
            return 0
    else:
        print("DeFiHackLabs repository already exists. Pulling updates...")
        try:
            try:
                subprocess.run(["git", "pull", "origin", "main"], cwd=str(target_dir), check=True)
            except subprocess.CalledProcessError:
                subprocess.run(["git", "pull", "origin", "master"], cwd=str(target_dir), check=True)
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], cwd=str(target_dir), check=True)
        except Exception as e:
            print(f"Failed to update DeFiHackLabs: {e}")
            
    # 2. Fetch incidents.json from Incident Explorer
    incidents_url = "https://raw.githubusercontent.com/SunWeb3Sec/DeFiHackLabs-Incident-Explorer/main/incidents.json"
    print(f"Fetching DeFiHackLabs companion incident database from {incidents_url}...")
    
    try:
        incidents_bytes, _ = make_request(incidents_url)
        incidents = json.loads(incidents_bytes.decode("utf-8"))
        print(f"Retrieved {len(incidents)} incidents from DeFiHackLabs Incident Explorer.")
    except Exception as e:
        print(f"Failed to retrieve incidents database: {e}")
        return 0
        
    findings_count = 0
    
    # 3. Process incidents and map them to physical test files in src/test/
    for inc in incidents:
        protocol_name = inc.get("name", "Unknown")
        attack_type = inc.get("type", "Unknown")
        date_str = str(inc.get("date", "Unknown"))
        chain = inc.get("chain", "Unknown")
        lost_amount = inc.get("Lost", 0.0)
        loss_type = inc.get("lossType", "USD")
        
        # Resolve USD Loss amount
        loss_usd = None
        if lost_amount and isinstance(lost_amount, (int, float)):
            loss_usd = lost_amount
            # rough conversions for major cryptos
            if loss_type.upper() == "ETH":
                loss_usd = lost_amount * 3000.0
            elif loss_type.upper() == "BTC":
                loss_usd = lost_amount * 60000.0
            elif loss_type.upper() in ["BNB", "WBNB"]:
                loss_usd = lost_amount * 500.0
                
        # Resolve physical test file path(s)
        rel_contract_path = inc.get("Contract")
        file_paths = []
        
        if rel_contract_path:
            abs_path = target_dir / rel_contract_path
            # Check if file exists
            if abs_path.exists():
                file_paths.append(str(abs_path.resolve()))
            else:
                # Try finding it in src/test recursively if paths shifted
                filename = Path(rel_contract_path).name
                found_files = list((target_dir / "src" / "test").rglob(filename))
                if found_files:
                    file_paths.append(str(found_files[0].resolve()))
                    
        # If no explicit contract but we want to map recursively by protocol name
        if not file_paths and protocol_name != "Unknown":
            # Search src/test/ for a .sol file containing the protocol name
            found_files = list((target_dir / "src" / "test").rglob(f"*{protocol_name}*.sol"))
            if found_files:
                file_paths.append(str(found_files[0].resolve()))
                
        # Skip if no physical contract file was resolved (we want exploits mapping to code)
        if not file_paths:
            continue
            
        finding_id = f"defihacklabs-{protocol_name}".replace(" ", "-").lower()
        finding_id = re.sub(r"[^a-z0-9_-]", "", finding_id)
        
        # Read test contract file content to include as content_markdown
        content_markdown = f"DeFiHackLabs Exploit Proof of Concept for {protocol_name}.\n\n"
        content_markdown += f"- **Incident Date**: {date_str}\n"
        content_markdown += f"- **Attack Vector**: {attack_type}\n"
        loss_usd_str = f"${loss_usd:,.2f}" if loss_usd is not None else "Unknown"
        content_markdown += f"- **Estimated Loss**: {lost_amount} {loss_type} (~{loss_usd_str} USD)\n"
        content_markdown += f"- **Chain**: {chain}\n"
        content_markdown += f"- **Proof of Concept Contract**: `{rel_contract_path}`\n\n"
        
        try:
            with open(file_paths[0], "r", encoding="utf-8", errors="ignore") as f:
                content_markdown += "### PoC Source Code\n```solidity\n" + f.read() + "\n```"
        except Exception as e:
            content_markdown += f"*(Could not read source code file: {e})*"
            
        finding_data = {
            "id": finding_id,
            "source_pool": "defihacklabs",
            "protocol_name": protocol_name,
            "title": f"[Exploit] {protocol_name} - {attack_type}",
            "content_markdown": content_markdown,
            "severity": "High (Exploit)",
            "loss_usd": loss_usd,
            "file_paths": file_paths,
            "fix_commit": None,
            "root_cause_keywords": [attack_type, chain]
        }
        
        db.insert_finding(finding_data)
        findings_count += 1
        
    print(f"Ingested {findings_count} findings from DeFiHackLabs.")
    return findings_count

def ingest_immunefi():
    """Clones Immunefi-bugfixes and parses case studies directly from README.md, mapping support code files."""
    target_dir = REPOS_DIR / "immunefi_bugfixes"
    print(f"Starting Immunefi Bugfixes ingestion at {target_dir}...")
    
    # 1. Clone Immunefi-bugfixes repository
    if not target_dir.exists():
        print("Cloning Immunefi-bugfixes repository (shallow)...")
        try:
            subprocess.run(["git", "clone", "--depth", "1", "https://github.com/tpiliposian/Immunefi-bugfixes.git", str(target_dir)], check=True)
        except Exception as e:
            print(f"Failed to clone Immunefi-bugfixes repository: {e}")
            return 0
    else:
        print("Immunefi-bugfixes repository already exists. Pulling updates...")
        try:
            try:
                subprocess.run(["git", "pull", "origin", "main"], cwd=str(target_dir), check=True)
            except subprocess.CalledProcessError:
                subprocess.run(["git", "pull", "origin", "master"], cwd=str(target_dir), check=True)
        except Exception as e:
            print(f"Failed to update Immunefi-bugfixes: {e}")
            
    findings_count = 0
    readme_path = target_dir / "README.md"
    if not readme_path.exists():
        print("README.md not found in Immunefi bugfixes repo.")
        return 0
        
    with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    # Split content by `# [Number]. ` pattern to isolate each case study
    sections = re.split(r"\n#\s+(\d+)\.\s+", "\n" + content)
    
    # Process sections in pairs of (number, body)
    for i in range(1, len(sections), 2):
        sec_num = sections[i]
        sec_body = sections[i+1] if i+1 < len(sections) else ""
        
        # Split body into lines to parse title and metadata
        lines = sec_body.strip().split("\n")
        if not lines:
            continue
            
        header = lines[0] # e.g. "Raydium - Tick Manipulation"
        if " - " in header:
            protocol_name, title = header.split(" - ", 1)
        else:
            protocol_name = header
            title = header
            
        protocol_name = protocol_name.strip()
        title = title.strip()
        
        # Parse metadata from first few lines of section
        reported_by = ""
        date_str = ""
        bounty = ""
        
        for line in lines[1:10]:
            if line.startswith("Reported by:"):
                reported_by = line.replace("Reported by:", "").strip()
            elif line.startswith("Protocol:"):
                protocol_name = line.replace("Protocol:", "").strip()
            elif line.startswith("Date:"):
                date_str = line.replace("Date:", "").strip()
            elif line.startswith("Bounty:"):
                bounty = line.replace("Bounty:", "").strip()
                
        # The content markdown is the section title plus body
        section_content = f"# {sec_num}. {header}\n\n" + sec_body
        
        # Determine severity based on content keywords
        severity = "High"
        content_lower = section_content.lower()
        if "critical" in content_lower:
            severity = "Critical"
        elif "medium" in content_lower:
            severity = "Medium"
            
        # Match folders by cleaning up the protocol name (e.g. "Silo Finance" -> "SiloFinance")
        folder_name = protocol_name.replace(" ", "")
        proto_dir = target_dir / folder_name
        
        # Look for any support files inside this protocol's directory
        resolved_files = []
        if proto_dir.exists():
            for root, dirs, files in os.walk(proto_dir):
                for file in files:
                    resolved_files.append(str(Path(root) / file))
                    
        # Read the code from any resolved file to append to raw_solidity_code
        raw_solidity_code = ""
        for rf in resolved_files:
            if rf.endswith(".sol") or rf.endswith(".rs") or rf.endswith(".vy"):
                try:
                    with open(rf, "r", encoding="utf-8", errors="ignore") as f_code:
                        rel_path = Path(rf).relative_to(target_dir)
                        raw_solidity_code += f"// File: {rel_path}\n" + f_code.read() + "\n\n"
                except Exception as e:
                    print(f"Error reading code file {rf}: {e}")
                    
        finding_id = f"immunefi-{sec_num}-{protocol_name.replace(' ', '-').lower()}"
        finding_id = re.sub(r"[^a-z0-9_-]", "", finding_id)
        
        finding_data = {
            "id": finding_id,
            "source_pool": "immunefi",
            "protocol_name": protocol_name,
            "title": f"[Immunefi] {protocol_name} - {title}",
            "content_markdown": section_content,
            "severity": severity,
            "loss_usd": None,
            "file_paths": resolved_files,
            "fix_commit": None,
            "root_cause_keywords": ["bugfix", "immunefi", severity],
            "raw_solidity_code": raw_solidity_code,
            "source_repo": "tpiliposian/Immunefi-bugfixes"
        }
        
        db.insert_finding(finding_data)
        findings_count += 1
            
    print(f"Ingested {findings_count} findings from Immunefi bugfixes.")
    return findings_count

# ==========================================
# PHASE 6: DEFIVULNLABS PROCESSING
# ==========================================

def ingest_defivulnlabs():
    """Clones DeFiVulnLabs and processes vulnerability educational test files."""
    target_dir = REPOS_DIR / "defivulnlabs_clone"
    print(f"Starting DeFiVulnLabs ingestion at {target_dir}...")
    
    # Clone repository
    if not target_dir.exists():
        print("Cloning DeFiVulnLabs repository...")
        try:
            subprocess.run(["git", "clone", "--depth", "1", "https://github.com/SunWeb3Sec/DeFiVulnLabs.git", str(target_dir)], check=True)
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], cwd=str(target_dir), check=True)
        except Exception as e:
            print(f"Failed to clone DeFiVulnLabs repository: {e}")
            return 0
    else:
        print("DeFiVulnLabs repository already exists. Pulling updates...")
        try:
            try:
                subprocess.run(["git", "pull", "origin", "main"], cwd=str(target_dir), check=True)
            except subprocess.CalledProcessError:
                subprocess.run(["git", "pull", "origin", "master"], cwd=str(target_dir), check=True)
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], cwd=str(target_dir), check=True)
        except Exception as e:
            print(f"Failed to update DeFiVulnLabs: {e}")
            
    test_dir = target_dir / "src" / "test"
    if not test_dir.exists():
        print(f"DeFiVulnLabs test directory not found: {test_dir}")
        return 0
        
    findings_count = 0
    sol_files = list(test_dir.glob("*.sol"))
    print(f"Found {len(sol_files)} Solidity files in DeFiVulnLabs.")
    
    for sol_path in sol_files:
        filename = sol_path.name
        finding_id = f"defivulnlabs-{filename.replace('.sol', '').lower()}"
        finding_id = re.sub(r"[^a-z0-9_-]", "", finding_id)
        
        try:
            with open(sol_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_code = f.read()
        except Exception as e:
            print(f"Could not read DeFiVulnLabs file {sol_path}: {e}")
            continue
            
        # Robust Comment Extraction
        comment_match = re.search(r"\/\*([\s\S]*?)\*\/", raw_code)
        if comment_match:
            header_comment = comment_match.group(1).strip()
            content_markdown = f"DeFiVulnLabs Educational Vulnerability PoC.\n\n### Description & Details\n\n{header_comment}"
        else:
            # Fallback to first 30 lines
            lines = raw_code.split("\n")[:30]
            header_comment = "\n".join(lines).strip()
            content_markdown = f"DeFiVulnLabs Educational Vulnerability PoC (Raw Header Fallback).\n\n### Raw Header Lines\n```solidity\n{header_comment}\n```"
            
        # Parse title from comment metadata if available, else clean file name
        title = filename.replace(".sol", "")
        name_match = re.search(r"Name:\s*(.+)", header_comment)
        if name_match:
            title = name_match.group(1).strip()
            
        # Basic severity estimation
        severity = "High (PoC)"
        if "reentrancy" in title.lower() or "overflow" in title.lower():
            severity = "High"
        elif "collision" in title.lower() or "replay" in title.lower():
            severity = "Critical"
            
        finding_data = {
            "id": finding_id,
            "source_pool": "defivulnlabs",
            "protocol_name": "DeFiVulnLabs",
            "title": f"[Vulnerability] {title}",
            "content_markdown": content_markdown,
            "severity": severity,
            "loss_usd": None,
            "file_paths": [str(sol_path.resolve())],
            "fix_commit": None,
            "root_cause_keywords": ["educational", "vuln-lab", title.lower()],
            "raw_solidity_code": raw_code,
            "source_repo": "SunWeb3Sec/DeFiVulnLabs"
        }
        
        db.insert_finding(finding_data)
        findings_count += 1
        
    print(f"Ingested {findings_count} findings from DeFiVulnLabs.")
    return findings_count

# ==========================================
# PHASE 7: OFFICIAL IMMUNEFI TEMPLATES INGESTION
# ==========================================

def ingest_immunefi_templates():
    """Ingests official vulnerability PoCs and template code from immunefi-team/forge-poc-templates."""
    import shutil
    base_target_dir = REPOS_DIR / "forge_poc_templates_base"
    print(f"Starting official Immunefi Templates Ingestion at {base_target_dir}...")
    
    # 1. Clone base repository (which gives us main branch and access to other branches)
    if base_target_dir.exists():
        try:
            shutil.rmtree(base_target_dir)
        except Exception as e:
            print(f"Warning: Could not remove existing directory {base_target_dir}: {e}")
            
    try:
        print("Cloning forge-poc-templates main branch...")
        subprocess.run(["git", "clone", "https://github.com/immunefi-team/forge-poc-templates.git", str(base_target_dir)], check=True)
    except Exception as e:
        print(f"Failed to clone forge-poc-templates: {e}")
        return 0
        
    findings_count = 0
    
    # Ingest community PoCs in pocs/ directory from main branch
    pocs_dir = base_target_dir / "pocs"
    if pocs_dir.exists():
        for poc_file in pocs_dir.glob("*.sol"):
            filename = poc_file.name
            finding_id = f"immunefi-template-poc-{filename.replace('.sol', '').lower()}"
            finding_id = re.sub(r"[^a-z0-9_-]", "", finding_id)
            
            try:
                with open(poc_file, "r", encoding="utf-8", errors="ignore") as f:
                    raw_code = f.read()
            except Exception as e:
                print(f"Error reading community PoC {poc_file}: {e}")
                continue
                
            content_markdown = f"Official Immunefi community-submitted vulnerability validation Proof of Concept.\n\nFile Name: `{filename}`"
            
            finding_data = {
                "id": finding_id,
                "source_pool": "immunefi",
                "protocol_name": "Immunefi Community PoC",
                "title": f"[Immunefi Community PoC] {filename.replace('.sol', '')}",
                "content_markdown": content_markdown,
                "severity": "Critical",
                "loss_usd": None,
                "file_paths": [str(poc_file.resolve())],
                "fix_commit": None,
                "root_cause_keywords": ["community-poc", "forge-poc-template"],
                "raw_solidity_code": raw_code,
                "source_repo": "immunefi-team/forge-poc-templates"
            }
            db.insert_finding(finding_data)
            findings_count += 1

    # Switch branch names and parse structured tests
    branches = ["default", "reentrancy", "flash_loan", "price_manipulation", "sandwich"]
    
    for branch in branches:
        branch_dir = REPOS_DIR / f"forge_poc_templates_{branch}"
        if branch_dir.exists():
            try:
                shutil.rmtree(branch_dir)
            except Exception as e:
                print(f"Warning: Could not remove directory {branch_dir}: {e}")
                
        print(f"Cloning branch '{branch}' of forge-poc-templates...")
        try:
            subprocess.run(["git", "clone", "--depth", "1", "-b", branch, "https://github.com/immunefi-team/forge-poc-templates.git", str(branch_dir)], check=True)
        except Exception as e:
            print(f"Failed to clone branch {branch}: {e}")
            continue
            
        # Parse README
        readme_path = branch_dir / "README.md"
        readme_content = ""
        if readme_path.exists():
            try:
                with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                    readme_content = f.read()
            except:
                pass
                
        # Parse test contract PoCTest.sol
        poc_test_path = branch_dir / "test" / "PoCTest.sol"
        poc_test_code = ""
        if poc_test_path.exists():
            try:
                with open(poc_test_path, "r", encoding="utf-8", errors="ignore") as f:
                    poc_test_code = f.read()
            except:
                pass
                
        # Parse source contracts under src/
        src_code = ""
        src_dir = branch_dir / "src"
        file_paths = []
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                for file in files:
                    if file.endswith(".sol"):
                        sol_file_path = Path(root) / file
                        file_paths.append(str(sol_file_path.resolve()))
                        try:
                            with open(sol_file_path, "r", encoding="utf-8", errors="ignore") as sf:
                                rel_path = sol_file_path.relative_to(branch_dir)
                                src_code += f"// File: {rel_path}\n" + sf.read() + "\n\n"
                        except:
                            pass
                            
        # Concatenate test and target code for full context
        raw_solidity_code = ""
        if poc_test_code:
            raw_solidity_code += f"// File: test/PoCTest.sol\n{poc_test_code}\n\n"
        if src_code:
            raw_solidity_code += src_code
            
        if not raw_solidity_code:
            print(f"No solidity code found in branch {branch}. Skipping ingestion.")
            continue
            
        finding_id = f"immunefi-template-branch-{branch}"
        finding_id = re.sub(r"[^a-z0-9_-]", "", finding_id)
        
        content_markdown = f"Official Immunefi Template configuration for the {branch.replace('_', ' ')} vulnerability category.\n\n"
        if readme_content:
            content_markdown += f"### Branch README\n\n{readme_content}"
            
        finding_data = {
            "id": finding_id,
            "source_pool": "immunefi",
            "protocol_name": f"Immunefi Template {branch.upper()}",
            "title": f"[Immunefi Template] {branch.replace('_', ' ').title()} Attack Architecture",
            "content_markdown": content_markdown,
            "severity": "High (Template)",
            "loss_usd": None,
            "file_paths": file_paths,
            "fix_commit": None,
            "root_cause_keywords": ["template", "forge-poc-template", branch],
            "raw_solidity_code": raw_solidity_code,
            "source_repo": f"immunefi-team/forge-poc-templates/tree/{branch}"
        }
        db.insert_finding(finding_data)
        findings_count += 1
        
        # Clean up cloned branch directory
        try:
            shutil.rmtree(branch_dir)
        except Exception as e:
            print(f"Warning: Could not remove temp directory {branch_dir}: {e}")
            
    # Clean up base directory
    try:
        shutil.rmtree(base_target_dir)
    except Exception as e:
        print(f"Warning: Could not remove temp base directory {base_target_dir}: {e}")
        
    print(f"Ingested {findings_count} findings from official Immunefi Templates.")
    return findings_count

def backfill_vulnerability_tags():
    """
    Backfills the vulnerability_tags_index table for all current existing records
    if the table is unpopulated.
    """
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Check if table already has rows
    try:
        cursor.execute("SELECT COUNT(*) FROM vulnerability_tags_index")
        tag_count = cursor.fetchone()[0]
        if tag_count > 0:
            print(f"vulnerability_tags_index already populated with {tag_count} records. Skipping backfill.")
            conn.close()
            return
    except Exception as e:
        print(f"Error checking vulnerability_tags_index: {e}")
    
    print("Starting high-speed transaction backfill of vulnerability_tags_index...")
    start_time = time.time()
    
    # Fetch all records from normalized_findings
    cursor.execute("SELECT id, source_pool, root_cause_keywords FROM normalized_findings")
    findings = cursor.fetchall()
    
    total_inserted = 0
    # Performance Critical: Wrap the entire insertion loop inside a single SQL transaction block ('with conn:')
    try:
        with conn:
            for row in findings:
                finding_id = row["id"]
                source_pool = row["source_pool"]
                kws_str = row["root_cause_keywords"]
                
                if not kws_str:
                    continue
                try:
                    keywords = json.loads(kws_str)
                except Exception:
                    continue
                
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
                                """, (finding_id, source_pool, tag))
                                total_inserted += 1
        elapsed = time.time() - start_time
        print(f"Backfill completed successfully. Inserted {total_inserted} tags in {elapsed:.2f} seconds.")
    except Exception as e:
        print(f"Error during backfill: {e}")
    finally:
        conn.close()

# ==========================================
# PIPELINE ORCHESTRATION
# ==========================================

def run_pipeline():
    """Runs the complete ingestion and normalization pipeline."""
    db.init_db()
    backfill_vulnerability_tags()
    
    # Early exit if database is already populated with the full dataset
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM normalized_findings")
        count = cursor.fetchone()[0]
        conn.close()
        if count >= 70000:
            print(f"Database already populated with {count} findings. Skipping slow online ingestion pipeline.")
            return
    except Exception as e:
        print(f"Checking database failed: {e}")
    
    # Phase 1: Solodit
    solodit_count = 0
    if sparse_checkout_solodit_content():
        solodit_count += parse_solodit_markdown_reports()
    solodit_count += fetch_solodit_api_findings()
    
    # Phase 2: Code4rena
    c4_count = fetch_code4rena_findings()
    
    # Phase 3: DeFiHackLabs
    dhl_count = ingest_defihacklabs()
    
    # Phase 4: Sherlock
    sherlock_count = fetch_sherlock_findings()
    
    # Phase 5: Immunefi
    immunefi_count = ingest_immunefi()
    
    # Phase 6: DeFiVulnLabs Ingestion
    defivuln_count = ingest_defivulnlabs()
    
    # Phase 7: Official Immunefi Templates Ingestion
    immunefi_templates_count = ingest_immunefi_templates()
    
    print("\n==========================================")
    print("Pipeline Execution Completed!")
    print(f"- Solodit findings ingested: {solodit_count}")
    print(f"- Code4rena findings ingested: {c4_count}")
    print(f"- DeFiHackLabs exploits ingested: {dhl_count}")
    print(f"- Sherlock findings ingested: {sherlock_count}")
    print(f"- Immunefi bugfixes ingested: {immunefi_count}")
    print(f"- DeFiVulnLabs findings ingested: {defivuln_count}")
    print(f"- Immunefi Templates ingested: {immunefi_templates_count}")
    print(f"Total entries: {solodit_count + c4_count + dhl_count + sherlock_count + immunefi_count + defivuln_count + immunefi_templates_count}")
    print("==========================================\n")

if __name__ == "__main__":
    run_pipeline()

