import json
import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.server import app

print("[+] Initializing FastAPI TestClient...")
client = TestClient(app)

print("[+] GET /api/batch/export?limit=3 ...")
resp = client.get("/api/batch/export?limit=3")
print(f"[+] Response status: {resp.status_code}")

if resp.status_code == 200:
    with open("full_export.json", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print("[+] Successfully wrote full_export.json")

    data = resp.json()
    requests = data.get("requests", [])
    print(f"[+] Total requests returned: {len(requests)}")
    for i, r in enumerate(requests):
        fid = r.get("id")
        p_len = len(r.get("user_prompt", ""))
        ps_len = len(r.get("user_prompt_snippet", ""))
        tokens = r.get("total_tokens")
        tier = r.get("context_tier")
        print(f"\n--- Item #{i+1} ---")
        print(f"  ID                  : {fid}")
        print(f"  Context Tier        : {tier}")
        print(f"  Total Tokens        : {tokens}")
        print(f"  User Prompt Length  : {p_len:,} chars")
        print(f"  User Prompt Snippet : {ps_len:,} chars")
        print(f"  User Prompt Excerpt:\n{r.get('user_prompt', '')[:400]}")
