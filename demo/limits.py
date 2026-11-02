"""Limits of the public demo: the sign-in limiter (per client bucket, an IPv4 address or an IPv6 /64, per network,
and fewer tries per network while many networks fail) and the checks of what a guest in control may store
(lengths and counts of free text, the core's own rule actions only). Pure: the plug-in wires them (core.RESTRICTED_CHECKS)."""
import ipaddress
import json
import re
import threading
import time
from collections import OrderedDict

WINDOW_S = 600           # the limiter's memory
FAIL_MAX = 5             # wrong passwords per bucket in the window
TRY_MAX = 20             # sign-in tries per bucket in the window
NEW_MAX = 10             # new sessions per bucket in the window
GLOBAL_NETS_MAX = 50     # networks (IPv4 /24, IPv6 /48) with wrong passwords in the window: a storm for PAUSE_S
NET_FAIL_MAX = 20        # wrong passwords of one network in the window (many addresses of one network)
STORM_NET_FAIL_MAX = 2   # the same in a storm: a network that did not fail still signs in
PAUSE_S = 300
BUCKETS_MAX = 5000


def net(bucket_: str) -> str:
    """The network a bucket lies in: an IPv4 /24, an IPv6 /48. One guest or one attacker, many addresses."""
    try:
        n = ipaddress.ip_network(bucket_, strict=False)
    except ValueError:
        return bucket_
    return str(n.supernet(new_prefix=24 if n.version == 4 else 48))


def bucket(ip: str) -> "str | None":
    """An IPv4 address as it is, an IPv6 address as its /64; None for anything else."""
    try:
        a = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    if a.version == 4:
        return str(a)
    if a.ipv4_mapped is not None:
        return str(a.ipv4_mapped)
    return str(ipaddress.ip_network(f"{a}/64", strict=False))


class Limiter:
    def __init__(self, clock=time.time):
        self.clock, self.lock = clock, threading.Lock()
        self.b: OrderedDict = OrderedDict()      # bucket -> {"tries": [t], "fails": [t], "new": [t]}, least recent first
        self.fails: dict = {}                    # network -> its failures in the window: its own cap and the global one
        self.storm_until = 0.0

    def _get(self, k):
        now = self.clock()
        e = self.b.get(k)
        if e is None:
            if len(self.b) >= BUCKETS_MAX:      # forget the least recent bucket that holds no lock
                drop = next((x for x, v in self.b.items() if not self._locked(v, now)), None)
                if drop is None:
                    return None
                del self.b[drop]
            e = self.b[k] = {"tries": [], "fails": [], "new": []}
        self.b.move_to_end(k)
        for v in e.values():
            v[:] = [t for t in v if now - t < WINDOW_S]
        return e

    @staticmethod
    def _locked(e, now) -> bool:
        live = lambda v: sum(1 for t in v if now - t < WINDOW_S)   # noqa: E731
        return live(e["fails"]) >= FAIL_MAX or live(e["tries"]) >= TRY_MAX or live(e["new"]) >= NEW_MAX

    def attempt(self, k: str) -> "str | None":
        """A sign-in try from bucket k: why it is refused now, or None (counted)."""
        with self.lock:
            now = self.clock()
            self.fails = {n: [t for t in v if now - t < WINDOW_S] for n, v in self.fails.items()}
            self.fails = {n: v for n, v in self.fails.items() if v}
            cap = STORM_NET_FAIL_MAX if now < self.storm_until else NET_FAIL_MAX
            if len(self.fails.get(net(k), [])) >= cap:
                return "too many tries: wait 10 minutes"
            e = self._get(k)
            if e is None:
                return "too many guests at once: try later"
            if self._locked(e, now):
                return "too many tries: wait 10 minutes"
            e["tries"].append(now)
            return None

    def failed(self, k: str):
        with self.lock:
            now = self.clock()
            e = self._get(k)
            if e is not None:
                e["fails"].append(now)
            n = net(k)
            if n not in self.fails and len(self.fails) >= 10000:
                return
            self.fails.setdefault(n, []).append(now)
            if len(self.fails) >= GLOBAL_NETS_MAX:      # many networks at once: each one gets fewer tries, nobody
                self.storm_until = now + PAUSE_S        # is locked out who did not fail

    def signed_in(self, k: str):
        with self.lock:
            e = self._get(k)
            if e is not None:
                e["new"].append(self.clock())


# ---- what a guest in control may store ----
CORE_ACTIONS = {"on", "off", "toggle", "bright_up", "bright_down", "press"}
ALIAS = re.compile(r"^[A-Za-z0-9 ]{1,24}$")
SENSOR_GESTURES = {"true", "false", "above", "below"}
WRITES_PER_S, WRITES_BURST = 2.0, 6.0
_bucket = {"tokens": WRITES_BURST, "at": 0.0}
_bucket_lock = threading.Lock()


def write_allowed(now=None) -> bool:
    """The guest in control writes at most WRITES_PER_S a second (a burst of WRITES_BURST)."""
    with _bucket_lock:
        now = time.monotonic() if now is None else now
        _bucket["tokens"] = min(WRITES_BURST, _bucket["tokens"] + (now - _bucket["at"]) * WRITES_PER_S)
        _bucket["at"] = now
        if _bucket["tokens"] < 1:
            return False
        _bucket["tokens"] -= 1
        return True
BINDING_KEYS = {"target", "code", "action", "threshold", "hyst", "conditions", "for_sec", "retrigger", "time_window"}
SHORT = re.compile(r"^[A-Za-z0-9 ._:/|-]{0,64}$")
NAME_KEYS = {"name", "label", "title", "text", "alias", "new_name", "to", "friendly_name", "caption"}
LINKISH = re.compile(r"(?i)https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|ru|il|dev|app|me|info|co|xyz|ly|gg)\b"
                     r"|\S+@\S+\.\w{2,}|\+?\d[\d\s().-]{7,}\d")       # a link, an e-mail address, a phone number
BIG = {"/api/map", "/api/wiring", "/api/map/zones", "/api/map/rooms", "/api/map/rooms/{rid}"}     # whole documents: the core's own limit


def _names_ok(o) -> bool:
    """No name in the body holds a link, an e-mail address or a phone number: names show on the page."""
    if isinstance(o, dict):
        return all(not (k in NAME_KEYS and isinstance(v, str) and LINKISH.search(v)) and _names_ok(v) for k, v in o.items())
    return all(_names_ok(v) for v in o) if isinstance(o, list) else True


def _scalar(v, n=32) -> bool:
    return v is None or isinstance(v, (bool, int, float)) or isinstance(v, str) and len(v) <= n


def _ids_ok(xs, n=100, size=300) -> bool:
    return isinstance(xs, list) and len(xs) <= n and all(isinstance(x, str) and len(x) <= size for x in xs)


PLAYGROUND, SIM_CAMERA = "playground", "sim-balcony"
LAYOUT_MAX_BYTES, LAYOUT_MAX_WIDGETS = 32 * 1024, 40   # the gate refuses past 64 KB (413) before this
TOPIC_KEY = re.compile(r"(topic|_state|_cmd)$")


def _demo_topic(t: str, devices: dict, own: set) -> bool:
    """A device's own topic, or the house bus of a device of the flat (home/state|cmd/<id>/<code>)."""
    lv = t.split("/")
    return t in own or (len(lv) == 4 and lv[0] == "home" and lv[1] in ("state", "cmd") and lv[2] in devices and bool(lv[3]))


def _layout(params: dict, body: bytes, devices) -> "str | None":
    """The playground: the one panel a guest may shape; small, and bound only to the demo flat's devices."""
    if params.get("name") != PLAYGROUND:
        return "only the playground panel can be changed in the demo"
    if len(body) > LAYOUT_MAX_BYTES:
        return "the layout is too big"
    try:
        b = json.loads(body)
    except ValueError:
        return "the body must be JSON"
    ws = b.get("widgets") if isinstance(b, dict) else None
    if not isinstance(ws, list) or len(ws) > LAYOUT_MAX_WIDGETS:
        return f"a layout has at most {LAYOUT_MAX_WIDGETS} widgets"
    if b.get("hw") not in (None, "android") or b.get("bar"):
        return "the playground is a tablet without status bar buttons"
    if not _names_ok(b):
        return "a name may not hold a link, an e-mail address or a phone number"
    devices = devices or {}
    own = {t for d in devices.values() for c in d.get("controls") or [] for t in (c.get("state_topic"), c.get("command_topic")) if t}
    for w in ws:
        if not isinstance(w, dict):
            return "a widget is an object"
        for k, v in w.items():
            if k == "device" and v not in devices:
                return "a widget names a device the demo flat does not have"
            if k == "cam_id" and v != SIM_CAMERA:
                return "the demo has one camera"
            if TOPIC_KEY.search(k) and isinstance(v, str) and v and not _demo_topic(v, devices, own):
                return "a widget is bound to something the demo flat does not have"
    return None


def check(method: str, path: str, params: dict, body: bytes, devices=None, scopes=None) -> "str | None":
    """Why the demo refuses what this request would store, or None. `devices`: id -> device (its controls);
    `scopes`: the tab and room names an order or a tile size may name."""
    if method in ("GET", "HEAD") or path.startswith("/api/demo/") and not path.startswith("/api/demo/sim/"):
        return None
    if not write_allowed():
        return "slower, please: at most two changes a second"
    if path.startswith("/api/demo/"):
        return None
    if path == "/api/panels/{name}/layout":
        return _layout(params, body, devices)
    try:
        b = json.loads(body) if body.strip() else {}
    except ValueError:
        return "the body must be JSON"
    if not isinstance(b, dict):
        return "the body must be a JSON object"
    if not _names_ok(b):
        return "a name may not hold a link, an e-mail address or a phone number"
    if any(not SHORT.match(str(v)) for v in params.values()):
        return "a name in the address is too long or has odd characters"
    dev = params.get("dev_id") or params.get("device") or params.get("src")
    if devices is not None and dev is not None and dev not in devices:
        return "no such device"
    if path == "/api/devices/{dev_id}/control":
        if set(b) - {"code", "value", "source"} or not _scalar(b.get("value")) or not _scalar(b.get("code"), 64) \
                or b.get("source") not in (None, "app"):
            return "a control is {code, value}"
    elif path == "/api/favorites/{device}/{code}":
        if set(b) - {"alias"} or not isinstance(b.get("alias"), str) or not ALIAS.match(b["alias"]):
            return "a favourite's name: up to 24 letters, digits and spaces"
    elif path in ("/api/favorites/reorder", "/api/tab_order/{tab_id}"):
        if set(b) - {"order"} or not _ids_ok(b.get("order")):
            return "an order is at most 100 names"
        if devices is not None and path.startswith("/api/tab_order") and any(x not in devices for x in b["order"]):
            return "an order names devices only"
        if scopes is not None and path.startswith("/api/tab_order") and params.get("tab_id") not in scopes:
            return "no such tab"
    elif path == "/api/tile_sizes/{scope}":
        if set(b) - {"device", "w", "h", "col"} or not re.match(r"^(room:)?[a-z0-9_-]{1,24}$", params.get("scope", "")):
            return "a tile size is {device, w, h, col} of a tab or a room"
        if scopes is not None and params.get("scope") not in scopes:
            return "no such tab or room"
    elif path == "/api/bindings/{src}/{src_code}/{gesture}":
        if set(b) - BINDING_KEYS:
            return "a rule of the demo switches a device: no other fields"
        if b.get("action") not in CORE_ACTIONS:
            return "a rule of the demo switches a device (on, off, toggle, brighter, darker, press)"
        if devices is not None:                 # a rule starts at a sensor or a button: no rule can start another
            src = devices.get(params.get("src")) or {}
            ctl = next((c for c in src.get("controls") or [] if c.get("code") == params.get("src_code")), None)
            if ctl is None or not (ctl.get("ro") or ctl.get("kind") in ("sensor", "sensor_text", "trigger", "trigger_text")):
                return "a rule of the demo starts at a sensor or a button"
            if params.get("gesture") not in SENSOR_GESTURES | set(map(str, ctl.get("values") or [])):
                return "no such event of that sensor or button"
        conds = b.get("conditions") or []
        if not isinstance(conds, list) or len(conds) > 5 or any(
                not isinstance(c, dict) or set(c) - {"device", "code", "op", "value"} or not all(_scalar(v, 64) for v in c.values())
                for c in conds):
            return "at most 5 conditions {device, code, op, value}"
        if not all(_scalar(b.get(k), 64) for k in ("target", "code", "retrigger")):
            return "a name is too long"
    elif path == "/api/automation/{dev_id}/{code}":
        if set(b) - {"inching_sec", "inching_min", "schedule"} or len(b.get("schedule") or []) > 8:
            return "at most 8 times a day"
    elif path in ("/api/rules/run", "/api/rules/enable", "/api/rules/delete"):
        if set(b) - {"id", "enabled"} or not _scalar(b.get("id"), 300):
            return "a rule is named by its id"
    elif len(body) > 2048 and path not in BIG:
        return "too much for this request"
    return None
