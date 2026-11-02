"""The demo backend's command (setup/compose.demo.yml): the pristine house first, then the backend as usual.
Refuses to run outside demo mode, so it can never wipe a real house."""
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seed  # noqa: E402

if os.environ.get("YASHOME_RESTRICTED") != "1" or not os.environ.get("HOUSE_ROOT"):
    sys.exit("entry.py runs the demo only: YASHOME_RESTRICTED=1 and HOUSE_ROOT are needed")
seed.reset_house(os.environ["HOUSE_ROOT"])
print(f"[demo] house seeded {seed.digest(os.environ['HOUSE_ROOT'])} (seed {seed.digest(seed.SEED)})", flush=True)
os.environ["DASHBOARD_TOKEN"] = secrets.token_urlsafe(32)     # nobody holds the house token in the demo
# no access log: it holds the edge's address only, and /ws?token=<session token> in full
os.execvp("uvicorn", ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8765", "--no-server-header", "--no-access-log"])
