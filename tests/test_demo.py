"""The demo plug-in: every route of every shipped plug-in is allowed or refused on purpose (a new one fails
here), each refused one answers 403 in demo mode even to the guest in control, a guest in line only reads, the
lease (a sign-in takes the flat or a place in line), the sign-in and its limits, the reset of the house byte for byte, English only."""
import filecmp
import importlib
import json
import os
import re
import sys
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app as core
import conftest

demo = sys.modules["yashome_plugins.demo"]
routes = sys.modules["yashome_plugins.demo.routes"]
leaselib = sys.modules["yashome_plugins.demo.lease"]
limits = sys.modules["yashome_plugins.demo.limits"]
seed = importlib.import_module("yashome_plugins.demo.seed")

# what must never run in the demo, by name: if one of these moves to ALLOW, this fails before anything ships
DANGEROUS = {
    "POST /api/backups/upload", "POST /api/backups", "GET /api/backups", "GET /api/backups/{name}",
    "PUT /api/map/underlay",
    "POST /api/helper/plugins", "POST /api/helper/env", "POST /api/helper/jobs", "GET /api/helper/state",
    "POST /api/fwgen/builds", "POST /api/panels/{name}/build", "POST /api/build/server/test",
    "POST /api/family/app/build", "GET /plugins/family/yash.apk", "GET /plugins/panels/panel.apk",
    "GET /plugins/build/server.tar.gz", "POST /api/panels/launcher",
    "POST /api/zigbee/pair/start", "POST /api/zigbee/pair/add", "POST /api/pair/start", "POST /api/family/pair",
    "POST /api/webos/{dev_id}/pair", "POST /api/connect/start", "POST /api/panels/pairing",
    "POST /api/esphome/ap/scan", "POST /api/esphome/ap/provision", "GET /api/esphome/discover",
    "POST /api/esphome/add", "POST /api/esphome/remove", "POST /api/signin/start", "POST /api/signin",
    "GET /api/camera/{cid}/stream", "GET /api/camera/{cid}/snapshot", "POST /api/voice/ask", "POST /api/voice/chat",
    "PUT /api/house", "GET /api/health/report",
    "GET /docs", "GET /openapi.json",
}
CYRILLIC = "[" + chr(0x400) + "-" + chr(0x4FF) + "]"      # i18n: the demo shows none of it
CTL, VIEW, OTHER = "control-0123456789abcdef", "viewer-0123456789abcdef", "nobody-0123456789abcdef"


def _shipped(r) -> bool:
    """The core's routes and those of the shipped plug-ins (not one a test adds, such as the example's)."""
    mod = getattr(getattr(r, "endpoint", None), "__module__", "") or ""
    parts = mod.split(".")
    return mod == "app" or mod.startswith(("fastapi.", "starlette.")) or (
        parts[0] == "yashome_plugins" and len(parts) > 1 and parts[1] in conftest.LOADED)


@pytest.fixture(autouse=True)
def _no_write_rate(monkeypatch, request):
    if "write_rate" not in request.node.name:
        monkeypatch.setattr(limits, "write_allowed", lambda now=None: True)


def _app_routes():
    out = set()
    for r in filter(_shipped, core.app.router.routes):
        for m in (getattr(r, "methods", None) or {"WS"}):
            if m != "HEAD":
                out.add(f"{m} {r.path}")
    return out


def _url(path):
    return re.sub(r"\{[^}]+\}", "x", path)


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(core, "RESTRICTED", True)
    roles = {CTL: "control", VIEW: "view"}
    monkeypatch.setattr(core, "RESTRICTED_ROLE", [lambda tok, m, p: roles.get(tok)])
    monkeypatch.setattr(core, "TOKEN_CHECKS", core.TOKEN_CHECKS + [lambda tok, m, p: tok in roles])
    return TestClient(core.app)


def test_every_route_is_allowed_or_refused_on_purpose():
    have, allow = _app_routes(), {f"{m} {p}" for m, p in routes.ALLOW}
    assert not allow & routes.REFUSED, "both allowed and refused"
    assert sorted(have - allow - routes.REFUSED) == [], "new routes: put each in routes.VIEW / CONTROL / REFUSED"
    assert sorted(allow - have) == [], "allowed routes that no longer exist"
    assert sorted(routes.REFUSED - have) == [], "refused routes that no longer exist"


def test_the_dangerous_ones_are_refused():
    own = {f"{m} {p}" for keys in demo.OWN_ROUTES.values() for m, p in keys}       # the demo answers them itself
    assert sorted(DANGEROUS - routes.REFUSED - own) == []
    stack = open(os.path.join(os.path.dirname(demo.__file__), "setup", "compose.demo.yml"), encoding="utf-8").read()
    listed = re.search(r"PLUGINS: *([a-z_,]+)", stack).group(1).split(",")
    assert not set(demo.OWN_ROUTES) & set(listed)                                    # so no real weather or camera there


def test_the_core_gate_takes_the_plugins_list():
    assert {k: v for k, v in core.RESTRICTED_ALLOW.items() if k in routes.ALLOW} == routes.ALLOW


def test_every_refused_route_answers_403_to_the_guest_in_control(demo_on):
    wrong = []
    for k in sorted(routes.REFUSED):
        m, p = k.split(" ", 1)
        if m == "WS":
            try:
                with demo_on.websocket_connect(_url(p) + "?token=" + CTL) as ws:
                    ws.receive_text()
                wrong.append((k, "open"))
            except WebSocketDisconnect as e:
                if e.code != 4403:
                    wrong.append((k, e.code))
            continue
        r = demo_on.request(m, _url(p), headers={"authorization": "Bearer " + CTL})
        if r.status_code != 403 or r.json().get("detail") != core.RESTRICTED_REFUSED:
            wrong.append((k, r.status_code))
    assert wrong == []


def test_a_guest_in_line_cannot_control(demo_on):
    for m, p in sorted(k for k, v in routes.ALLOW.items() if v == "control"):
        r = demo_on.request(m, _url(p), headers={"authorization": "Bearer " + VIEW})
        assert (r.status_code, r.json().get("detail")) == (403, "Not yet: wait for your turn"), (m, p)


def test_a_guest_in_line_reads_the_house_and_its_map(demo_on):
    h = {"authorization": "Bearer " + VIEW}
    for p in ("/api/devices", "/api/rooms", "/api/rules", "/api/map", "/api/demo/state"):
        assert demo_on.get(p, headers=h).status_code == 200, p
    assert demo_on.get("/api/devices").status_code == 401


def test_english_only(demo_on):
    assert core.house_langs() == ["en"]
    js = open(os.path.join(os.path.dirname(core.__file__), "i18n.js"), encoding="utf-8").read()
    assert "if (window.RESTRICTED) { Object.keys(I18N).forEach(k => delete I18N[k]); return 'en'; }" in js


# ---- the lease ----
class Clock:
    def __init__(self):
        self.t = 100000.0

    def __call__(self):
        return self.t


def _lease(tmp_path=None):
    c = Clock()
    return leaselib.Lease(tmp_path and tmp_path / "lease.json", clock=c), c


def _act(lz, tok):
    lz.role(tok, "POST", "/api/devices/x/control")


def _reset(lz):
    """The plug-in's reset: taken, then finished by the restart on the pristine house."""
    why = lz.take_reset()
    if why:
        lz.reset_finished()
    return why


def test_the_first_sign_in_controls_the_next_ones_wait_in_line():
    lz, c = _lease()
    a, b, d = lz.login("198.51.100.1"), lz.login("198.51.100.2"), lz.login("198.51.100.3")
    assert lz.view(a)["role"] == "control" and lz.view(a)["left_s"] == leaselib.LEASE_S       # from the first second
    assert lz.view(b)["position"] == 1 and lz.view(d)["position"] == 2 and lz.view(b)["busy"]
    assert lz.take(b)["position"] == 1                # signed in is in line: a take changes nothing
    assert lz.role(b) == "view" and lz.role(a) == "control"
    assert lz.view(d)["eta_s"] == leaselib.LEASE_S * 2
    for t in (b, d):
        lz.heartbeat(t)
    assert not lz.release(b)                         # only the controller releases
    _act(lz, a)
    assert lz.release(a) and lz.reset_due == "released"
    assert lz.role(b) == "view"                       # the line waits for the reset
    assert _reset(lz) == "released"
    lz.tick()
    assert lz.role(b) == "control" and lz.view(d)["position"] == 1


def test_a_short_turn_without_an_action_needs_no_reset():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    lz.take(a)
    lz.take(b)
    c.t += leaselib.SHORT_S - 1
    lz.heartbeat(b)
    assert lz.release(a) and lz.reset_due == "" and lz.role(b) == "control"


def test_resets_are_two_minutes_apart():
    lz, c = _lease()
    a = lz.login("198.51.100.1")
    lz.take(a)
    _act(lz, a)
    lz.release(a)
    assert _reset(lz) == "released"
    c.t += leaselib.TAKE_GAP_S
    lz.take(a)
    _act(lz, a)
    lz.release(a)
    c.t = lz.last_reset + leaselib.RESET_GAP_S - 1
    assert lz.take_reset() == ""                      # due, but not yet
    c.t += 1
    assert _reset(lz) == "released"


def test_the_guest_resets_once_a_turn_and_not_right_after_another_reset():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    lz.take(a)
    with pytest.raises(leaselib.Refused):
        lz.use_reset(b)
    lz.use_reset(a)
    with pytest.raises(leaselib.Refused):
        lz.use_reset(a)
    assert lz.view(a)["can_reset"] is False


def test_the_first_s_idle_turn_ends_and_the_next_in_line_gets_the_flat():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    c.t += leaselib.IDLE_S
    lz.heartbeat(b)
    assert lz.tick() == "idle" and lz.role(b) == "view"                  # the flat is reset first
    assert _reset(lz) == "idle"
    lz.tick()
    assert lz.role(b) == "control" and lz.view(a)["summary"]["why"] == "idle" and lz.view(a)["position"] == 0


def test_getting_in_line_again_once_in_two_minutes_per_session():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    lz.take(a)
    lz.take(b)
    lz.leave(b)
    with pytest.raises(leaselib.Refused) as e:
        lz.take(b)
    assert e.value.wait_s > 0
    c.t += leaselib.TAKE_GAP_S
    lz.heartbeat(a)
    _act(lz, a)
    assert lz.take(b)["position"] == 1


def test_one_turn_or_place_in_line_per_address():
    lz, _c = _lease()
    lz.login("198.51.100.1")
    n = len(lz.sessions)
    with pytest.raises(leaselib.Refused) as e:
        lz.login("198.51.100.1")                       # a second sign-in of that guest: no session at all
    assert "per guest" in e.value.why and len(lz.sessions) == n
    assert lz.view(lz.login(limits.bucket("2001:db8:1:2::5")))["position"] == 1
    with pytest.raises(leaselib.Refused):
        lz.login(limits.bucket("2001:db8:1:2::99"))    # the same /64


def test_an_address_that_had_a_turn_waits_while_others_are_in_line():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    _act(lz, a)
    c.t += 20
    for t in (a, b):
        lz.heartbeat(t)
    lz.release(a)
    _reset(lz)
    lz.tick()
    assert lz.role(b) == "control"
    c.t += leaselib.TAKE_GAP_S
    lz.heartbeat(b)
    _act(lz, b)
    with pytest.raises(leaselib.Refused):
        lz.take(a)                                     # b plays, a just had a turn
    d = lz.login("198.51.100.3")
    assert lz.view(d)["position"] == 1
    lz.cool["198.51.100.1"] = c.t - 1                  # its waiting time is over
    assert lz.take(a)["position"] == 2


def test_a_turn_ends_idle_capped_or_with_a_closed_tab():
    lz, c = _lease()
    a = lz.login("198.51.100.1")
    lz.take(a)
    c.t += leaselib.IDLE_S - 1
    lz.heartbeat(a)
    assert lz.tick() is None
    _act(lz, a)
    c.t += leaselib.IDLE_S - 1
    lz.heartbeat(a)
    assert lz.tick() is None
    c.t += 2
    assert lz.tick() == "idle" and lz.reset_due == "idle"
    lz.reset_due, lz.last_reset = "", 0
    c.t += leaselib.TAKE_GAP_S
    lz.take(a)
    lz.bye(a)                                          # the page closed
    c.t += leaselib.HEARTBEAT_S
    assert lz.tick() == "tab closed"
    lz.reset_due = ""
    c.t += leaselib.TAKE_GAP_S
    lz.take(a)
    for _ in range(leaselib.LEASE_S // 20):
        c.t += 20
        lz.heartbeat(a)
        _act(lz, a)
    assert lz.role(a) == "view" and lz.reset_due == "time is up"


def test_a_heartbeat_or_a_read_does_not_keep_the_turn():
    lz, c = _lease()
    a = lz.login("198.51.100.1")
    lz.take(a)
    for _ in range(leaselib.IDLE_S // 10):
        c.t += 10
        lz.heartbeat(a)
        lz.role(a, "POST", "/api/demo/heartbeat")
        lz.role(a, "GET", "/api/devices")
    assert lz.role(a) == "view"


def test_a_closed_waiting_tab_loses_its_place():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    lz.take(a)
    lz.take(b)
    lz.bye(b)                                          # b closed its page while in line
    c.t += leaselib.HEARTBEAT_S + 1
    lz.heartbeat(a)
    assert lz.release(a) and _reset(lz) == "released"
    lz.tick()
    assert lz.role(b) == "view" and lz.view(b)["position"] == 0


def test_a_hidden_tab_keeps_control_until_the_idle_limit():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    lz.take(a)
    _act(lz, a)
    lz.take(b)
    c.t += leaselib.IDLE_S - 5                         # a phone in a pocket: no heartbeat, no press
    assert lz.tick() is None and lz.role(a) == "control"
    lz.still(a)                                        # "Still there? Yes"
    c.t += leaselib.IDLE_S - 5
    assert lz.role(a) == "control"
    c.t += 5
    assert lz.tick() == "idle"


def test_a_reload_says_goodbye_and_comes_back():
    lz, c = _lease()
    a = lz.login("198.51.100.1")
    lz.take(a)
    lz.bye(a)
    c.t += 3
    lz.heartbeat(a)                                    # the new page beats
    c.t += leaselib.HEARTBEAT_S + 5
    assert lz.tick() is None and lz.role(a) == "control"


def test_a_waiting_tab_that_is_only_hidden_keeps_its_place():
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    lz.take(a)
    _act(lz, a)
    lz.take(b)
    c.t += 120                                         # b's phone is locked: no heartbeat
    lz.heartbeat(a)
    lz.release(a)
    _reset(lz)
    lz.tick()
    assert lz.role(b) == "control"


def test_a_login_flood_evicts_idle_sessions_out_of_turn_only(monkeypatch):
    monkeypatch.setattr(leaselib, "MAX_SESSIONS", 4)
    lz, c = _lease()
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    for i in range(20):
        c.t += leaselib.HEARTBEAT_S + 1
        for t in (a, b):
            lz.heartbeat(t)
        lz.leave(lz.login(f"203.0.113.{i}"))           # out of the line: evicted once idle
    assert lz.known(a) and lz.known(b) and len(lz.sessions) == 4
    lz.login("203.0.113.99")                            # in line, and the last one out of turn beat just now: full
    with pytest.raises(leaselib.Refused) as e:
        lz.login("203.0.113.100")
    assert e.value.code == 503
    lz2, _c = _lease()
    monkeypatch.setattr(leaselib, "MAX_SESSIONS", 2)
    x, y = lz2.login("198.51.100.1"), lz2.login("198.51.100.2")
    lz2.take(x)
    lz2.take(y)
    with pytest.raises(leaselib.Refused):
        lz2.login("203.0.113.1")


def test_the_lease_survives_a_restart_and_keeps_no_token(tmp_path):
    lz, c = _lease(tmp_path)
    a = lz.login("198.51.100.1")
    lz.take(a)
    assert a not in (tmp_path / "lease.json").read_text()
    again = leaselib.Lease(tmp_path / "lease.json", clock=c)
    assert again.role(a) == "control"


def test_logout_of_the_controller_ends_the_turn():
    lz, _c = _lease()
    a = lz.login("198.51.100.1")
    lz.take(a)
    _act(lz, a)
    lz.logout(a)
    assert lz.reset_due == "signed out" and not lz.known(a)


# ---- the limiter ----
def test_buckets_are_addresses_and_ipv6_64s():
    assert limits.bucket("198.51.100.7") == "198.51.100.7"
    assert limits.bucket("2001:db8:1:2:aaaa::1") == limits.bucket("2001:db8:1:2:ffff::9") == "2001:db8:1:2::/64"
    assert limits.bucket("::ffff:198.51.100.7") == "198.51.100.7"
    assert limits.bucket("") is None and limits.bucket("nope") is None


def test_the_limiter_never_forgets_a_locked_bucket(monkeypatch):
    monkeypatch.setattr(limits, "BUCKETS_MAX", 3)
    lim = limits.Limiter(Clock())
    for _ in range(limits.FAIL_MAX):
        lim.attempt("198.51.100.1")
        lim.failed("198.51.100.1")
    for i in range(50):
        lim.attempt(f"203.0.113.{i}")
    assert lim.attempt("198.51.100.1") is not None


def test_failures_from_many_networks_cut_their_tries_and_lock_nobody_else_out():
    c = Clock()
    lim = limits.Limiter(c)
    for i in range(300):                                   # one /24 tries hard: it is locked, nobody else is
        lim.failed(f"203.0.113.{i % 250}")
    assert lim.attempt("203.0.113.251") is not None and lim.attempt("198.51.100.1") is None
    for i in range(limits.GLOBAL_NETS_MAX * 4):            # a cheap spread attempt: many networks, one failure each
        lim.failed(f"10.{i // 256}.{i % 256}.1")
    assert lim.attempt("198.51.100.2") is None             # a network that did not fail still signs in
    assert lim.attempt("10.0.0.2") is None                 # one failure: one more try in the storm
    lim.failed("10.0.0.2")
    assert lim.attempt("10.0.0.3") is not None             # the storm's cap per network
    c.t += limits.PAUSE_S
    assert lim.attempt("10.0.0.3") is None                 # after the storm: the usual cap per network


def test_networks_are_ipv4_24s_and_ipv6_48s():
    assert limits.net("198.51.100.7") == "198.51.100.0/24"
    assert limits.net(limits.bucket("2001:db8:1:2::5")) == limits.net(limits.bucket("2001:db8:1:ff::5")) == "2001:db8:1::/48"


def test_new_sessions_per_address_are_capped():
    lim = limits.Limiter(Clock())
    for _ in range(limits.NEW_MAX):
        assert lim.attempt("198.51.100.1") is None
        lim.signed_in("198.51.100.1")
    assert lim.attempt("198.51.100.1") is not None


def test_what_a_guest_stores_is_bounded():
    devs = {"lamp": {"controls": [{"code": "state", "kind": "switch"}]},
            "btn": {"controls": [{"code": "action", "kind": "trigger_text", "ro": True, "values": ["single", "double"]}]}}
    ck = limits.check
    assert ck("PUT", "/api/favorites/{device}/{code}", {"device": "lamp", "code": "state"}, b'{"alias": "' + b"x" * 25 + b'"}', devs)
    assert ck("PUT", "/api/favorites/{device}/{code}", {"device": "lamp", "code": "state"}, b'{"alias": "Lamp"}', devs) is None
    rule = {"target": "lamp", "code": "state", "action": "toggle"}
    p, pp = "/api/bindings/{src}/{src_code}/{gesture}", {"src": "btn", "src_code": "action", "gesture": "single"}
    assert ck("PUT", p, pp, json.dumps(rule).encode(), devs) is None
    assert ck("PUT", p, pp, json.dumps({**rule, "action": "say"}).encode(), devs)          # a plug-in's action
    assert ck("PUT", p, pp, json.dumps({**rule, "text": "hello"}).encode(), devs)
    assert ck("PUT", p, pp, json.dumps({**rule, "conditions": [{"device": "lamp", "code": "state", "op": "on"}] * 6}).encode(), devs)
    assert ck("POST", "/api/tab_order/{tab_id}", {"tab_id": "switch"}, b'{"order": ["lamp", "not a device"]}', devs)
    assert ck("POST", "/api/tab_order/{tab_id}", {"tab_id": "x" * 70}, b'{"order": []}', devs)
    assert ck("PUT", "/api/tile_sizes/{scope}", {"scope": "<b>"}, b'{"device": "lamp"}', devs)
    assert ck("POST", "/api/devices/{dev_id}/control", {"dev_id": "lamp"}, b'{"code": "state", "value": true, "source": "voice"}', devs)
    assert ck("POST", "/api/devices/{dev_id}/control", {"dev_id": "lamp"}, b'{"code": "state", "value": "' + b"x" * 40 + b'"}', devs)
    assert ck("POST", "/api/devices/{dev_id}/control", {"dev_id": "lamp"}, b'{"code": "state", "value": true}', devs) is None
    assert ck("POST", "/api/devices/{dev_id}/control", {"dev_id": "ghost"}, b'{"code": "state", "value": true}', devs)
    assert ck("POST", "/api/rules/run", {}, b"not json", devs)
    assert ck("PUT", "/api/favorites/{device}/{code}", {"device": "lamp", "code": "state"}, b'{"alias": "<b>hi</b>"}', devs)
    assert ck("PUT", p, {"src": "lamp", "src_code": "state", "gesture": "true"}, json.dumps({**rule, "target": "btn"}).encode(), devs)  # no rule starts at a switch
    assert ck("PUT", p, {**pp, "gesture": "triple"}, json.dumps(rule).encode(), devs)
    assert ck("POST", "/api/tab_order/{tab_id}", {"tab_id": "switch"}, b'{"order": ["lamp"]}', devs, {"switch"}) is None
    assert ck("POST", "/api/tab_order/{tab_id}", {"tab_id": "made-up"}, b'{"order": ["lamp"]}', devs, {"switch"})
    assert ck("PUT", "/api/tile_sizes/{scope}", {"scope": "room:x9"}, b'{"device": "lamp"}', devs, {"switch", "room:kitchen"})


def test_the_write_rate_of_the_guest_in_control(monkeypatch):
    monkeypatch.setattr(limits, "_bucket", {"tokens": limits.WRITES_BURST, "at": 100.0})
    assert all(limits.write_allowed(100.0) for _ in range(int(limits.WRITES_BURST)))
    assert not limits.write_allowed(100.0)
    assert limits.write_allowed(100.0 + 1 / limits.WRITES_PER_S)


# ---- sign-in ----
@pytest.fixture
def signin(monkeypatch, demo_on):
    monkeypatch.setattr(demo, "PASSWORD", "pw-for-tests")
    monkeypatch.setattr(demo, "EDGE_IP", "testclient")          # the test client plays the demo proxy
    monkeypatch.setattr(demo, "LIMITS", limits.Limiter())
    monkeypatch.setattr(demo, "LEASE", leaselib.Lease())
    monkeypatch.setattr(core, "RESTRICTED_ROLE", [lambda tok, m, p: demo.LEASE.role(tok, m, p)])
    return demo_on


def _login(c, pw="pw-for-tests", ip="198.51.100.20"):
    return c.post("/api/demo/login", json={"password": pw}, headers={"x-forwarded-for": ip})


def test_the_first_sign_in_gets_control_the_next_waits_and_gets_it_when_the_first_leaves(signin):
    a = {"authorization": "Bearer " + _login(signin).json()["token"]}
    st = signin.get("/api/demo/state", headers=a).json()
    assert st["signed_in"] and st["role"] == "control"
    b = {"authorization": "Bearer " + _login(signin, ip="203.0.113.5").json()["token"]}
    st = signin.get("/api/demo/state", headers=b).json()
    assert (st["role"], st["position"], st["busy"]) == ("view", 1, True) and st["eta_s"] > 0
    assert signin.post("/api/demo/release", headers=a).json()["role"] == "view"   # a short turn, no action: no reset
    assert signin.post("/api/demo/heartbeat", headers=b).json()["role"] == "control"
    assert _login(signin, "nope").status_code == 401


def test_five_failures_from_one_address_block_it(signin):
    for _ in range(limits.FAIL_MAX):
        assert _login(signin, "nope").status_code == 401
    assert _login(signin).status_code == 429
    assert _login(signin, ip="198.51.100.21").status_code == 200


def test_sign_in_fails_closed_without_the_demo_proxy(signin, monkeypatch):
    assert signin.post("/api/demo/login", json={"password": "pw-for-tests"}).status_code == 503
    assert _login(signin, ip="not an address").status_code == 503
    monkeypatch.setattr(demo, "EDGE_IP", "192.0.2.1")
    assert _login(signin).status_code == 503                      # the test client is not the proxy now


def test_no_sign_in_outside_demo_mode(signin, monkeypatch):
    monkeypatch.setattr(core, "RESTRICTED", False)
    assert _login(signin).status_code == 403


def test_sign_in_and_its_refusals_over_http(signin):
    a = {"authorization": "Bearer " + _login(signin).json()["token"]}
    assert signin.post("/api/demo/take", headers=a).json()["role"] == "control"
    r = _login(signin)                                                      # the same address
    assert r.status_code == 409 and "per guest" in r.json()["detail"]
    b = {"authorization": "Bearer " + _login(signin, ip="203.0.113.5").json()["token"]}
    assert signin.post("/api/demo/reset", headers=b).status_code == 403    # the gate: b waits in line


def test_the_sign_in_page_is_open_and_english(signin):
    r = signin.get("/try")
    assert r.status_code == 200 and "Enter the demo" in r.text and not re.search(CYRILLIC, r.text)


# ---- the reset ----
def _tree_equal(a, b):
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    if filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)[1:] != ([], []):
        return False
    return all(_tree_equal(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)


def test_the_reset_puts_back_the_seed_byte_for_byte(tmp_path):
    house = tmp_path / "house"
    house.mkdir()
    seed.reset_house(house)
    assert _tree_equal(seed.SEED, house)
    (house / "settings.json").write_text('{"room_sensors": {"living": {"temperature": "living_ac/room_temp"}}}')   # a guest's pick of a thermometer
    (house / "plugin-state" / "history").mkdir(parents=True, exist_ok=True)
    (house / "plugin-state" / "history" / "history.db").write_bytes(b"guest data")
    (house / "status_cache.json").write_text("{}")
    seed.reset_house(house)
    assert _tree_equal(seed.SEED, house)


def test_the_reset_never_takes_the_seed_for_the_house():
    with pytest.raises(ValueError):
        seed.reset_house(seed.SEED)


def test_a_reset_asks_the_simulator_to_clean_the_broker_then_restarts(monkeypatch):
    sent, exited = [], []

    class Cli:
        def publish(self, topic, payload, qos=0):
            sent.append(topic)
            demo._reset_done.set()

    monkeypatch.setattr(core, "_mqtt_client", Cli())
    monkeypatch.setattr(demo, "_exit", lambda: exited.append(1))
    demo._schedule_reset("test")
    for _ in range(50):
        if exited:
            break
        time.sleep(0.05)
    assert sent == ["demo/reset"] and exited == [1]
    demo._resetting.release()


def test_a_closing_page_says_goodbye_without_a_header(signin):
    tok = _login(signin).json()["token"]
    assert signin.post("/api/demo/bye", json={"token": tok}).status_code == 200      # a beacon: no Authorization
    assert demo.LEASE.sessions[leaselib._h(tok)]["bye"] > 0
    assert signin.post("/api/demo/bye", json={"token": "x" * 300}).status_code == 422


def test_no_address_reaches_the_log(signin, caplog):
    with caplog.at_level("DEBUG"):
        _login(signin, "nope", ip="198.51.100.66")
        signin.post("/api/demo/login", json={"password": "x"}, headers={"x-forwarded-for": "198.51.100.67"})
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "refused" in text and "198.51.100" not in text and "testclient" not in text


def test_a_guest_in_line_is_not_the_owner(signin):
    _login(signin)                                                                # the first one has the flat
    w = {"authorization": "Bearer " + _login(signin, ip="203.0.113.5").json()["token"]}
    assert signin.get("/api/map", headers=w).status_code == 200                   # listed for everyone signed in
    for path in ("/api/history", "/api/history/info", "/api/watchdog"):          # the owner's own: control only
        assert signin.get(path, headers=w).status_code == 403, path


def test_repeats_of_a_rule_are_one_feed_line():
    n = demo._feed_seq[0]
    for _ in range(5):
        demo._on_event({"kind": "rule", "device": "Sofa button", "gesture": "single", "target": "Floor lamp", "value": "toggle"})
    items = demo.demo_feed(n)["items"]
    assert len(items) == 1 and items[0]["n"] == 5


def test_no_guest_address_is_kept(signin, monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "LEASE", leaselib.Lease(tmp_path / "lease.json"))
    _login(signin, ip="198.51.100.77")
    assert "198.51.100.77" not in (tmp_path / "lease.json").read_text()
    assert demo._anon("198.51.100.77") == demo._anon("198.51.100.77") != "198.51.100.77"


# ---- the page's side ----
def test_every_greyed_control_maps_to_a_refused_route():
    d = json.loads((demo.HERE / "static" / "greyed.json").read_text())
    assert d["controls"]
    for c in d["controls"]:
        assert c["route"] in routes.REFUSED, c
        assert c["do"] in ("grey", "hide") and c["sel"], c


def test_a_turn_leaves_a_summary_for_its_guest():
    lz, c = _lease()
    a = lz.login("198.51.100.1")
    lz.take(a)
    _act(lz, a)
    lz.note_rule()
    c.t += 90
    lz.heartbeat(a)
    lz.release(a)
    s = lz.view(a)["summary"]
    assert (s["why"], s["actions"], s["rules"], s["minutes"]) == ("released", 1, 1, 1.5)
    lz.dismiss(a)
    assert lz.view(a)["summary"] is None


def test_steering_the_simulator_counts_as_an_action():
    lz, c = _lease()
    a = lz.login("198.51.100.1")
    lz.take(a)
    lz.role(a, "POST", "/api/demo/sim/weather")
    assert lz.acted and lz.turn["actions"] == 1
    lz.role(a, "POST", "/api/demo/heartbeat")
    assert lz.turn["actions"] == 1


def test_rules_reach_the_feed():
    n = demo._feed_seq[0]
    demo._on_event({"kind": "rule", "device": "Doorbell", "gesture": "single", "target": "Hallway light", "value": "on"})
    demo._on_event({"kind": "state", "device": "Doorbell"})
    items = demo.demo_feed(n)["items"]
    assert [i["who"] for i in items] == ["rule"] and items[0]["src"] == "Doorbell" and items[0]["device"] == "Hallway light"
    assert items[0]["text"].endswith("pressed -> Hallway light on")
    assert demo._value({"state": "ON"}) == "on" and demo._value({"brightness": 120}) == "brightness 120"


def test_the_simulator_takes_only_known_values(signin):
    a = {"authorization": "Bearer " + _login(signin).json()["token"]}
    signin.post("/api/demo/take", headers=a)
    sent = []

    class Cli:
        def publish(self, topic, payload=None, retain=False, qos=0):
            sent.append((topic, payload))
            return type("I", (), {"rc": 0})()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(core, "_mqtt_client", Cli())
        assert signin.post("/api/demo/sim/speed", headers=a, json={"x": 60}).status_code == 200
        assert signin.post("/api/demo/sim/speed", headers=a, json={"x": 7}).status_code == 422
        assert signin.post("/api/demo/sim/move", headers=a, json={"who": "Alex", "room": "bath"}).status_code == 200
        assert signin.post("/api/demo/sim/move", headers=a, json={"who": "Eve", "room": "bath"}).status_code == 422
        assert signin.post("/api/demo/sim/event", headers=a, json={"name": "fire"}).status_code == 422
    assert sent == [("demo/sim/speed", "60"), ("demo/sim/move", "Alex=bath")]


def test_the_showcase_is_open_without_sign_in(demo_on):
    page = demo_on.get("/showcase")
    assert page.status_code == 200 and '<base href="/showcase/">' in page.text and 'href="/try"' in page.text
    for name in re.findall(r'(?:src|href)="img/([^"]+)"', page.text) + ["en/map.png", "ru/mobile.png"]:
        r = demo_on.get("/showcase/img/" + name)
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/"), name
    for bad in ("../__init__.py", "..%2F__init__.py", "en/../../index.html", "nope.png"):
        assert demo_on.get("/showcase/img/" + bad).status_code in (401, 403, 404), bad


def test_the_simulation_panel_presses_only_what_the_demo_allows():
    """Things to try are live controls: each change is a control of a demo device or a sim call the demo accepts."""
    catalog = importlib.import_module("yashome_plugins.demo.sim.catalog")
    js = open(os.path.join(os.path.dirname(routes.__file__), "ui.js"), encoding="utf-8").read()
    tasks = js[js.index("const TASKS = ["):js.index("function drawTasks()")]
    sends = re.findall(r"send\(('[^']+'|AC), '([^']+)'", tasks)
    sims = re.findall(r"simPost\('(\w+)', \{([^}]*)\}", tasks)
    assert len(sends) == 5 and len(sims) == 3, (sends, sims)
    assert ("POST", "/api/devices/{dev_id}/control") in routes.ALLOW
    ids = {d["id"] for d in catalog.DEVICES}
    assert {d.strip("'") if d != "AC" else "bedroom_ac" for d, _ in sends} <= ids and "const AC = 'bedroom_ac'" in tasks
    for a, body in sims:
        assert ("POST", f"/api/demo/sim/{a}") in routes.ALLOW
        words = re.findall(r"'([^']+)'", body)
        if a == "event":
            assert words and set(words) <= set(demo.SIM_EVENTS), body
        else:
            assert words[0] in catalog.RESIDENTS and set(words[1:]) <= set(catalog.ROOMS), body
    assert "demo-sim" not in js                       # the simulation lives beside the map, not in a tab


def test_the_intro_only_reads_and_speaks_english():
    """The intro draws a copy of the map (MapScene): eight steps in plain English, a Skip, and no call that writes."""
    js = open(os.path.join(os.path.dirname(routes.__file__), "ui.js"), encoding="utf-8").read()
    block = js[js.index("const INTRO_SEEN"):js.index("window.__demoIntro = intro;")]
    steps = re.findall(r"^    \['([^']+)', '((?:[^'\\]|\\.)*)', ", block, re.M)
    assert len(steps) == 8 and all(t.isascii() and c.isascii() for t, c in steps), steps
    assert "method:" not in block and "MapScene.render(" in block and 'data-i="skip"' in block
    assert {u for u in re.findall(r"Home\.api\('([^']+)'", block)} <= {p for m, p in routes.ALLOW if m == "GET"}


def test_the_demo_s_ask_never_reaches_a_model():
    """Ask the house in the demo: example questions answered from the flat; nothing goes to a language model."""
    js = open(os.path.join(os.path.dirname(routes.__file__), "ui.js"), encoding="utf-8").read()
    block = js[js.index("const ASK = ["):js.index("window.__demoAsk")]
    assert len(re.findall(r"^    \['([^']+)', async", block, re.M)) >= 6
    assert "/api/voice" not in block and "fetch(" not in block and "demo-ask" not in js
    assert not [k for k in routes.ALLOW if k[1].startswith("/api/voice")]


def test_no_two_functions_of_one_name_in_the_page():
    """A second function of the same name in ui.js replaces the first one silently (27.10: the live controls' act took the
    header's Take control); every name is declared once."""
    js = open(os.path.join(os.path.dirname(routes.__file__), "ui.js"), encoding="utf-8").read()
    names = re.findall(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(", js, re.M)
    assert not sorted({n for n in names if names.count(n) > 1}), names



def test_the_forecast_s_first_hour_is_now_and_rain_shows_on_the_balcony(monkeypatch):
    import time as _t
    t0 = _t.mktime((2026, 10, 27, 14, 20, 0, 0, 0, -1))
    monkeypatch.setattr(demo, "_sim_state", {"t": int(t0), "time": "14:20", "weather": "rain", "outdoor": 13.5, "held_until": "14:40"})
    f = demo._forecast()
    h = f["hourly"]
    assert (h["weather_code"][0], h["temperature_2m"][0], f["current"]["weather_code"]) == (63, 13.5, 63)
    assert h["weather_code"][1] in (63, 1, 3, 0) and len(h["time"]) == 24 and len(f["daily"]["time"]) == 4
    assert "#d6e6ff" in demo._still().decode()                         # the balcony's rain
    monkeypatch.setattr(demo, "_sim_state", {"t": int(t0), "time": "14:20", "weather": "clear", "outdoor": 22.0, "held_until": None})
    assert demo._forecast()["current"]["weather_code"] == 1 and "#d6e6ff" not in demo._still().decode()



def test_the_sign_in_is_the_password_alone_and_an_old_page_s_name_is_ignored(monkeypatch):
    import pathlib
    page = (pathlib.Path(demo.__file__).parent / "static" / "try.html").read_text(encoding="utf-8")
    assert page.count("<input") == 1 and 'type="password"' in page and "username" not in page
    assert '"wrong password"' in pathlib.Path(demo.__file__).read_text(encoding="utf-8")


def test_every_plug_in_the_compose_file_runs_is_one_the_export_keeps():
    import pathlib
    import re
    setup = pathlib.Path(demo.__file__).parent / "setup"
    runs = re.search(r"PLUGINS: ([\w,]+)", (setup / "compose.demo.yml").read_text(encoding="utf-8")).group(1).split(",")
    keep = re.search(r"^keep=\"([^\"]+)\"", (setup / "export.sh").read_text(encoding="utf-8"), re.M).group(1).split()
    assert sorted(runs) == sorted([k.split("/")[1] for k in keep] + ["demo"])          # the demo itself comes as plugins-extra/demo



def test_the_watchdog_keeps_off_while_an_export_holds_the_deploy_lock(tmp_path):
    import fcntl
    import pathlib
    import subprocess
    setup = pathlib.Path(demo.__file__).parent / "setup"
    (tmp_path / ".deploy.lock").write_text("")
    with open(tmp_path / ".deploy.lock") as held:
        fcntl.flock(held, fcntl.LOCK_EX)                      # an export runs
        r = subprocess.run(["sh", str(setup / "watchdog.sh"), str(tmp_path)], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0 and r.stdout.strip() == "watchdog: an export runs: skipped"
        r = subprocess.run(["sh", str(setup / "export.sh"), "/nonexistent", "/nonexistent", str(tmp_path)], capture_output=True, text=True, timeout=20,
                           env={**os.environ, "DEMO_LOCK_WAIT": "1"})
        assert r.returncode == 4 and "holds" in r.stdout                  # a second deploy waits, then gives up


def test_a_reset_the_gap_holds_back_is_delayed_never_dropped_and_nobody_gets_the_flat_before_it():
    lz, c = _lease()
    a = lz.login("198.51.100.1")
    _act(lz, a)
    lz.release(a)
    assert _reset(lz) == "released"
    c.t += leaselib.TAKE_GAP_S
    lz.take(a)
    _act(lz, a)
    lz.release(a)
    c.t = lz.last_reset + leaselib.RESET_GAP_S - 30        # inside the gap: this reset must wait
    assert lz.take_reset() == "" and lz.reset_wait() > 0
    b = lz.login("198.51.100.2")
    lz.tick()
    assert lz.view(b)["role"] != "control" and lz.view(b)["resetting"]          # b waits for a clean flat
    c.t = lz.last_reset + leaselib.RESET_GAP_S
    assert lz.take_reset() == "released"                  # the reset runs, late, not lost
    lz.tick()
    assert lz.view(b)["role"] != "control" and lz.view(b)["resetting"]          # not before the restart
    assert lz.reset_finished()
    assert lz.view(b)["role"] == "control"


def test_the_turn_is_handed_over_only_by_the_restart_after_the_reset(tmp_path):
    lz, c = _lease(tmp_path)
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    _act(lz, a)
    lz.heartbeat(b)
    lz.release(a)
    assert lz.take_reset() == "released" and lz.take_reset() == ""      # one reset, asked once
    for _ in range(5):                                    # the old flat lives on until the backend exits
        c.t += 1
        lz.heartbeat(b)
        lz.tick()
        assert lz.role(b) == "view" and lz.view(b)["resetting"] and lz.view(b)["eta_s"] < leaselib.LEASE_S + 60
    lz2 = leaselib.Lease(tmp_path / "lease.json", clock=c)           # the restart
    assert lz2.resetting == "asked" and lz2.role(b) == "view"
    assert lz2.reset_finished() and lz2.role(b) == "control" and not lz2.reset_finished()


def test_the_line_is_full_of_tabs_that_beat_only():
    lz, c = _lease()
    lz.login("net-ctl")
    line = [lz.login(f"net-{i}") for i in range(leaselib.MAX_LINE)]
    with pytest.raises(leaselib.Refused):
        lz.login("net-late")                              # 20 live places: full
    c.t += leaselib.LIVE_S + 1                            # they went silent (closed without a goodbye)
    for t in line[:5]:
        lz.heartbeat(t)
    late = lz.login("net-late")
    assert lz.view(late)["position"] == leaselib.MAX_LINE + 1 and lz.view(line[-1])["position"] == leaselib.MAX_LINE


def test_the_restart_asks_the_simulator_again_when_it_did_not_answer(monkeypatch, tmp_path):
    import asyncio
    lz, c = _lease(tmp_path)
    a, b = lz.login("198.51.100.1"), lz.login("198.51.100.2")
    _act(lz, a)
    lz.heartbeat(b)
    lz.release(a)
    lz.take_reset()
    asks = []

    def ask(why):
        asks.append(why)
        return len(asks) == 2                              # the first try is lost, the second answered
    monkeypatch.setattr(demo, "LEASE", lz)
    monkeypatch.setattr(demo, "_ask_sim", ask)
    monkeypatch.setattr(core, "RESTRICTED", True)
    asyncio.run(demo._finish_reset())
    assert len(asks) == 2 and lz.role(b) == "control" and lz.resetting == ""
    lz.sim_clean()                                         # no reset runs: nothing to mark
    assert lz.resetting == ""


import pathlib  # noqa: E402
import shutil  # noqa: E402

seedmod = importlib.import_module("yashome_plugins.demo.seed")


def _snap(root):
    return {str(p): p.stat().st_mtime_ns for p in pathlib.Path(root).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}


def test_what_a_guest_does_as_an_owner_is_written_into_the_house_only_and_the_reset_takes_it_back(demo_on, tmp_path):
    """Every new owner route a guest in control may use writes under the house directory (the reset empties it and copies the
    seed back); nothing of the checkout changes."""
    h = {"authorization": "Bearer " + CTL}
    house, code = pathlib.Path(core.HOUSE).resolve(), pathlib.Path(demo.__file__).resolve().parents[3]
    before_code = _snap(code)
    dev = next(d for d, v in core.DEVICES.items() if v.get("transport") not in ("ir",) and not d.startswith(("blaster:", "panel:")))
    m = demo_on.get("/api/map", headers=h).json()                 # sent as the map's own save sends it
    calls = [("PUT", "/api/map", {k: m[k] for k in ("rev", "rooms", "items", "links", "walls", "openings") if k in m}),
             ("POST", f"/api/devices/{dev}/rename", {"name": "Reading lamp"}),
             ("POST", "/api/rooms", {"name": "Study"}),
             ("PUT", "/api/wiring", demo_on.get("/api/wiring", headers=h).json()),
             ("DELETE", "/api/history?all=1", None)]
    codes = [demo_on.request(m, p, headers=h, json=b).status_code for m, p, b in calls]
    assert all(c < 400 for c in codes), list(zip([p for _m, p, _b in calls], codes))
    assert _snap(code) == before_code                       # the checkout is untouched: every write went to the house
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "settings.json").write_text("{}")
    target = tmp_path / "house"
    shutil.copytree(house, target)
    seedmod.reset_house(target, seed)                        # what the reset does to that house
    assert seedmod.digest(target) == seedmod.digest(seed)


def test_a_name_with_a_link_an_e_mail_or_a_phone_number_is_refused(demo_on):
    h = {"authorization": "Bearer " + CTL}
    dev = next(iter(core.DEVICES))
    for bad in ("visit https://example.com", "www.example.org", "mail me at a@b.co", "call +972 50 123 4567", "shop.example.com"):
        r = demo_on.post(f"/api/devices/{dev}/rename", headers=h, json={"name": bad})
        assert r.status_code == 400 and "link" in r.json()["detail"], bad
    assert limits.check("POST", "/api/rooms", {}, json.dumps({"name": "Kids room 2"}).encode()) is None


def test_settings_show_pages_only_for_plug_ins_the_demo_keeps_off():
    """ui.js gives a page of items to every plug-in in SHOW: none of them may run here (two pages of one subject)."""
    import pathlib
    import re
    here = pathlib.Path(demo.__file__).parent
    runs = re.search(r"PLUGINS: ([\w,]+)", (here / "setup" / "compose.demo.yml").read_text(encoding="utf-8")).group(1).split(",")
    ui = (here / "ui.js").read_text(encoding="utf-8")
    block = ui[ui.index("const SHOW = {"):ui.index("function showcase(")]
    shown = re.findall(r"^    ([a-z]+): \[\[", block, re.M)
    assert shown and not set(shown) & set(runs)
    every = re.search(r"const SHOW_AT = \{([^}]+)\}", ui).group(1)
    assert set(shown) == set(re.findall(r"([a-z]+):", every))
