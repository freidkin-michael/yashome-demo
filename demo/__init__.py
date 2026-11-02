"""demo: the public demo of Yashome (README.md). With YASHOME_RESTRICTED=1 the core runs only the routes of routes.py;
this plug-in signs guests in by the shared demo password, gives control to one of them at a time and keeps the
others in line (lease.py)
and resets the house when a turn ends (seed.py, entry.py; the simulator clears the broker). Without demo mode
it registers its routes and refuses every sign-in."""
import asyncio
import hashlib
import hmac
import os
import secrets
import sys
import threading
import time
from pathlib import Path

import collections
import json
from typing import Literal, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

import app as core

from . import lease as leaselib
from . import limits, routes

PLUGIN = {"name": "Demo", "version": "1.0.0", "menu": False}    # nothing in it for a guest to set
HERE = Path(__file__).resolve().parent
PASSWORD = os.environ.get("DEMO_PASSWORD") or ""             # unset: nobody signs in
EDGE_IP = (os.environ.get("DEMO_EDGE_IP") or "").strip()     # the demo's own proxy (a fixed address): its X-Forwarded-For is the guest
RESET_WAIT_S = 5.0                                           # for the simulator's "broker clean" before the restart
RESET_TRIES = 3                                              # the restart asks again this often when it did not answer
FEEDBACK_URL = (os.environ.get("DEMO_FEEDBACK_URL") or "").strip()    # the end-of-session summary links it (none: no link)

_state_dir = Path(os.environ.get("DEMO_STATE_DIR") or core.plugin_state("demo"))
_state_dir.mkdir(parents=True, exist_ok=True)
LEASE = leaselib.Lease(_state_dir / "lease.json")
_salt_file = _state_dir / "salt"
if not _salt_file.exists():
    _salt_file.write_text(secrets.token_hex(16))
_SALT = _salt_file.read_text().strip()


def _anon(bucket: str) -> str:
    """What the lease keeps of a guest's address: a salted hash (no address is written to disk)."""
    return hashlib.sha256(f"{_SALT}|{bucket}".encode()).hexdigest()[:20]
LIMITS = limits.Limiter()
_reset_done = threading.Event()

core.RESTRICTED_ALLOW.update(routes.ALLOW)
core.RESTRICTED_ROLE.append(lambda tok, method, path: LEASE.role(tok, method, path) if core.RESTRICTED else None)
def _scopes() -> set:
    """What an order or a tile size may name: the dashboard's tabs (device categories, favourites) and its rooms."""
    rooms = [r.get("id") for r in core.get_rooms()]
    return ({d.get("category") for d in core.DEVICES.values()} | {"fav", "other", "auto", "tech"}
            | set(rooms) | {f"room:{r}" for r in rooms})


core.RESTRICTED_CHECKS.append(lambda method, path, params, body: limits.check(method, path, params, body, core.DEVICES, _scopes()))
core.TOKEN_CHECKS.append(lambda tok, method, path: core.RESTRICTED and LEASE.known(tok))
_PKG = __package__.rsplit(".", 1)[0]
PLAYGROUND_LIMITS = {"only": limits.PLAYGROUND, "hide": ["renPanel", "renTo", "delPanel", "flash", "panelRoom", "barBox"],
                     "notice": "Playground: shape this tablet as you like. It goes back to its start when your turn ends."}


async def _playground_limits():
    """The builder offers the playground only (panels loads after this plug-in: set once all are in)."""
    pn = sys.modules.get(_PKG + ".panels")
    if core.RESTRICTED and pn is not None:
        pn.BUILDER_LIMITS.update(PLAYGROUND_LIMITS)


core.STARTUP_TASKS.append(_playground_limits)
core.OPEN_PATHS.add("/try")
core.MQTT_NAMESPACES.add("demo")
core.MQTT_SUBSCRIPTIONS.extend(["demo/reset/done", "demo/sim/state"])
core.MQTT_HANDLERS.append((("demo", "reset", "done"), lambda parts, payload, retain: None if retain else _reset_done.set()))
_sim_state: dict = {}


def _on_sim_state(parts, payload, retain):
    try:
        _sim_state.clear()
        _sim_state.update(json.loads(payload))
    except (ValueError, TypeError):
        pass


core.MQTT_HANDLERS.append((("demo", "sim", "state"), _on_sim_state))

# ---- the feed: what the house did by itself (rules, schedules) and what the guest did, for toasts and the map ----
_feed: collections.deque = collections.deque(maxlen=200)
_feed_seq = [0]
_feed_lock = threading.Lock()


def _name(did) -> str:
    return str((core.DEVICES.get(did) or {}).get("name") or did or "")


_GESTURE = {"single": "pressed", "double": "pressed twice", "hold": "held", "true": "on", "false": "off",
            "above": "went above its threshold", "below": "went below its threshold"}


def _value(v) -> str:
    """A rule's result as words: {"state": "ON"} -> "on", {"brightness": 120} -> "brightness 120"."""
    if isinstance(v, dict):
        return ", ".join(str(x).lower() if str(k).startswith("state") else f"{k} {x}" for k, x in v.items())
    return str(v).lower() if v is not None else ""


def _on_event(ev: dict):
    kind, src = ev.get("kind"), str(ev.get("source") or "")
    if kind == "rule":
        text = f"{_name(ev.get('device'))} {_GESTURE.get(str(ev.get('gesture')), ev.get('gesture'))} -> {_name(ev.get('target'))} {_value(ev.get('value'))}"
        who, dev = "rule", ev.get("target")
        LEASE.note_rule()
    elif kind == "command" and src.startswith(("schedule", "inching", "timer")):
        text, who, dev = f"{_name(ev.get('device'))} {ev.get('code')} -> {ev.get('new')} ({src.split(':')[0]})", "rule", ev.get("device")
    elif kind == "command" and src in ("app", "", "dashboard"):
        text, who, dev = f"{_name(ev.get('device'))} {ev.get('code')} -> {ev.get('new')}", "guest", ev.get("device")
    else:
        return
    with _feed_lock:
        last = _feed[-1] if _feed else None
        if last and last["text"] == text[:160] and time.time() - last["ts"] < 10:      # a rule that repeats is one line, counted
            last["n"] = last.get("n", 1) + 1
            last["ts"] = time.time()
            return
        _feed_seq[0] += 1
        _feed.append({"seq": _feed_seq[0], "ts": time.time(), "who": who, "device": dev, "src": ev.get("device"), "text": text[:160]})


core.ON_EVENT.append(_on_event)


def _token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else (request.headers.get("x-token") or "")


def client_bucket(request: Request) -> "str | None":
    """The guest's address bucket from the demo proxy's X-Forwarded-For; None (refuse) for a request that did
    not come through that proxy or carries no valid address."""
    peer = request.client.host if request.client else ""
    if not EDGE_IP or peer != EDGE_IP:
        return None
    return limits.bucket((request.headers.get("x-forwarded-for") or "").split(",")[-1])


def _refused(e: leaselib.Refused):
    raise HTTPException(429 if e.wait_s else e.code, e.why, headers={"Retry-After": str(e.wait_s)} if e.wait_s else None)


class LoginBody(BaseModel):
    password: str = Field(max_length=256)
    login: str = Field(default="", max_length=64)          # an older sign-in page still sends a name: ignored


@core.app.post("/api/demo/login")
def demo_login(body: LoginBody, request: Request):
    """The shared demo password (no name) gives a session of its own: in control when the flat is free, else in
    line (the page waits and enters by itself); refused when its network has a turn or a place already."""
    if not core.RESTRICTED or not PASSWORD:
        raise HTTPException(403, "this house is not a demo")
    ip = client_bucket(request)
    if ip is None:
        core.log.error("[demo] a sign-in came without the demo proxy's address: refused")
        raise HTTPException(503, "try later")
    why = LIMITS.attempt(ip)
    if why:
        raise HTTPException(429, why, headers={"Retry-After": str(limits.WINDOW_S)})
    if not hmac.compare_digest(body.password.encode(), PASSWORD.encode()):
        LIMITS.failed(ip)
        core.log.warning(f"[demo] sign-in refused ({_anon(ip)[:8]})")      # never an address in the log
        raise HTTPException(401, "wrong password")
    try:
        tok = LEASE.login(_anon(limits.net(ip)))
    except leaselib.Refused as e:
        _refused(e)
    LIMITS.signed_in(ip)
    return {"token": tok}


core.open_route(demo_login)


@core.app.get("/try")
def demo_try_page():
    return HTMLResponse((HERE / "static" / "try.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-cache"})


@core.app.get("/api/demo/state")
def demo_state(request: Request):
    return LEASE.view(_token(request))


@core.app.post("/api/demo/heartbeat")
def demo_heartbeat(request: Request):
    """Every open tab beats (every 9 s in control, 3 s in line): a controller's tab that stops (closed) frees
    control in 30 s."""
    LEASE.heartbeat(_token(request))
    return LEASE.view(_token(request))


class ByeBody(BaseModel):
    token: str = Field(max_length=256)


@core.app.post("/api/demo/bye")
def demo_bye(body: ByeBody):
    """The page closes (pagehide): a beacon cannot carry a header, so the token comes in the body. Unless the tab
    beats again within 30 s (a reload), its turn or place in line ends; a tab that is only hidden keeps it."""
    LEASE.bye(body.token)
    return {"ok": True}


core.open_route(demo_bye)


@core.app.post("/api/demo/still")
def demo_still(request: Request):
    return LEASE.still(_token(request))


@core.app.post("/api/demo/take")
def demo_take(request: Request):
    """After a turn: get in line again (the turn at once when the flat is free)."""
    try:
        return LEASE.take(_token(request))
    except leaselib.Refused as e:
        _refused(e)


@core.app.post("/api/demo/leave")
def demo_leave(request: Request):
    """Out of the line, still signed in (the page offers to get in line again)."""
    return LEASE.leave(_token(request))


@core.app.post("/api/demo/logout")
def demo_logout(request: Request):
    LEASE.logout(_token(request))
    return {"ok": True}


@core.app.post("/api/demo/release")
def demo_release(request: Request):
    """Give control back; the house resets for the next guest (a short turn with no action needs none)."""
    LEASE.release(_token(request))
    return LEASE.view(_token(request))


@core.app.post("/api/demo/dismiss")
def demo_dismiss(request: Request):
    """The end-of-session summary was read."""
    LEASE.dismiss(_token(request))
    return LEASE.view(_token(request))


@core.app.get("/api/demo/feed")
def demo_feed(after: int = 0):
    with _feed_lock:
        return {"seq": _feed_seq[0], "items": [e for e in _feed if e["seq"] > after][-50:], "feedback": FEEDBACK_URL}


# ---- the simulator, steered by the guest in control ----
SIM_EVENTS = ("doorbell", "leak", "leak_dry", "smoke", "smoke_clear", "window_open", "window_close")
ROOMS = ("living", "kitchen", "bedroom", "kids", "hall", "bath")


class SpeedBody(BaseModel):
    x: Literal[1, 10, 60]


class WeatherBody(BaseModel):
    mode: Literal["clear", "cloudy", "rain", "heatwave", "auto"]       # auto: back to the day's own weather


class EventBody(BaseModel):
    name: Literal[SIM_EVENTS]


class MoveBody(BaseModel):
    who: Literal["Alex", "Sam", "Mia"]
    room: Optional[Literal[ROOMS]] = Field(default=None)


def _sim(topic: str, payload: str):
    cli = core.mqtt_client
    if cli is None:
        raise HTTPException(503, "the simulator is not reachable")
    core.mqtt_pub(cli, f"demo/sim/{topic}", payload)
    return {"ok": True}


@core.app.get("/api/demo/sim")
def demo_sim_state():
    return dict(_sim_state)


# ---- the sim's weather and balcony camera, for the playground's widgets (the demo has no weather or camera plug-in)
def _forecast() -> dict:
    """The sim's weather as Open-Meteo answers it (what the weather tile reads), from the same day script as the sim: the first
    hour is now (the sim's own weather and temperature), then the script; a guest's held weather lasts until it ends."""
    from .sim import weather_day as WD
    s = dict(_sim_state)
    t0, mode, t = float(s.get("t") or time.time()), s.get("weather") or "clear", float(s.get("outdoor") or 17.0)
    held = s.get("held_until")
    held_t = None
    if held:
        lt = time.localtime(t0)
        hh, mm = (int(x) for x in str(held).split(":"))
        held_t = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
        held_t += 86400 if held_t < t0 else 0
    at = lambda ts: mode if (ts == t0 or (held_t and ts < held_t)) else WD.mode_at(ts)    # noqa: E731
    day = lambda ts: 1 if 7 <= time.localtime(ts).tm_hour < 19 else 0                     # noqa: E731
    hours = [t0] + [(t0 // 3600 + i) * 3600 for i in range(1, 24)]
    modes = [at(h) for h in hours]
    midnight = time.mktime(time.localtime(t0)[:3] + (0, 0, 0, 0, 0, -1))
    days = []
    for d in range(4):
        hs = [midnight + d * 86400 + k * 3600 for k in range(24)]
        ms = [at(h) for h in hs if 6 <= time.localtime(h).tm_hour <= 20]
        worst = max(ms, key=lambda m: (WD.RAIN_PROB[m], m == "heatwave"))
        temps = [WD.target(h, at(h)) for h in hs]
        days.append((time.strftime("%Y-%m-%d", time.localtime(hs[0])), worst, max(temps), min(temps), max(WD.RAIN_PROB[m] for m in ms)))
    temps = [t] + [round(WD.target(h, m), 1) for h, m in zip(hours[1:], modes[1:])]
    return {"fetched_at": int(time.time()),
            "current": {"temperature_2m": t, "apparent_temperature": round(t - 1, 1), "weather_code": WD.CODE[mode], "is_day": day(t0),
                        "precipitation": 0.4 if mode == "rain" else 0.0,
                        "relative_humidity_2m": {"rain": 92, "cloudy": 70, "heatwave": 35}.get(mode, 55),
                        "wind_speed_10m": {"rain": 6, "cloudy": 4}.get(mode, 2)},
            "hourly": {"time": [time.strftime("%Y-%m-%dT%H:00", time.localtime(h)) for h in hours], "temperature_2m": temps,
                       "weather_code": [WD.CODE[m] for m in modes], "is_day": [day(h) for h in hours],
                       "precipitation_probability": [WD.RAIN_PROB[m] for m in modes]},
            "daily": {"time": [x[0] for x in days], "weather_code": [WD.CODE[x[1]] for x in days],
                      "temperature_2m_max": [round(x[2], 1) for x in days], "temperature_2m_min": [round(x[3], 1) for x in days],
                      "precipitation_probability_max": [x[4] for x in days]}}


def _sky(h: int, mode: str) -> tuple:
    """The sky's top and bottom colours at this hour in this weather."""
    if h < 6 or h >= 21:
        return ("#070b1a", "#1a2440")
    if h < 8 or h >= 19:
        return ("#3b4f86", "#f2a65a") if mode in ("clear", "heatwave") else ("#4a5466", "#8b8f99")
    return {"clear": ("#3d8ee6", "#a9d5ff"), "heatwave": ("#5aa0e8", "#ffd9a0"), "cloudy": ("#8d98a6", "#c5ccd4"),
            "rain": ("#5c6672", "#8d969f")}.get(mode, ("#3d8ee6", "#a9d5ff"))


def _still() -> bytes:
    """The balcony camera: a view through the window whose sky follows the sim's clock and weather (no real camera)."""
    s = dict(_sim_state)
    mode, hhmm = s.get("weather") or "clear", str(s.get("time") or time.strftime("%H:%M"))
    h = int(hhmm[:2] or 12)
    night, (top, bottom) = h < 6 or h >= 21, _sky(h, mode)
    stars = "".join(f'<circle cx="{x}" cy="{y}" r="1.2" fill="#fff" opacity=".8"/>' for x, y in
                    ((40, 40), (95, 22), (150, 58), (230, 30), (300, 50), (380, 26), (420, 64), (500, 36), (610, 44))) if night and mode != "rain" else ""
    sun = ('<circle cx="560" cy="70" r="24" fill="#fff4c2"/><circle cx="560" cy="70" r="34" fill="#fff4c2" opacity=".25"/>'
           if not night and mode in ("clear", "heatwave") else
           '<circle cx="560" cy="62" r="18" fill="#e9edf7"/><circle cx="567" cy="56" r="16" fill="' + top + '"/>' if night and mode != "rain" else "")
    clouds = "".join(f'<g opacity=".9" fill="{"#c9d0d8" if not night else "#3a4256"}"><ellipse cx="{x}" cy="{y}" rx="60" ry="16"/>'
                     f'<ellipse cx="{x + 30}" cy="{y - 10}" rx="34" ry="14"/></g>' for x, y in ((120, 66), (330, 88), (480, 58))) \
        if mode in ("cloudy", "rain") else ""
    drops = "".join(f'<line x1="{x}" y1="{y}" x2="{x - 5}" y2="{y + 14}" stroke="#d6e6ff" stroke-width="1.6" opacity=".8"/>'
                    for x in range(18, 640, 31) for y in (40, 96, 150)) if mode == "rain" else ""
    blocks = ((0, 112, 92), (96, 92, 66), (166, 124, 104), (274, 80, 78), (356, 118, 116), (476, 100, 164))
    town = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{190 - y}" fill="{"#1d2533" if night else "#4a5568"}"/>' for x, y, w in blocks)
    lit = "".join(f'<rect x="{x + dx}" y="{y + dy}" width="7" height="9" fill="#ffcf6e"/>'
                  for i, (x, y, w) in enumerate(blocks) for dx in range(10, w - 12, 18) for dy in range(14, 190 - y - 12, 22)
                  if (i * 7 + dx + dy) % 3 == 0) if (night or h >= 18 or h < 8) else ""
    rail = '<rect y="176" width="640" height="6" fill="#2b2f36"/>' + "".join(
        f'<rect x="{x}" y="182" width="3" height="38" fill="#2b2f36"/>' for x in range(8, 640, 22))
    plant = lambda x: (f'<path d="M{x - 18} 200 h36 l-5 20 h-26 z" fill="#8a5a3c"/>'                     # noqa: E731
                       f'<path d="M{x} 200 C{x - 30} 170 {x - 22} 150 {x - 6} 160 M{x} 200 C{x + 4} 160 {x + 18} 150 {x + 24} 168 '
                       f'M{x} 200 C{x - 4} 180 {x + 2} 160 {x} 146" fill="none" stroke="#3e8e4f" stroke-width="7" stroke-linecap="round"/>')
    frame = ('<rect x="3" y="3" width="634" height="214" fill="none" stroke="#e6e2da" stroke-width="10" rx="4"/>'
             '<rect x="318" y="3" width="6" height="214" fill="#e6e2da"/>')
    t = s.get("outdoor")
    label = "Balcony  " + hhmm + (f"  {t}\u00b0C" if t is not None else "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="220" viewBox="0 0 640 220">'
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
           f'<stop offset="1" stop-color="{bottom}"/></linearGradient></defs>'
           f'<rect width="640" height="220" fill="url(#g)"/>{stars}{sun}{clouds}{town}{lit}{drops}{rail}{plant(70)}{plant(590)}{frame}'
           f'<rect x="8" y="8" width="230" height="24" rx="4" fill="#000" opacity=".45"/>'
           f'<text x="16" y="25" font-family="sans-serif" font-size="15" fill="#fff">{label}</text></svg>')
    return svg.encode()


def _plugin_on(name: str) -> bool:
    """The plug-in is on in this deployment (PLUGINS), loaded yet or not."""
    on = core._enabled_plugins()
    return on is None or name in on


OWN_ROUTES = {"weather": [("GET", "/api/weather")], "cameras": [("GET", "/api/cameras"), ("GET", "/api/camera/{cid}/snapshot")]}


# the demo's own answers (from the simulator) for routes whose real plug-ins are not in the demo stack (compose.demo.yml)

if core.RESTRICTED and not _plugin_on("weather"):
    @core.app.get("/api/weather")
    def demo_weather():
        return _forecast()

if core.RESTRICTED and not _plugin_on("cameras"):
    @core.app.get("/api/cameras")
    def demo_cameras():
        return [{"id": limits.SIM_CAMERA, "name": "Balcony camera"}]

    @core.app.get("/api/camera/{cid}/snapshot")
    def demo_camera(cid: str):
        if cid != limits.SIM_CAMERA:
            raise HTTPException(404, "no such camera")
        return Response(_still(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@core.app.post("/api/demo/sim/speed")
def demo_sim_speed(body: SpeedBody):
    return _sim("speed", str(body.x))


@core.app.post("/api/demo/sim/weather")
def demo_sim_weather(body: WeatherBody):
    return _sim("weather", body.mode)


@core.app.post("/api/demo/sim/event")
def demo_sim_event(body: EventBody):
    return _sim("event", body.name)


@core.app.post("/api/demo/sim/move")
def demo_sim_move(body: MoveBody):
    return _sim("move", f"{body.who}={body.room or ''}")


# ---- the public showcase: a picture of the map and a short film, no sign-in ----
SHOWCASE = {"/showcase": ("showcase.html", "text/html"), "/showcase/map.png": ("map.png", "image/png"),
            "/showcase/tour.webm": ("tour.webm", "video/webm")}
core.OPEN_PATHS.update(SHOWCASE)


def _showcase(path: str):
    name, mime = SHOWCASE[path]
    f = (HERE / "static" / name) if name.endswith(".html") else (_state_dir / "showcase" / name)
    if not f.is_file():
        raise HTTPException(404, "not made yet")
    return FileResponse(f, media_type=mime, headers={"Cache-Control": "public, max-age=300"})


@core.app.get("/showcase")
def demo_showcase():
    return _showcase("/showcase")


@core.app.get("/showcase/map.png")
def demo_showcase_map():
    return _showcase("/showcase/map.png")


@core.app.get("/showcase/tour.webm")
def demo_showcase_film():
    return _showcase("/showcase/tour.webm")


@core.app.post("/api/demo/reset")
def demo_reset(request: Request):
    """The guest in control starts over (the page asks first) and keeps control: once a turn."""
    try:
        LEASE.use_reset(_token(request))
    except leaselib.Refused as e:
        _refused(e)
    _schedule_reset("reset by the guest")
    return {"ok": True, "resetting": True}


# ---- the reset: the simulator cleans the broker, then the backend exits and starts on the pristine house ----
def _exit():                                   # a test replaces it
    os._exit(0)


_resetting = threading.Lock()


def _schedule_reset(why: str):
    if not _resetting.acquire(blocking=False):
        return
    core.log.warning(f"[demo] reset: {why}")
    core.emit_event({"kind": "demo", "device": "demo", "code": "reset", "new": why, "source": "demo", "ts": time.time()})

    def run():
        try:
            if _ask_sim(why):
                LEASE.sim_clean()
        finally:
            time.sleep(0.3)                    # the answer of the route that asked goes out first
            _exit()
    threading.Thread(target=run, daemon=True, name="demo-reset").start()


def _ask_sim(why: str) -> bool:
    """Asks the simulator to clean the broker (demo/reset); True once it answers (demo/reset/done)."""
    _reset_done.clear()
    end = time.monotonic() + RESET_WAIT_S
    cli = core.mqtt_client
    while cli is None or not getattr(cli, "is_connected", lambda: True)():
        if time.monotonic() >= end:
            return False
        time.sleep(0.2)
        cli = core.mqtt_client
    try:
        cli.publish("demo/reset", why, qos=1)
    except Exception as e:                      # noqa: BLE001
        core.log.warning(f"[demo] reset: {e}")
        return False
    return _reset_done.wait(max(0.5, end - time.monotonic()))


async def _finish_reset():
    """After the restart of a reset: when the simulator did not answer before it, asked again (RESET_TRIES at
    most); then the turn goes to the next in line, on the pristine house."""
    if not core.RESTRICTED or not LEASE.resetting:
        return
    if LEASE.resetting != "clean":
        for _ in range(RESET_TRIES):
            if await asyncio.to_thread(_ask_sim, "after the restart"):
                break
        else:
            core.log.error("[demo] the simulator did not answer the reset: the last turn's devices may stay")
    LEASE.reset_finished()


async def _watch_turns():
    """Ends turns that are over (cap, idle, a closed tab) and resets the house after each one."""
    await _finish_reset()
    while True:
        LEASE.tick()
        why = LEASE.take_reset()          # at most one reset per RESET_GAP_S; the line waits for it
        if why and core.RESTRICTED:
            _schedule_reset(why)
        await asyncio.sleep(1)


core.STARTUP_TASKS.append(_watch_turns)
