"""ui_check.py <run dir>: the running demo's map as a guest sees it, in headless Chromium at 390 x 844 (a phone)
and 1280 x 800: no room name or temperature lies over an icon or a badge, comes within 9 px of a wall, is crossed by
a link, door, window or strip line, or leaves its room; every room shows its name; the header's menu button is on
the screen. Needs the repo's Python (websockets) and chromium. Exit 1 on any finding."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

RUN = Path(sys.argv[1])
ENV = dict(ln.split("=", 1) for ln in (RUN / "demo.env").read_text().splitlines() if "=" in ln and not ln.startswith("#"))
BASE = f"http://{ENV['DEMO_BIND']}:{ENV.get('DEMO_PORT', '8780')}"
CHROME = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
CHECK = r"""(async () => {
  const hits = [], svg = document.querySelector('[data-m=svg]');
  if (!svg) return ['no map'];
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && s.display !== 'none' && s.visibility !== 'hidden'; };
  const icons = [...document.querySelectorAll('[data-m=icons] [data-id], [data-m=icons] [data-cluster]')].filter(vis).map(e => [e, e.getBoundingClientRect()]);
  const over = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  const ctm = svg.getScreenCTM(), inv = ctm.inverse(), unitPx = Math.hypot(ctm.a, ctm.b) || 1;
  const toUser = (x, y) => new DOMPoint(x, y).matrixTransform(inv);
  // the plan's walls: the rectangles of its drawing (the map reads the same ones), in the plan's units
  let walls = [];
  try {
    const m = await Home.api('/api/map'), u = m.underlay;
    const t = await (await fetch('/api/map/underlay', {headers: Home.authHeaders()})).text();
    const doc = new DOMParser().parseFromString(t, 'image/svg+xml'), vb = (doc.documentElement.getAttribute('viewBox') || '0 0 1 1').split(/[\s,]+/).map(Number);
    const k = u.w / (vb[2] || 1);
    walls = [...doc.querySelectorAll('g[data-walls] rect')].map(r => ({x0: u.x + (+r.getAttribute('x') - vb[0]) * k, y0: u.y + (+r.getAttribute('y') - vb[1]) * k,
      x1: u.x + (+r.getAttribute('x') - vb[0] + +r.getAttribute('width')) * k, y1: u.y + (+r.getAttribute('y') - vb[1] + +r.getAttribute('height')) * k}));
  } catch (e) { hits.push('walls not read: ' + e); }
  const strokes = [...svg.querySelectorAll('line, path, polyline')].filter(e => !e.closest('text') && vis(e));
  for (const t of svg.querySelectorAll('text[data-z], text[data-zt]')) {
    if (!vis(t)) continue;
    const r = t.getBoundingClientRect(), name = t.textContent;
    const R = x => `${Math.round(x.left)},${Math.round(x.top)} ${Math.round(x.width)}x${Math.round(x.height)}`;
    for (const [e, b] of icons) if (over(r, b)) hits.push(`${name} (${R(r)}): over ${e.dataset.id || 'a badge'} (${R(b)})`);
    for (const o of svg.querySelectorAll('text[data-z], text[data-zt]')) if (o !== t && vis(o) && over(r, o.getBoundingClientRect())) hits.push(`${name} (${R(r)}): over the text "${o.textContent}"`);
    const cs = [[r.left, r.top], [r.right, r.top], [r.left, r.bottom], [r.right, r.bottom]].map(([x, y]) => toUser(x, y));
    const bx = {x0: Math.min(...cs.map(c => c.x)), x1: Math.max(...cs.map(c => c.x)), y0: Math.min(...cs.map(c => c.y)), y1: Math.max(...cs.map(c => c.y))};
    const pad = 9 / unitPx;                                       // a name keeps 9 px off a wall
    if (walls.some(w => w.x0 < bx.x1 + pad && bx.x0 - pad < w.x1 && w.y0 < bx.y1 + pad && bx.y0 - pad < w.y1)) hits.push(`${name} (${R(r)}): within 9 px of a wall`);
    const inside = (x, y) => x > bx.x0 + 0.5 && x < bx.x1 - 0.5 && y > bx.y0 + 0.5 && y < bx.y1 - 0.5;
    for (const e of strokes) {
      let cut = false;
      if (e.localName === 'line') {
        const x1 = +e.getAttribute('x1'), y1 = +e.getAttribute('y1'), x2 = +e.getAttribute('x2'), y2 = +e.getAttribute('y2');
        for (let k = 0; k <= 40 && !cut; k++) cut = inside(x1 + (x2 - x1) * k / 40, y1 + (y2 - y1) * k / 40);
      } else {
        const n = e.getTotalLength();
        for (let d = 0; d <= n && !cut; d += Math.max(0.5, n / 80)) { const q = e.getPointAtLength(d); cut = inside(q.x, q.y); }
      }
      if (cut) hits.push(`${name} (${R(r)}): crossed by ${e.dataset.a ? 'a link line' : 'a door, window or strip line'}`);
    }
    const poly = [...svg.querySelectorAll('polygon')].find(p => { const pt = svg.createSVGPoint(), c = toUser(r.left + r.width / 2, r.top + r.height / 2); pt.x = c.x; pt.y = c.y; return p.isPointInFill(pt); });
    if (!poly) { hits.push(`${name}: not in a room`); continue; }
    for (const c of cs) { const pt = svg.createSVGPoint(); pt.x = c.x; pt.y = c.y; if (!poly.isPointInFill(pt)) { hits.push(`${name}: leaves its room`); break; } }
  }
  for (const z of svg.querySelectorAll('text[data-z]')) if (!vis(z)) hits.push(`${z.textContent}: no name shown`);
  const menu = document.querySelector('.demo-pill [data-a=menu]');
  if (menu && vis(menu)) { const r = menu.getBoundingClientRect(); if (r.right > innerWidth || r.left < 0) hits.push('the menu button is off the screen'); }
  const names = [...svg.querySelectorAll('text[data-z]')].filter(vis).length, temps = [...svg.querySelectorAll('text[data-zt]')].filter(vis).length;
  return {hits, seen: `${names} names, ${temps} temperatures, ${icons.length} icons and badges, ${walls.length} walls, ${strokes.length} lines`};
})()"""


def login():
    r = urllib.request.Request(BASE + "/api/demo/login", method="POST", headers={"Content-Type": "application/json"},
                               data=json.dumps({"password": ENV["DEMO_PASSWORD"]}).encode())
    return json.loads(urllib.request.urlopen(r, timeout=10).read())["token"]


async def run(ws_url, tok):
    found = []
    async with websockets.connect(ws_url, max_size=20_000_000) as ws:
        n = 0

        async def cmd(method, **params):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == n:
                    return m.get("result", {})
        await cmd("Page.enable")
        first = True
        for w, h, mobile in ((390, 844, True), (1280, 800, False)):
            await cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mobile)
            await cmd("Page.navigate", url=f"{BASE}/?{'token=' + tok + '&' if first else ''}tab=p:map")
            first = False
            await asyncio.sleep(9)
            r = await cmd("Runtime.evaluate", expression=CHECK, returnByValue=True, awaitPromise=True)
            v = r.get("result", {}).get("value") or {}
            hits = v.get("hits", ["the check did not run"]) if isinstance(v, dict) else v
            print(f"{w}x{h}: {len(hits)} finding(s); checked {v.get('seen', '?') if isinstance(v, dict) else '?'}")
            found += [f"{w}: {x}" for x in hits]
    return found


def main():
    prof = Path(tempfile.mkdtemp(prefix="demo-ui-", dir=os.environ.get("HOME")))      # a snap Chromium cannot use /tmp
    chrome = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=9336",
                               f"--user-data-dir={prof}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                pages = json.loads(urllib.request.urlopen("http://127.0.0.1:9336/json/list", timeout=2).read())
                break
            except OSError:
                time.sleep(0.3)
        found = asyncio.run(run(next(t for t in pages if t.get("type") == "page")["webSocketDebuggerUrl"], login()))
    finally:
        chrome.terminate()
        chrome.wait(10)
        shutil.rmtree(prof, ignore_errors=True)
    for f in found:
        print("FAIL", f)
    sys.exit(1 if found else 0)


main()
