"""live_check.py <run dir>: the running demo on its host (the run dir holds demo.env and app/). Checks what the
unit tests cannot: a real turn ends in a real reset (the house files equal the seed byte for byte, the guest's
light is off again, the event feed starts empty), every dangerous route answers 403 through the edge, and the
containers reach neither the LAN nor the internet. Tokens are never printed. Exit 1 on any failure."""
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RUN = Path(sys.argv[1])
ENV = dict(ln.split("=", 1) for ln in (RUN / "demo.env").read_text().splitlines() if "=" in ln and not ln.startswith("#"))


def _cid(svc: str) -> str:
    """A service's container by its compose labels (a cut recreate can leave it under a temporary name)."""
    out = subprocess.run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=yashome-demo",
                          "--filter", f"label=com.docker.compose.service={svc}"], capture_output=True, text=True).stdout.split()
    return out[0] if out else f"yashome-demo-{svc}-1"


C = {s: _cid(s) for s in ("home", "sim", "mosquitto", "edge")}
NAME = {v: f"yashome-demo-{k}" for k, v in C.items()}
BASE = f"http://{ENV['DEMO_BIND']}:{ENV.get('DEMO_PORT', '8780')}"
SEED = RUN / "app" / "plugins-extra" / "demo" / "house"
fails = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def call(m, p, tok=None, body=None):
    h = {"Content-Type": "application/json", **({"Authorization": "Bearer " + tok} if tok else {})}
    r = urllib.request.Request(BASE + p, method=m, headers=h, data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            raw = x.read()
            try:
                return x.status, json.loads(raw or b"null")
            except ValueError:
                return x.status, None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None
    except OSError:
        return 0, None


def house_files() -> dict:
    out = subprocess.run(["docker", "exec", C["home"], "tar", "-C", "/house", "-cf", "-", "."],
                         capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(out)) as t:
        return {m.name.lstrip("./"): hashlib.sha256(t.extractfile(m).read()).hexdigest() for m in t if m.isfile()}


def seed_files() -> dict:
    return {str(p.relative_to(SEED)): hashlib.sha256(p.read_bytes()).hexdigest() for p in SEED.rglob("*") if p.is_file()}


def starts() -> int:
    logs = subprocess.run(["docker", "logs", C["home"]], capture_output=True, text=True).stdout
    return logs.count("[demo] house seeded")


def wait_up(before: int, t=90):
    """The backend started again (one more seeding in its log) and answers."""
    end = time.time() + t
    while time.time() < end:
        if starts() > before and call("GET", "/try")[0] == 200:
            return True
        time.sleep(1)
    return False


def in_container(name, py):
    return subprocess.run(["docker", "exec", name, "python", "-c", py], capture_output=True, text=True, timeout=30)


# ---- a turn and its reset ----
s, d = call("POST", "/api/demo/login", body={"password": ENV["DEMO_PASSWORD"]})
ok(s == 200, "sign-in through the edge")
tok = (d or {}).get("token", "")
s, st = call("GET", "/api/demo/state", tok)
ok(s == 200 and st.get("role") == "control", f"the sign-in has control at once ({s}: {st and (st.get('detail') or st.get('position'))})")
time.sleep(1.2)                                            # the edge lets one sign-in a second through
s, d = call("POST", "/api/demo/login", body={"password": ENV["DEMO_PASSWORD"]})
ok(s == 409 and "per guest" in (d or {}).get("detail", ""), f"a second sign-in from the same address is refused ({s})")
s, _ = call("POST", "/api/devices/Kitchen%20light/control", tok, {"code": "state", "value": True})
ok(s == 200, "the guest switches the kitchen light on")
time.sleep(1.5)
s, st = call("GET", "/api/devices/Kitchen%20light/status", tok)
ok(s == 200 and st.get("values", {}).get("state") is True, "the simulator answered: on")
s, _ = call("PUT", "/api/favorites/Kitchen%20light/state", tok, {"alias": "Guest was here"})
ok(s == 200, "the guest stores a favourite")
ok(house_files() != seed_files(), "the house differs from the seed now")
start, n0 = time.time(), starts()
call("POST", "/api/demo/release", tok)
ok(wait_up(n0), "the backend is back after the reset")
time.sleep(4)
up = time.time() - start
logs = subprocess.run(["docker", "logs", C["home"]], capture_output=True, text=True).stdout.splitlines()
seeded = [ln.split()[3] for ln in logs if ln.startswith("[demo] house seeded")]
sys.path.insert(0, str(SEED.parent))
import seed  # noqa: E402
ok(len(seeded) >= 2 and seeded[-1] == seed.digest(SEED), f"the reset copied the seed byte for byte ({up:.0f} s, {len(seeded)} starts)")
now, want = house_files(), seed_files()
ok(all(now.get(k) == v for k, v in want.items() if not k.startswith("plugin-data/map/")), "the seed's files are still the seed's")
s, st = call("GET", "/api/devices/Kitchen%20light/status", tok)
ok(s == 200 and st.get("values", {}).get("state") is False, "the guest's light is off again (retained state cleared)")
s, favs = call("GET", "/api/favorites", tok)
ok(s == 200 and not any(f.get("alias") == "Guest was here" for f in favs or []), "the guest's favourite is gone")
s, st = call("GET", "/api/demo/state", tok)
ok(st and st.get("signed_in") and st.get("role") == "view" and (st.get("summary") or {}).get("why") == "released",
   "the session survived the reset, out of turn, with its summary")
ok(call("GET", "/api/history?limit=50", tok)[0] == 403, "a session out of turn does not read the history")
s, d = call("POST", "/api/demo/login", body={"password": ENV["DEMO_PASSWORD"]})
tok2 = (d or {}).get("token", "")
ok(s == 200 and call("GET", "/api/demo/state", tok2)[1].get("role") == "control", "the next sign-in has control at once")
s, ev = call("GET", "/api/history?limit=50", tok2)
ok(s == 200 and not any("Guest" in json.dumps(e) for e in (ev or {}).get("rows", ev or [])), "the history starts again (read in control)")
call("POST", "/api/demo/release", tok2)                    # no action, under 30 s: no reset

# ---- refused through the edge ----
for m, p in (("POST", "/api/backups"), ("POST", "/api/backups/upload"), ("PUT", "/api/map/underlay"), ("POST", "/api/helper/plugins"),
             ("POST", "/api/esphome/add"), ("GET", "/api/esphome/discover"), ("POST", "/api/zigbee/pair/start"),
             ("POST", "/api/signin/start"), ("GET", "/docs"), ("GET", "/openapi.json"), ("PUT", "/api/house")):
    s, d = call(m, p, tok, {})
    ok(s == 403 and (d or {}).get("detail") == "Not available here", f"{m} {p} refused")
big = call("POST", "/api/rules/run", tok, {"id": "x" * 70000})[0]
ok(big == 413, f"a 70 KB body is refused ({big})")

# ---- isolation ----
gw = ENV["DEMO_INT_SUBNET"].split("/")[0].rsplit(".", 1)[0] + ".1"          # the host, as the demo's network sees it
probe = ("import socket\nfor h, p in (('1.1.1.1', 443), ('8.8.8.8', 53), ('%s', 80), ('%s', 443), ('%s', 22), ('%s', 3389)):\n"
         "    s = socket.socket(); s.settimeout(3)\n"
         "    try:\n        s.connect((h, p)); print('OPEN', h, p)\n    except OSError:\n        pass\n"
         "try:\n    socket.getaddrinfo('example.com', 443); print('DNS')\nexcept OSError:\n    pass\n") % (
    ENV["DEMO_PROXY_IP"].rsplit(".", 1)[0] + ".1", ENV["DEMO_PROXY_IP"], gw, gw)
for c in (C["home"], C["sim"]):
    r = in_container(c, probe)
    ok(r.returncode == 0 and not r.stdout.strip(), f"{NAME[c]} reaches no LAN host, no internet, no DNS, not the host ({r.stdout.strip() or 'none'})")
r = subprocess.run(["docker", "exec", C["edge"], "wget", "-q", "-T", "4", "-O", "/dev/null", "http://1.1.1.1/"],
                   capture_output=True, timeout=30)
ok(r.returncode != 0, "the edge opens no connection out")
ports = subprocess.run(["docker", "ps", "--filter", "name=yashome-demo", "--format", "{{.Names}} {{.Ports}}"],
                       capture_output=True, text=True).stdout
published = [ln for ln in ports.splitlines() if "->" in ln]
ok(len(published) == 1 and "edge" in published[0], f"only the edge has a host port: {published}")
codes = [call("GET", "/api/health", tok)[0] for _ in range(60)]
ok(429 in codes and codes[0] == 200, f"the edge limits a burst of API calls ({codes.count(429)} of 60 refused)")
for c in (C["home"], C["sim"], C["mosquitto"], C["edge"]):
    i = json.loads(subprocess.run(["docker", "inspect", c], capture_output=True, text=True).stdout)[0]["HostConfig"]
    ok(i.get("ReadonlyRootfs") and i.get("CapDrop") == ["ALL"] and "no-new-privileges:true" in (i.get("SecurityOpt") or [])
       and i.get("PidsLimit"), f"{NAME[c]}: read-only, no capabilities, no new privileges, a process cap")
env = subprocess.run(["docker", "exec", C["home"], "env"], capture_output=True, text=True).stdout
ok(not any(ln.startswith(("HOME_LAT=", "HOME_LON=")) for ln in env.splitlines()), "no house coordinates in the backend")
print(f"{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
