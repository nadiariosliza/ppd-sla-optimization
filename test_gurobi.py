import os
from pathlib import Path

# Load .env
env_path = Path(__file__).resolve().parent / "models" / ".env"
with open(env_path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ[key.strip()] = val.strip()

import sys
sys.path.insert(0, 'models')
sys.path.insert(0, 'models/realtime')

import gurobipy as gp

# Show exactly what is being passed
wls_id  = os.environ.get("WLSACCESSID", "NOT FOUND")
wls_sec = os.environ.get("WLSSECRET",   "NOT FOUND")
lic_id  = os.environ.get("LICENSEID",   "NOT FOUND")

print(f"WLSACCESSID : '{wls_id[:8]}...' (length={len(wls_id)})")
print(f"WLSSECRET   : '{wls_sec[:8]}...' (length={len(wls_sec)})")
print(f"LICENSEID   : '{lic_id}' (length={len(lic_id)})")

params = {
    "WLSACCESSID": wls_id,
    "WLSSECRET":   wls_sec,
    "LICENSEID":   int(lic_id),
}
env = gp.Env(params=params)
print('Gurobi OK')
env.dispose()