"""house_words.py <house dir> <.env>... : what of a REAL house must never be in the demo, one item per line on
stdout as "name<TAB>..." or "secret<TAB>...", for leak_scan.py to read from a pipe (nothing is written to disk):
device and room names, the Zigbee friendly names; secrets: the coordinates and the values of its keys. Read only."""
import json
import re
import sys
from pathlib import Path

out = set()


def name(v):
    if isinstance(v, str) and len(v.strip()) >= 4:
        out.add(("name", v.strip()))


house = Path(sys.argv[1])
for f in ("mqtt_devices.json",):
    try:
        for d in json.loads((house / f).read_text(encoding="utf-8")):
            name(d.get("name"))
            name(d.get("id"))
    except (OSError, ValueError):
        pass
try:
    s = json.loads((house / "settings.json").read_text(encoding="utf-8"))
    for r in s.get("rooms") or []:
        name(r.get("name"))
    for v in (s.get("names") or {}).values():
        name(v)
    for src in s.get("bindings") or {}:
        name(src)
except (OSError, ValueError):
    pass
for y in list(house.parent.glob("*/zigbee2mqtt*/configuration.yaml")) + list(house.rglob("configuration.yaml")):
    for m in re.finditer(r"friendly_name:\s*['\"]?([^'\"\n]+)", y.read_text(encoding="utf-8", errors="replace")):
        name(m.group(1))
for env in sys.argv[2:]:
    try:
        lines = Path(env).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        continue
    for ln in lines:
        k, _, v = ln.partition("=")
        v = v.strip().strip("'\"")
        if re.search(r"TOKEN|KEY|PASSWORD|SECRET|_LAT$|_LON$", k.strip()) and len(v) >= 6:
            out.add(("secret", v))
for kind, w in sorted(out):
    print(f"{kind}\t{w}")
