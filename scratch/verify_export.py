import sys
from pathlib import Path
WORKSPACE_DIR = Path(__file__).parent.parent.resolve()
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import asyncio
import json
from api.server import export_compact_batch

async def main():
    res = await export_compact_batch(limit=3, download=False)
    with open("github_enriched_export.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    
    requests = res.get("requests", [])
    print(f"Exported {len(requests)} items to github_enriched_export.json")
    for i, item in enumerate(requests):
        print(f"\n==================== ITEM {i+1}: {item.get('title')} ====================")
        print(f"ID: {item.get('id')}")
        user_prompt = item.get("user_prompt", "")
        # Print snippet section
        if "### Extracted Referenced Code Snippet" in user_prompt:
            idx = user_prompt.find("### Extracted Referenced Code Snippet")
            print("Extracted snippet found:\n", user_prompt[idx:idx+800])
        else:
            print("Tail of user prompt:\n", user_prompt[-500:])

if __name__ == "__main__":
    asyncio.run(main())
