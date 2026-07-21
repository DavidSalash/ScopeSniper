import time
import subprocess
import sys
import urllib.request
from pathlib import Path

WORKSPACE_DIR = Path(__file__).parent.parent.resolve()

print("[+] Starting uvicorn server on port 8000...")
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=str(WORKSPACE_DIR)
)

print("[+] Waiting for server to finish startup ingestion (up to 60s)...")
ready = False
for i in range(60):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/ingestion/prompt-config", timeout=2.0) as resp:
            if resp.status == 200:
                ready = True
                print(f"[+] Server ready after {i+1} seconds!")
                break
    except Exception:
        time.sleep(1.0)

if not ready:
    print("[-] Server failed to initialize in time.")
    proc.terminate()
    sys.exit(1)

print("[+] Executing curl http://localhost:8000/api/batch/export?limit=3 -o full_export.json")
try:
    res = subprocess.run(
        ["curl", "-s", "http://localhost:8000/api/batch/export?limit=3", "-o", "full_export.json"],
        cwd=str(WORKSPACE_DIR),
        capture_output=True,
        text=True
    )
    print(f"[+] Curl Return Code: {res.returncode}")
finally:
    print("[+] Terminating server process...")
    proc.terminate()
    proc.wait(timeout=5)
