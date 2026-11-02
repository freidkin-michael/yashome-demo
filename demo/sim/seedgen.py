"""Writes the demo house (../house/) from the catalog: `python -m sim.seedgen <dir>` from plugins-extra/demo.
The seed is checked in; tests/plugins/test_demo_sim.py fails when it differs from what this writes, so the
catalog stays the one source of the flat (devices, rooms, the map and its drawing, rules)."""
import json
import sys
from pathlib import Path

from . import catalog, devices

W, H, PX = 12.0, 8.0, 100          # the plan in metres, drawn at 100 units a metre
OX, OY = 14, 46                    # where the plan starts in the drawing (room for the balcony)
WT = 0.12                          # half a wall's thickness, metres
OPENINGS = [   # kind, (x1, y1), (x2, y2) on a wall, how a door opens
    ("door", (4.8, 4.6), (5.6, 4.6), "left"), ("door", (7.0, 4.6), (7.8, 4.6), "right"),
    ("door", (10.0, 4.6), (10.8, 4.6), "left"), ("door", (10.2, 6.0), (11.0, 6.0), "slide"),
    ("door", (4.0, 6.2), (4.0, 7.0), "left"), ("door", (6.9, 8.0), (7.9, 8.0), "right"),
    ("window", (1.0, 0.0), (3.4, 0.0), ""), ("window", (7.0, 0.0), (8.4, 0.0), ""),
    ("window", (9.8, 0.0), (11.4, 0.0), ""), ("window", (0.0, 5.4), (0.0, 7.2), ""),
    ("window", (0.0, 1.2), (0.0, 3.4), ""),
]
IR_NODE = "living-ir"
IR_FAN = {"id": "ceiling_fan_ir", "name": "Ceiling fan", "remote": "fan_remote", "blaster": IR_NODE}
FAN_REMOTE = {"id": "fan_remote", "name": "Ceiling fan remote", "learned_on": IR_NODE, "groups": [
    {"name": "Power", "buttons": [{"id": "power", "name": "Power", "proto": "ir", "code": "9000,-4500,560,-560,560,-1690", "n": 6}]},
    {"name": "Speed", "buttons": [{"id": "speed", "name": "Speed", "proto": "ir", "code": "9000,-4500,560,-1690,560,-560", "n": 6}]}]}


def _f(x, y):
    return {"x": round(x / W, 4), "y": round(y / H, 4)}


def wall_rects() -> list:
    """The walls as rectangles (x, y, w, h in metres): every room edge, a wall's thickness wide, doors and windows cut
    out. The map reads rectangles in <g data-walls>: names and dropped things keep off them."""
    out, seen = [], set()
    for _n, poly in catalog.ROOMS.values():
        pts = poly + poly[:1]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            key = tuple(sorted([(x1, y1), (x2, y2)]))
            if key in seen:
                continue
            seen.add(key)
            horiz = y1 == y2
            lo, hi = sorted((x1, x2) if horiz else (y1, y2))
            fixed = y1 if horiz else x1
            cuts = sorted((min(a[0], b[0]), max(a[0], b[0])) if horiz else (min(a[1], b[1]), max(a[1], b[1]))
                          for _k, a, b, _o in OPENINGS if (a[1] == b[1] == fixed if horiz else a[0] == b[0] == fixed))
            cuts = [c for c in cuts if c[1] > lo and c[0] < hi]          # only the openings on this stretch
            start = lo - WT
            for c0, c1 in cuts + [(hi + WT, hi + WT)]:
                if c0 > start:
                    out.append((start, fixed - WT, c0 - start, 2 * WT) if horiz else (fixed - WT, start, 2 * WT, c0 - start))
                start = max(start, c1)
    return out


def scheme_svg() -> str:
    """The drawing under the map, in the dashboard's colours: floors, walls (data-walls rectangles), the balcony."""
    w, h = int(W * PX), int(H * PX)
    floors = "".join(f'<polygon points="{" ".join(f"{x * PX + OX:.0f},{y * PX + OY:.0f}" for x, y in poly)}"/>'
                     for _n, poly in catalog.ROOMS.values())
    walls = "".join(f'<rect x="{x * PX + OX:.0f}" y="{y * PX + OY:.0f}" width="{ww * PX:.0f}" height="{hh * PX:.0f}"/>'
                    for x, y, ww, hh in wall_rects())
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w + 2 * OX} {h + OY + OX}" width="{(w + 2 * OX) * 2}" '
            f'height="{(h + OY + OX) * 2}">\n'
            '<defs><linearGradient id="fl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d2533"/>'
            '<stop offset="1" stop-color="#171d28"/></linearGradient></defs>\n'
            f'<rect width="{w + 2 * OX}" height="{h + OY + OX}" fill="#0b0e13"/>\n'
            '<g fill="#173022" fill-opacity="0.6" stroke="#2f5e45" stroke-width="1.2" stroke-dasharray="5 4">'
            f'<rect data-snap="1" x="{OX + 20}" y="{OY - 40}" width="{int(5.6 * PX)}" height="34" rx="6"/></g>\n'
            f'<g fill="url(#fl)" stroke="#1c2431" stroke-width="2" stroke-linejoin="round">{floors}</g>\n'
            f'<g data-walls="1" fill="#7f8ea6">{walls}</g>\n'
            '</svg>\n')


def map_json() -> dict:
    """map.json as the map plug-in keeps it after its start-up steps (canvas, the drawing shown, geometry 4)."""
    cw, ch = W * PX + 2 * OX, H * PX + OY + OX
    ox, oy = OX / cw, OY / ch                       # the plan's corner inside the drawing's frame
    sx, sy = W * PX / cw, H * PX / ch

    def fr(x, y):
        return {"x": round(ox + x / W * sx, 4), "y": round(oy + y / H * sy, 4)}
    rooms = [{"id": rid, "name": name, "house_room": rid, "poly": [fr(x, y) for x, y in poly],
              "walls": [True] * len(poly)} for rid, (name, poly) in catalog.ROOMS.items()]
    items, links, n = [], [], 0
    for d in catalog.DEVICES:
        n += 1
        dev = f"blaster:{IR_NODE}" if d["type"] == "blaster" else d["id"]
        items.append({"id": f"d{n}", "kind": "device", "dev": dev, "name": "", "type": "", **fr(*d["at"]), "room": "" if d.get("outdoor") else d["room"],
                      "smooth": False})
        for code, (name, typ, _w, at) in (d.get("loads") or {}).items():
            n += 1
            item = {"id": f"l{n}", "kind": "load", "dev": "", "name": name, "type": typ, **fr(*at), "room": d["room"],
                    "smooth": False}
            if typ == "led":
                item["path"] = [fr(at[0], at[1]), fr(at[0] + 1.6, at[1])]
                item["x"], item["y"] = item["path"][1]["x"], item["path"][1]["y"]
            items.append(item)
            links.append({"load": item["id"], "dev": d["id"], "code": code, "note": "", "seg": []})
    n += 1
    items.append({"id": f"l{n}", "kind": "load", "dev": IR_FAN["id"], "name": "Ceiling fan", "type": "fan", **fr(3.7, 1.3),     # the IR fan: the blaster's dashed line
                  "room": "living", "smooth": False})
    n += 1
    items.append({"id": f"l{n}", "kind": "load", "dev": "living_tv", "name": "Television", "type": "tv", **fr(2.7, 4.2),       # the TV itself: one icon
                  "room": "living", "smooth": False})
    links.append({"load": f"l{n}", "dev": "tv_socket", "code": "state", "note": "", "seg": []})
    openings = []
    for i, (kind, a, b, how) in enumerate(OPENINGS):
        fa, fb = fr(*a), fr(*b)
        openings.append({"id": f"o{i + 1}", "a": [fa["x"], fa["y"]], "b": [fb["x"], fb["y"]], "kind": kind,
                         "open": how or "left", "side": False})
    return {"v": 1, "rev": 1, "rooms": rooms, "items": items, "links": links, "walls": [], "openings": openings,
            "canvas": {"x": 0, "y": 0, "w": cw, "h": ch}, "geo": 4,
            "underlay": {"file": "scheme.svg", "kind": "svg", "x": 0, "y": 0, "w": cw, "h": ch, "rot": 0,
                         "opacity": 1, "show": True, "vw": cw, "vh": ch}}


def _b(target, code, action, **kw):
    return {"target": target, "code": code, "action": action, **kw}


NIGHT = {"from": "18:00", "to": "07:00", "days": [1, 2, 3, 4, 5, 6, 7]}
BINDINGS = {
    "Hallway motion": {"occupancy": {"true": _b("Hallway light", "state", "on", **{"for": 120, "retrigger": "extend"},
                                                conditions=[{"device": "Hallway motion", "code": "illuminance", "op": "<", "value": 80}])}},
    "Kitchen motion": {"occupancy": {"true": _b("Under-cabinet lights", "state", "on", **{"for": 300, "retrigger": "extend"},
                                                time_window=NIGHT)}},
    "Bathroom climate": {"humidity": {"above": _b("bath_fan", "power", "on", threshold=70, hyst=5),
                                      "below": _b("bath_fan", "power", "off", threshold=58, hyst=3)}},
    "Living room window": {"contact": {"false": _b("living_ac", "power", "off")}},
    "Bedroom window": {"contact": {"false": _b("bedroom_ac", "power", "off")}},
    "Sofa button": {"action": {"single": _b("Living room ceiling", "state", "toggle"),
                               "double": _b("Living room wall switch", "state_l2", "toggle"),
                               "hold": _b("Living room wall switch", "state_l1", "toggle")}},
    "Bedside button": {"action": {"single": _b("Bedside lamp", "state", "toggle"),
                                  "double": _b("Bedroom ceiling", "state", "off")}},
    "Doorbell": {"action": {"single": _b("Hallway light", "state", "on", **{"for": 60, "retrigger": "restart"})}},
    "Kitchen leak": {"water_leak": {"true": _b("water_heater", "power", "off")}},
    "Kitchen smoke": {"smoke": {"true": _b("Kitchen light", "state", "on")}},
    "bathroom_radar": {"presence": {"true": _b("Bathroom light", "state", "on"), "false": _b("Bathroom light", "state", "off")}},
    "presence": {"event": {"arrival": _b("Hallway light", "state", "on", **{"for": 180, "retrigger": "restart"}),
                           "departure": _b("Living room wall switch", "state_l1", "off")}},
}
AUTOMATIONS = {
    "Night light/state": {"schedule": [{"time": "20:30", "days": [1, 2, 3, 4, 5, 6, 7], "action": "on"},
                                       {"time": "07:00", "days": [1, 2, 3, 4, 5, 6, 7], "action": "off"}]},
    "water_heater/power": {"schedule": [{"time": "05:30", "days": [1, 2, 3, 4, 5, 6, 7], "action": "on"},
                                        {"time": "23:00", "days": [1, 2, 3, 4, 5, 6, 7], "action": "off"}]},
    "Kettle socket/state": {"inching_sec": 600},
    "Bathroom light/state": {"inching_sec": 1800},
}


def settings_json() -> dict:
    rooms = [{"id": rid, "name": name, "devices": [d["id"] for d in catalog.DEVICES
                                                   if d["room"] == rid and d["type"] != "blaster" and not d.get("outdoor")]}
             for rid, (name, _p) in catalog.ROOMS.items()]
    return {"_version": 1, "names": {d["id"]: d["name"] for d in catalog.DEVICES if d.get("name") and d.get("via") == "z2m"}, "channel_names": {
                "Living room wall switch": {"state_l1": "Floor lamp", "state_l2": "LED strip"}},
            "channel_dimrange": {}, "bindings": BINDINGS,
            "favorites": [{"device": "Living room ceiling", "code": "state", "alias": "Living room"},
                          {"device": "living_ac", "code": "power", "alias": "Living room AC"},
                          {"device": "front_lock", "code": "locked", "alias": "Front door"},
                          {"device": "Kettle socket", "code": "state", "alias": "Kettle"}],
            "rooms": rooms, "tab_order": {}, "tile_sizes": {}, "automations": AUTOMATIONS, "rules_disabled": [],
            "house": {"lang": "en"}}


def playground() -> dict:
    """The panel builder's playground: a designed 1024 x 600 tablet (clock, weather, lights, the living room's warmth,
    its AC, the balcony camera); a guest reshapes it in the builder, the turn's reset brings it back."""
    tile = {"font": "text", "align": "center", "bg": "#232a36", "fit": False, "size": 24, "pad": 8}
    w = [
        {"id": "clock_1", "type": "clock", "x": 24, "y": 16, "w": 440, "h": 150, "font": "clock", "align": "center", "fit": True, "pad": 10},
        {"id": "weather_1", "type": "weather", "x": 488, "y": 16, "w": 512, "h": 274, "bg": "#232a36", "mode": "auto", "pad": 0},
        {"id": "toggle_kitchen", "type": "toggle", "x": 24, "y": 182, "w": 212, "h": 112, **tile, "text": "Kitchen light", "icon": "bulb",
         "cmd_payload": "toggle", "state_topic": "home/state/Kitchen light/state", "cmd_topic": "home/cmd/Kitchen light/state"},
        {"id": "toggle_bedside", "type": "toggle", "x": 252, "y": 182, "w": 212, "h": 112, **tile, "text": "Bedside lamp", "icon": "bulb",
         "cmd_payload": "toggle", "state_topic": "home/state/Bedside lamp/state", "cmd_topic": "home/cmd/Bedside lamp/state"},
        {"id": "dimmer_ceiling", "type": "dimmer", "x": 24, "y": 310, "w": 212, "h": 112, **tile, "text": "Ceiling", "icon": "bulb",
         "state_topic": "home/state/Living room ceiling/brightness_pct", "dim_topic": "home/cmd/Living room ceiling/brightness",
         "cmd_topic": "home/cmd/Living room ceiling/state", "onoff_topic": "home/state/Living room ceiling/state"},
        {"id": "sensor_living", "type": "sensor", "x": 252, "y": 310, "w": 212, "h": 112, **tile, "fit": True, "text": "Living room", "icon": "thermo", "suffix": "\u00b0C",
         "decimals": 1, "state_topic": "home/state/Living room climate/temperature"},
        {"id": "camera_balcony", "type": "camera", "x": 24, "y": 438, "w": 440, "h": 146, "cam_id": "sim-balcony", "pad": 0},
        {"id": "ac_living", "type": "ac", "x": 488, "y": 306, "w": 512, "h": 278, "bg": "#232a36", "text": "Living room AC",
         "device": "living_ac", "pad": 0},
    ]
    return {"playground": {"hw": "android", "w": 1024, "h": 600, "rotation": 0, "title": "Playground tablet", "widgets": w}}


def files() -> dict:
    """Relative path -> bytes of every seed file."""
    def js(v):
        return (json.dumps(v, indent=1, ensure_ascii=True) + "\n").encode()
    return {
        "settings.json": js(settings_json()),
        "mqtt_devices.json": js(devices.mqtt_devices()),
        "plugin-data/map/map.json": js(map_json()),
        "plugin-data/map/scheme.svg": scheme_svg().encode(),
        "plugin-data/map/rooms.json": js(settings_json()["rooms"]),
        "plugin-data/ir/settings.json": js({"ir_blasters": [{"node": IR_NODE, "name": "Living room IR blaster", "rx": False}],
                                            "ir_appliances": [IR_FAN], "ir_toggles": []}),
        "plugin-data/ir/ir_remotes.json": js([FAN_REMOTE]),
        "plugin-data/climate/settings.json": js({"climate": {"room_temp_from": {}}}),
        "plugin-data/panels/layouts.json": js(playground()),
    }


def write(out: Path):
    for rel, data in files().items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


if __name__ == "__main__":
    write(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "house"))
