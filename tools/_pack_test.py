import os, subprocess, time
from pathlib import Path
import httpx

exe = Path("dist/PushAll/PushAll.exe").resolve()
env = os.environ.copy()
env["PUSHALL_AUTO_QUIT_SECONDS"] = "14"
proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
ok = False
for _ in range(60):
    time.sleep(0.5)
    try:
        r = httpx.get("http://127.0.0.1:8765/api/health", timeout=1)
        if r.status_code == 200:
            print("health:", r.json())
            ok = True
            break
    except Exception:
        pass
time.sleep(1)
try:
    print("update check:", httpx.get("http://127.0.0.1:8765/api/update/check", timeout=20).json())
except Exception as exc:
    print("update check failed:", exc)
print("exit:", proc.wait(timeout=45))
