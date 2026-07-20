import math
import re
import json
import time
import threading
import urllib.request
from typing import Dict, List, Any

from core.database import attach_vulnerabilities_db

_TVL_CACHE: Dict[str, float] = {}
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 1800.0  # 30-minute retention horizon
_CACHE_LOCK = threading.Lock()

def fetch_defillama_tvl_cache(endpoint: str = "https://api.llama.fi/protocols", timeout: float = 4.0) -> Dict[str, float]:
    """
    Builds a resilient, caching HTTP request client utilizing standard library tools (urllib.request)
    to query DeFiLlama's open endpoint and index protocol tokens, names, and slugs directly to current TVL numbers.
    Thread-safe and failsafe with fallback to existing cache or default fallback map.
    """
    global _TVL_CACHE, _CACHE_TIMESTAMP

    with _CACHE_LOCK:
        now = time.time()
        if _TVL_CACHE and (now - _CACHE_TIMESTAMP < _CACHE_TTL_SECONDS):
            return _TVL_CACHE

        try:
            req = urllib.request.Request(
                endpoint,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    new_cache: Dict[str, float] = {}
                    if isinstance(data, list):
                        for p in data:
                            tvl_val = float(p.get("tvl", 0.0) or 0.0)
                            slug = str(p.get("slug", "") or "").strip().lower()
                            name = str(p.get("name", "") or "").strip().lower()
                            symbol = str(p.get("symbol", "") or "").strip().lower()

                            if slug:
                                new_cache[slug] = tvl_val
                            if name:
                                new_cache[name] = tvl_val
                            if symbol:
                                new_cache[symbol] = tvl_val

                    _TVL_CACHE = new_cache
                    _CACHE_TIMESTAMP = now
                    return _TVL_CACHE
        except Exception as e:
            print(f"[!] Warning: DeFiLlama TVL ingestion error on {endpoint}: {e}")
            return _TVL_CACHE if _TVL_CACHE else {}

    return _TVL_CACHE

def calculate_success_probability(
    audits_count: int,
    global_tag_findings: int = 0,
    total_global_findings: int = 0
) -> float:
    """
    Computes statistical probability index combining global tag density with target audit counts:
    P_success = (Global Findings for Tag / Total Global Findings Pool) * (1 / (1 + ln(1 + Audits Count)))

    Fallback protection:
    If total_global_findings <= 0 or global_tag_findings <= 0, returns a strict fallback baseline of 0.0001
    to prevent division by zero or absolute zero dropouts.
    """
    if total_global_findings <= 0 or global_tag_findings <= 0:
        return 0.0001
    
    density_ratio = float(global_tag_findings) / float(total_global_findings)
    safe_audits = max(0, audits_count)
    audit_factor = 1.0 / (1.0 + math.log(1.0 + safe_audits))
    
    p_success = density_ratio * audit_factor
    return max(0.0001, p_success)

def calculate_complexity_time_index(files_count: int, nesting_depth_modifier: float, kyc_required: bool) -> float:
    """
    Computes algorithmically from scope properties:
    T = Files Count * Nesting Depth Modifier * (1.5 if KYC required else 1.0)
    """
    base_files = max(1, files_count)
    depth = max(1.0, nesting_depth_modifier)
    kyc_multiplier = 1.5 if kyc_required else 1.0
    return base_files * depth * kyc_multiplier

def calculate_expected_profitability_yield(
    p_success: float,
    r_max: float,
    alpha: float,
    tvl: float,
    c_time: float,
    t_index: float
) -> float:
    """
    Computes yield formula with explicit mathematical clamping rules:
    E(P) = P_success * min(R_max, alpha * TVL) - (C_time * T)
    """
    economic_cap = alpha * tvl if alpha is not None and alpha >= 0 else tvl
    clamped_reward = min(r_max, economic_cap)
    expected_gain = p_success * clamped_reward
    opportunity_cost = c_time * t_index
    return expected_gain - opportunity_cost

def get_target_profitability_matrix(conn) -> List[Dict[str, Any]]:
    """
    Fetches target programs, mounts historical vulnerabilities tracking ledger ('vulnerabilities.db'),
    calculates mathematical profitability metrics using individual row parameters, relational tag counts,
    live DeFiLlama TVL ingestion cache with fallback clamping, and child asset counts.
    Returns a sorted list matching the ProfitabilityRow schema.
    """
    # 1. Mount attached vulnerabilities database safely
    attach_vulnerabilities_db(conn)
    cursor = conn.cursor()
    
    # 2. Query total global findings pool across ecosystem safely with fallback
    total_global_findings = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM vuln.normalized_findings")
        res = cursor.fetchone()
        if res:
            total_global_findings = int(res[0] or 0)
    except Exception:
        total_global_findings = 0

    # 3. Pre-compile global tag frequencies into memory to eliminate N+1 loop queries
    tag_density_lookup = {}
    try:
        cursor.execute("SELECT tag, COUNT(*) as cnt FROM vuln.vulnerability_tags_index GROUP BY tag")
        tag_density_lookup = {r["tag"]: r["cnt"] for r in cursor.fetchall()}
    except Exception:
        tag_density_lookup = {}

    # 4. Fetch live DeFiLlama TVL lookup cache
    tvl_cache = fetch_defillama_tvl_cache()

    # 4b. Pre-compiled Global Cache Lookup for AST Metrics
    ast_cache_lookup = {}
    try:
        cursor.execute("""
        SELECT project_slug, 
               SUM(total_functions) as total_funcs,
               MAX(max_loop_depth) as max_loop,
               SUM(external_calls_count) as total_calls,
               SUM(state_mutations_count) as total_muts
        FROM ast_metrics GROUP BY project_slug
        """)
        ast_cache_lookup = {str(r["project_slug"]).lower(): dict(r) for r in cursor.fetchall()}
    except Exception:
        ast_cache_lookup = {}

    # 5. Query projects joined with rewards aggregation, assets count, and known issues count
    query = """
    SELECT 
        p.slug,
        p.project_name,
        p.source_platform,
        p.github_url,
        p.max_bounty_usd,
        p.primacy_model,
        p.scaling_percentage,
        p.kyc_required,
        COALESCE(r_agg.max_reward, p.max_bounty_usd, 0) as calculated_max_reward,
        COALESCE(r_agg.privilege_tier, 'unprivileged') as privilege_tier,
        COALESCE(r_agg.impact_type_normalized, 'Smart Contract Exploit') as normalized_impact,
        COALESCE(a_agg.asset_count, 0) as child_asset_count,
        COALESCE(ki_agg.issue_count, 0) as known_issues_count
    FROM projects p
    LEFT JOIN (
        SELECT 
            project_slug, 
            MAX(max_reward) as max_reward,
            privilege_escalation_tier as privilege_tier,
            impact_type_normalized
        FROM rewards
        GROUP BY project_slug
    ) r_agg ON p.slug = r_agg.project_slug
    LEFT JOIN (
        SELECT project_slug, COUNT(*) as asset_count
        FROM assets
        GROUP BY project_slug
    ) a_agg ON p.slug = a_agg.project_slug
    LEFT JOIN (
        SELECT project_slug, COUNT(*) as issue_count
        FROM known_issues
        GROUP BY project_slug
    ) ki_agg ON p.slug = ki_agg.project_slug
    """
    
    rows = cursor.execute(query).fetchall()
    matrix = []
    
    for row in rows:
        slug = str(row["slug"] or "").strip().lower()
        project_name = str(row["project_name"] or "").strip()
        project_name_lower = project_name.lower()
        source_platform = row["source_platform"]
        github_url = row["github_url"]
        stated_max_reward = float(row["max_bounty_usd"] or row["calculated_max_reward"] or 0)
        
        scaling_pct = row["scaling_percentage"]
        alpha = (float(scaling_pct) / 100.0) if scaling_pct is not None and float(scaling_pct) > 0 else 1.0
        kyc_required = bool(row["kyc_required"])
        
        primacy_model = row["primacy_model"] if row["primacy_model"] in ['impact', 'rules', 'mixed'] else 'rules'
        privilege_tier = row["privilege_tier"] if row["privilege_tier"] in ['unprivileged', 'moderator', 'admin', 'trusted_multisig'] else 'unprivileged'
        normalized_impact = row["normalized_impact"] or "Critical Logic Defect"
        
        # Fast memory lookup for target impact tag density
        global_tag_findings = tag_density_lookup.get(normalized_impact, 0)
            
        # Row-specific dynamic parameter calculations
        child_assets = int(row["child_asset_count"] or 0)
        files_count = child_assets if child_assets > 0 else 5
        
        known_issues = int(row["known_issues_count"] or 0)
        audits_count = 2 + known_issues
        
        p_success = calculate_success_probability(
            audits_count=audits_count,
            global_tag_findings=global_tag_findings,
            total_global_findings=total_global_findings
        )
        
        # Fetch pre-compiled AST metric map with fallbacks
        ast_data = ast_cache_lookup.get(slug, {})
        total_funcs = ast_data.get("total_funcs") if ast_data.get("total_funcs") is not None else 8
        max_loop = ast_data.get("max_loop") if ast_data.get("max_loop") is not None else 1
        total_calls = ast_data.get("total_calls") if ast_data.get("total_calls") is not None else 2

        depth_factor = 1.0 + (0.15 * max_loop)
        call_factor = 1.0 + (0.02 * total_calls)
        kyc_mult = 1.5 if kyc_required else 1.0

        t_index = files_count * depth_factor * call_factor * kyc_mult
        
        # Resolve TVL dynamically using tiered lookup rules
        tvl_applied = None
        
        # Step 1 & Step 2: Direct lookup on slug or project_name
        if slug in tvl_cache:
            tvl_applied = tvl_cache[slug]
        elif project_name_lower in tvl_cache:
            tvl_applied = tvl_cache[project_name_lower]
        else:
            # Check slug/name prefix matches if direct match failed (e.g. "aave-v3" -> "aave")
            slug_prefix = slug.split("-")[0]
            if slug_prefix in tvl_cache:
                tvl_applied = tvl_cache[slug_prefix]
            else:
                name_prefix = project_name_lower.split()[0]
                if name_prefix in tvl_cache:
                    tvl_applied = tvl_cache[name_prefix]

        # Step 3: Parse repository name from GitHub URL using regex if unmatched
        if tvl_applied is None:
            match = re.search(r"github\.com/([^/]+)/([^/]+)", str(github_url or ""))
            repo_name = match.group(2).strip().lower().rstrip("/") if match else None
            if repo_name:
                if repo_name in tvl_cache:
                    tvl_applied = tvl_cache[repo_name]
                else:
                    repo_prefix = repo_name.split("-")[0]
                    if repo_prefix in tvl_cache:
                        tvl_applied = tvl_cache[repo_prefix]

        # Step 4: Fallback boundary default
        if tvl_applied is None or tvl_applied <= 0:
            tvl_applied = 5_000_000.0

        c_time = 150.0
        
        # Explicit mathematical clamping rule
        economic_cap = alpha * tvl_applied
        clamped_real_reward = min(stated_max_reward, economic_cap)
        
        yield_val = calculate_expected_profitability_yield(
            p_success=p_success,
            r_max=stated_max_reward,
            alpha=alpha,
            tvl=tvl_applied,
            c_time=c_time,
            t_index=t_index
        )
        
        matrix.append({
            "slug": row["slug"],
            "project_name": project_name,
            "source_platform": source_platform,
            "normalized_impact": normalized_impact,
            "stated_max_reward": stated_max_reward,
            "calculated_real_reward": clamped_real_reward,
            "tvl_applied": tvl_applied,
            "complexity_time_cost": c_time * t_index,
            "success_probability": round(p_success, 4),
            "expected_profitability_yield": round(yield_val, 2),
            "primacy_model": primacy_model,
            "privilege_tier": privilege_tier
        })
        
    matrix.sort(key=lambda x: x["expected_profitability_yield"], reverse=True)
    return matrix

