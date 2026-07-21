import json

data = json.load(open('full_export.json', 'r', encoding='utf-8'))
requests = data.get('requests', [])
print(f"[+] Total requests exported: {len(requests)}")

for i, r in enumerate(requests):
    fid = r.get("id")
    p_len = len(r.get("user_prompt", ""))
    ps_len = len(r.get("user_prompt_snippet", ""))
    tokens = r.get("total_tokens")
    tier = r.get("context_tier")
    print(f"\nItem #{i+1}:")
    print(f"  ID                  : {fid}")
    print(f"  Context Tier        : {tier}")
    print(f"  Total Tokens        : {tokens}")
    print(f"  User Prompt Length  : {p_len:,} chars")
    print(f"  User Prompt Snippet : {ps_len:,} chars")
    snippet = r.get("user_prompt", "")[:400]
    print(f"  User Prompt Excerpt:\n{snippet}\n...")
