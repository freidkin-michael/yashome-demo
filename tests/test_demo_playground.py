"""The demo's panel playground: only that panel takes a layout, small (32 KB, 40 widgets), bound only to the demo flat's
devices; an unknown widget type is the core's 400; the designed starter passes; the builder and the tablet view are open
to the guest, the panels routes that leave the flat are not."""
import json
import os
import sys

import pytest

import app as core

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "tools", "demo", "sim"))
import catalog  # noqa: E402

from test_demo import CTL, VIEW, demo_on  # noqa: E402,F401

demo = sys.modules["yashome_plugins.demo"]
limits = demo.limits
panels = sys.modules["yashome_plugins.panels"]
FLAT = {d["id"]: {"id": d["id"], "controls": []} for d in catalog.DEVICES}
SEED = os.path.join(os.path.dirname(demo.__file__), "house", "plugin-data", "panels", "layouts.json")


def lay(widgets, name="playground"):
    return limits._layout({"name": name}, json.dumps({"widgets": widgets}).encode(), FLAT)


def toggle(topic):
    return {"id": "t", "type": "toggle", "x": 0, "y": 0, "w": 100, "h": 60, "state_topic": topic, "cmd_topic": topic}


def test_the_starter_is_designed_and_passes():
    seed = json.load(open(SEED, encoding="utf-8"))["playground"]
    assert (seed["hw"], seed["w"], seed["h"]) == ("android", 1024, 600) and 6 <= len(seed["widgets"]) <= 8
    assert {w["type"] for w in seed["widgets"]} <= panels._WIDGET_TYPES
    assert lay(seed["widgets"]) is None


def test_only_the_playground_small_and_bound_to_the_flat():
    assert lay([], "kitchen") == "only the playground panel can be changed in the demo"
    assert lay([toggle("home/state/Kitchen light/state")] * 41).startswith("a layout has at most 40")
    assert lay([toggle("home/state/Somebody's lamp/state")]) == "a widget is bound to something the demo flat does not have"
    assert lay([{"id": "a", "type": "ac", "x": 0, "y": 0, "w": 9, "h": 9, "device": "real_ac"}]).startswith("a widget names a device")
    assert lay([{"id": "c", "type": "camera", "x": 0, "y": 0, "w": 9, "h": 9, "cam_id": "front-door"}]) == "the demo has one camera"
    assert lay([toggle("home/state/Kitchen light/state")]) is None


def test_the_playground_s_words_hold_no_link_e_mail_or_phone():
    bad = "a name may not hold a link, an e-mail address or a phone number"
    assert lay([{"id": "l", "type": "label", "x": 0, "y": 0, "w": 9, "h": 9, "text": "visit www.example.com"}]) == bad
    assert lay([{**toggle("home/state/Kitchen light/state"), "label": "call +1 555 123 4567"}]) == bad
    body = json.dumps({"title": "mail me@example.org", "widgets": []}).encode()
    assert limits._layout({"name": "playground"}, body, FLAT) == bad
    assert lay([{**toggle("home/state/Kitchen light/state"), "label": "Kitchen"}]) is None


def test_the_gate_answers_400(demo_on, monkeypatch):
    monkeypatch.setattr(core, "DEVICES", {**core.DEVICES, **FLAT})
    monkeypatch.setitem(panels._layouts, "playground", {"hw": "android", "w": 1024, "h": 600, "widgets": []})
    monkeypatch.setattr(panels, "_save_layouts", lambda: None)
    monkeypatch.setattr(panels, "_publish", lambda name: None)
    h = {"Authorization": "Bearer " + CTL, "Content-Type": "application/json"}
    put = lambda name, body: demo_on.put(f"/api/panels/{name}/layout", headers=h, content=json.dumps(body))    # noqa: E731
    assert put("kitchen", {"widgets": []}).status_code == 400
    big = {"widgets": [{**toggle("home/state/Kitchen light/state"), "text": "x" * 1000, "id": f"t{i}"} for i in range(36)]}
    assert 32 * 1024 < len(json.dumps(big)) < 64 * 1024 and put("playground", big).status_code == 400
    assert put("playground", {"widgets": [toggle("home/state/nobody/state")]}).status_code == 400
    assert put("playground", {"widgets": [{"id": "z", "type": "nope", "x": 0, "y": 0, "w": 9, "h": 9}]}).status_code == 400
    assert put("playground", {"widgets": []}).status_code == 200
    v = {"Authorization": "Bearer " + VIEW}
    assert demo_on.put("/api/panels/playground/layout", headers={**v, "Content-Type": "application/json"}, content="{}").status_code == 403
    for path in ("/panel-builder", "/panel-view.html", "/api/panels/limits", "/api/panels/playground/layout"):
        assert demo_on.get(path, headers=v).status_code == 200, path
    for m, path in (("POST", "/api/panels/playground/rename"), ("DELETE", "/api/panels/playground"), ("POST", "/api/panels/pairing")):
        assert demo_on.request(m, path, headers=h, content="{}").status_code == 403, path
