import statistics
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add workspace root to sys.path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from core.database import get_unified_connection, attach_vulnerabilities_db

def run_db_length_investigation():
    conn = get_unified_connection()
    attach_vulnerabilities_db(conn)
    cursor = conn.cursor()

    print("[+] Fetching finding content lengths from vuln.normalized_findings...")
    cursor.execute("""
    SELECT id, source_pool, protocol_name, title, content_markdown, severity
    FROM vuln.normalized_findings
    """)
    rows = cursor.fetchall()
    conn.close()

    total_findings = len(rows)
    print(f"[+] Total findings fetched: {total_findings:,}")

    if total_findings == 0:
        print("[-] No findings found in database.")
        return

    # Process metrics overall and per source_pool
    overall_lengths: List[int] = []
    pool_lengths: Dict[str, List[int]] = {}
    
    bucket_counts = {
        "< 200": 0,
        "200 - 2,000": 0,
        "2,000 - 10,000": 0,
        "> 10,000": 0
    }

    scored_findings = []

    for r in rows:
        fid = r["id"]
        pool = r["source_pool"] or "unknown"
        title = r["title"] or ""
        content = r["content_markdown"] or ""
        char_len = len(content)

        overall_lengths.append(char_len)
        pool_lengths.setdefault(pool, []).append(char_len)

        if char_len < 200:
            bucket_counts["< 200"] += 1
        elif char_len <= 2000:
            bucket_counts["200 - 2,000"] += 1
        elif char_len <= 10000:
            bucket_counts["2,000 - 10,000"] += 1
        else:
            bucket_counts["> 10,000"] += 1

        scored_findings.append({
            "id": fid,
            "source_pool": pool,
            "title": title,
            "char_len": char_len,
            "content": content
        })

    # Overall stats
    min_len = min(overall_lengths)
    max_len = max(overall_lengths)
    avg_len = statistics.mean(overall_lengths)
    med_len = statistics.median(overall_lengths)

    print("\n" + "="*60)
    print("      DATABASE CONTENT LENGTH METRICS (OVERALL)")
    print("="*60)
    print(f"Total Findings: {total_findings:,}")
    print(f"Min Length   : {min_len:,} chars")
    print(f"Max Length   : {max_len:,} chars")
    print(f"Average Len  : {avg_len:,.2f} chars")
    print(f"Median Len   : {med_len:,.2f} chars")

    print("\n" + "="*60)
    print("      CONTENT LENGTH BREAKDOWN BY BUCKET")
    print("="*60)
    for bucket, count in bucket_counts.items():
        pct = (count / total_findings) * 100
        print(f"  {bucket:<15}: {count:>7,} ({pct:6.2f}%)")

    print("\n" + "="*60)
    print("      SOURCE POOL DETAILED METRICS")
    print("="*60)
    print(f"{'Source Pool':<22} | {'Count':<7} | {'Min':<6} | {'Max':<7} | {'Avg':<8} | {'Median':<8}")
    print("-" * 72)
    for pool in sorted(pool_lengths.keys()):
        lens = pool_lengths[pool]
        p_min = min(lens)
        p_max = max(lens)
        p_avg = statistics.mean(lens)
        p_med = statistics.median(lens)
        print(f"{pool:<22} | {len(lens):<7,} | {p_min:<6,} | {p_max:<7,} | {p_avg:<8.1f} | {p_med:<8.1f}")

    # Top 3 longest reports
    scored_findings.sort(key=lambda x: x["char_len"], reverse=True)
    top_3 = scored_findings[:3]

    print("\n" + "="*60)
    print("      TOP 3 LONGEST REPORTS (EXCERPTS)")
    print("="*60)
    for idx, f in enumerate(top_3, 1):
        print(f"\n--- Rank #{idx} ---")
        print(f"ID         : {f['id']}")
        print(f"Source Pool: {f['source_pool']}")
        print(f"Title      : {f['title']}")
        print(f"Length     : {f['char_len']:,} chars")
        excerpt = f['content'][:1000]
        print(f"Excerpt (first 1000 chars):\n{excerpt}")
        if len(f['content']) > 1000:
            print("...\n[Content continues...]")

if __name__ == "__main__":
    run_db_length_investigation()
