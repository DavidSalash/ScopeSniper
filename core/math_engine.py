import math
from typing import Dict, List, Any

from core.database import attach_vulnerabilities_db

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
    and child asset counts, and returns a sorted list matching the ProfitabilityRow schema.
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

    # 4. Query projects joined with rewards aggregation, assets count, and known issues count
    query = """
    SELECT 
        p.slug,
        p.project_name,
        p.source_platform,
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
        slug = row["slug"]
        project_name = row["project_name"]
        source_platform = row["source_platform"]
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
        
        nesting_depth_modifier = 1.0 + (0.05 * min(10, files_count))
        t_index = calculate_complexity_time_index(files_count, nesting_depth_modifier, kyc_required)
        
        tvl_applied = 15_000_000.0
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
            "slug": slug,
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

