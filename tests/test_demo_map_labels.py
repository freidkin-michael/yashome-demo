"""The demo flat on the engine's map screen (its ui.js at the pin, a real headless Chrome): at the size the map pane has in a
1280 px wide window, every thing on the plan shows its name, none on another name or a room's. The page gets the seed's map, wires from its links, the
blaster's IR line and the catalog's names, the way the house serves them."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2]
DEMO = ENGINE / "plugins" / "tools" / "demo"
sys.path.insert(0, str(DEMO / "sim"))
import catalog  # noqa: E402

import app  # noqa: E402,F401  (loads the plug-ins: the demo is yashome_plugins.demo)
seedgen = __import__("importlib").import_module("yashome_plugins.demo.sim.seedgen")

CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
CATEGORY = {"tv": "tv", "ac": "climate", "switch": "switch", "switch2": "switch", "dimmer": "light", "plug": "switch", "relay": "switch",
            "blaster": "ir", "climate": "sensor", "weather": "sensor", "air": "sensor", "contact": "sensor", "motion": "sensor",
            "leak": "sensor", "smoke": "sensor", "radar": "sensor", "button": "button", "lock": "lock", "meter": "sensor", "heater": "switch"}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;background:#0e1116;color:#ddd;font-family:sans-serif}</style></head>
<body><div id="app" style="width:%(w)dpx"></div><pre id="out"></pre><script>
window.onerror = (m, src, l) => { document.getElementById('out').textContent += 'ERROR ' + m + ' @' + src + ':' + l + '\\n'; };
window.i18n = s => s; window.STATE = {}; window.RESTRICTED = true;      // the demo: read-only, its icons a finger size
const D = %(data)s;
window.Home = {escapeHtml: s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])),
  api: async url => ({'/api/map': D.map, '/api/map/candidates': D.cands, '/api/wiring': D.wiring, '/api/map/auto': D.auto})[url] || [],
  authHeaders: h => h || {}, state: id => window.STATE[id]};
window.fetch = async () => ({ok: true, text: async () => D.svg, blob: async () => new Blob([D.svg], {type: 'image/svg+xml'})});
window.HomePlugins = {register(p){ window.__p = p; }};
</script><script src="display.js"></script><script src="ui.js?v=111"></script><script>
(async () => {
  const box = document.getElementById('app');
  await __p.tabs[0].render(box); await new Promise(r => setTimeout(r, 1500));
  const v = box.querySelector('[data-m="view"]').getBoundingClientRect();
  const overlaps = () => { const R = e => e.getBoundingClientRect(), hit = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
    const M = [...box.querySelectorAll('[data-id] .mn')].filter(m => { const s = getComputedStyle(m); return m.closest('[data-id]').offsetParent && s.visibility !== 'hidden' && s.display !== 'none'; });
    const T = [...box.querySelectorAll('svg text[data-fs]')].filter(t => getComputedStyle(t).display !== 'none'), out = [];
    for (const m of M) { for (const t of T) if (hit(R(m), R(t))) out.push(m.textContent + ' x ' + t.textContent);
      for (const k of M) if (k !== m && m.textContent < k.textContent && hit(R(m), R(k))) out.push(m.textContent + ' x ' + k.textContent); }
    return out; };
  const N = [...box.querySelectorAll('[data-id] .mn')].filter(m => m.closest('[data-id]').offsetParent).map(m => { const s = getComputedStyle(m);
    return [m.closest('[data-id]').title, s.visibility !== 'hidden' && s.display !== 'none' && m.getBoundingClientRect().width > 0]; });
  document.getElementById('out').textContent = JSON.stringify({view: [Math.round(v.width), Math.round(v.height)],
    big: box.querySelector('[data-m="stage"]').classList.contains('big'), names: N.length, hidden: N.filter(n => !n[1]).map(n => n[0]), overlaps: overlaps()}) + '\\nDONE';
})();
</script></body></html>"""


def _data():
    house = DEMO / "house" / "plugin-data" / "map"
    m = json.loads((house / "map.json").read_text())
    for i in m["items"]:
        i.setdefault("path", [])
    m.update(scheme=m["canvas"], scheme_img=True, ui_v=111, load_types=["lamp", "socket", "ac", "tv", "boiler", "led", "fan", "other"])     # as GET /api/map adds them
    cands = [{"id": f"blaster:{seedgen.IR_NODE}" if d["type"] == "blaster" else d["id"], "name": d.get("name", d["id"]),
              "category": CATEGORY.get(d["type"], "sensor"), "room": d["room"], "online": True, "members": []} for d in catalog.DEVICES]
    cands.append({"id": seedgen.IR_FAN["id"], "name": seedgen.IR_FAN["name"], "category": "ir", "room": "living", "online": True, "members": [],
                  "ir_appliance": True})
    wiring = {"entries": [{"id": f"w{n}", "switch": {"dev": lk["dev"], "code": lk["code"]}, "target": {"load": lk["load"]}, "note": ""}
                          for n, lk in enumerate(m["links"])], "state": "ok"}
    auto = [{"from": f"blaster:{seedgen.IR_NODE}", "to": seedgen.IR_FAN["id"], "via": "ir", "note": ""}]
    return {"map": m, "cands": cands, "wiring": wiring, "auto": auto, "svg": (house / "scheme.svg").read_text()}


def _render(w, h):
    with tempfile.TemporaryDirectory() as d:
        shutil.copy(ENGINE / "plugins" / "tools" / "map" / "ui.js", d)
        shutil.copy(ENGINE / "display.js", d)
        Path(d, "page.html").write_text(PAGE % {"w": w, "data": json.dumps(_data())})
        page = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", f"--window-size={w},{h}", "--virtual-time-budget=20000",
                               f"--user-data-dir={d}/chrome", "--dump-dom", f"file://{d}/page.html"], capture_output=True, text=True, timeout=90)
    log = page.stdout.split('<pre id="out">', 1)[-1].split("</pre>", 1)[0]
    assert "DONE" in log, (log, page.stdout[-300:], page.stderr[-600:])
    return json.loads(log.split("\n", 1)[0])


@pytest.mark.skipif(CHROME is None, reason="no Chrome here")
def test_every_name_in_the_demo_flat_shows_at_1280():
    r = _render(960, 748)                             # the map pane of a 1280 x 800 window in the demo: 960 x 553
    assert r["view"] == [960, 553] and r["big"] and r["names"] >= 35, r
    assert r["hidden"] == [] and r["overlaps"] == [], r                    # every name shows, none on another name or on a room's name
