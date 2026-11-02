"""The demo simulator: its devices are what the zigbee plug-in and the core read them as, commands change them,
the model behaves like a flat (an AC cools, a shower fogs the bath, the fan clears it, loads draw power),
and the reset clears every retained topic before it answers."""
import importlib
import json
import sys
import time

import app as core

catalog = importlib.import_module("yashome_plugins.demo.sim.catalog")
devices = importlib.import_module("yashome_plugins.demo.sim.devices")
world = importlib.import_module("yashome_plugins.demo.sim.world")
simmain = importlib.import_module("yashome_plugins.demo.sim.__main__")
zigbee = sys.modules["yashome_plugins.zigbee"]

def at(hour):
    return time.mktime((2026, 1, 15, hour, 0, 0, 0, 0, -1))      # a winter day, local time like the simulator


NOON = at(10)


def test_about_forty_devices_of_every_kind_in_six_rooms():
    kinds = {d["type"] for d in catalog.DEVICES}
    assert 35 <= len(catalog.DEVICES) <= 45
    assert {"dimmer", "switch", "switch2", "plug", "climate", "contact", "motion", "leak", "smoke", "button", "tv", "ac",
            "radar", "weather", "air", "lock", "relay", "heater", "meter", "blaster"} <= kinds
    assert {d["room"] for d in catalog.DEVICES} == set(catalog.ROOMS)
    assert len({d["id"] for d in catalog.DEVICES}) == len(catalog.DEVICES)


def test_zigbee_devices_register_as_the_zigbee_plugin_reads_them():
    cats = {}
    for z in devices.bridge_devices():
        d = zigbee.device_from_z2m(z)
        if d is not None:
            assert not d["unsupported"], d["id"]
            cats[d["id"]] = (d["category"], sorted(c["code"] for c in d["controls"]))
    assert cats["Living room ceiling"] == ("switch", ["brightness", "state"])
    assert cats["Living room wall switch"][1] == ["state_l1", "state_l2"]
    assert cats["Sofa button"][0] == "button"
    assert cats["Kettle socket"] == ("switch", ["energy", "power", "state", "voltage"])
    assert cats["Front door"] == ("sensor", ["battery", "contact"])
    z = next(x for x in devices.bridge_devices() if x["friendly_name"] == "Kitchen leak")
    d = zigbee.device_from_z2m(z)
    assert (d["model"], d["vendor"], d["description"]) == ("SJCGQ11LM", "Aqara", "Water leak sensor")


def test_generic_devices_are_valid_mqtt_devices():
    for e in devices.mqtt_devices():
        ok = core._safe_controls(e["id"], e["controls"])
        assert len(ok) == len(e["controls"]), e["id"]
        assert all(c.get("state_topic", "").startswith(devices.node(e) + "/") for c in e["controls"])


def test_a_command_changes_the_device():
    w = world.World(NOON)
    assert w.command("Living room ceiling", {"state": "ON", "brightness": 100})
    assert w.state["Living room ceiling"] == {**w.state["Living room ceiling"], "state": "ON", "brightness": 100}
    assert w.command("Living room wall switch", {"state_l2": "TOGGLE"}) and w.state["Living room wall switch"]["state_l2"] == "ON"
    assert w.command("living_ac", {"temp": "19.0"}) and w.state["living_ac"]["temp"] == "19"
    assert not w.command("living_ac", {"mode": "turbo"})
    assert w.command("front_lock", {"locked": "UNLOCKED"}) and w.state["front_lock"]["locked"] == "UNLOCKED"
    assert not w.command("Kitchen motion", {"occupancy": True}) and not w.command("tv_socket", {"power": 5})
    assert not w.command("nothing", {"state": "ON"})


def test_the_tv_needs_its_socket():
    w = world.World(NOON)
    w.command("tv_socket", {"state": "OFF"})
    w.step(2)
    assert not w.online["living_tv"] and not w.command("living_tv", {"power": "ON"})
    w.command("tv_socket", {"state": "ON"})
    w.step(2)
    assert w.command("living_tv", {"power": "ON"})
    w.step(2)
    assert w.state["tv_socket"]["power"] == 90


def test_an_ac_cools_its_room_and_draws_power():
    w = world.World(NOON)
    w.set_weather("heatwave", minutes=24 * 60)
    for _ in range(300):
        w.step(60)
    hot = w.rooms["living"]["T"]
    w.command("living_ac", {"power": "ON", "temp": "21", "mode": "cool"})
    w.step(2)
    assert w.loads()["living_ac"] > 300
    for _ in range(120):
        w.step(30)
    assert w.rooms["living"]["T"] < hot - 2 and w.state["living_ac"]["room_temp"] == round(w.rooms["living"]["T"], 1)


def test_a_shower_fogs_the_bath_and_the_fan_clears_it():
    w = world.World(NOON)
    w.where = {"Alex": "bath"}
    w._residents = lambda: None                  # Alex stays in the shower
    for _ in range(60):
        w.step(20)
    foggy = w.rooms["bath"]["H"]
    assert foggy > 75
    w.where = {}
    w.command("bath_fan", {"power": "ON"})
    for _ in range(60):
        w.step(20)
    assert w.rooms["bath"]["H"] < foggy - 15


def test_the_meter_counts_every_load():
    w = world.World(NOON)
    w.step(2)
    idle = w.state["energy_meter"]["power"]
    w.command("Kettle socket", {"state": "ON"})
    w.step(2)
    assert w.state["energy_meter"]["power"] >= idle + 2000 and w.state["Kettle socket"]["power"] == 2000
    w.step(200)
    assert w.state["Kettle socket"]["power"] == 0          # boiled


def test_residents_come_and_go_with_the_day():
    w = world.World(at(7))
    assert w.where["Alex"] == "bath"
    w.step(3 * 3600)                                       # 10:00: everyone out
    assert not any(w.where.values()) and ("presence", {"event": "departure"}) in w.events


class FakeCli:
    def __init__(self):
        self.out = []

    def publish(self, topic, payload=None, retain=False, qos=0):
        self.out.append((topic, payload, retain))


def test_the_runner_speaks_z2m_and_esphome():
    cli = FakeCli()
    s = simmain.Sim(cli)
    s.publish_all(force=True)
    topics = {t for t, _p, _r in cli.out}
    assert {"zigbee2mqtt/bridge/state", "zigbee2mqtt/bridge/devices", "zigbee2mqtt/Kitchen light",
            "living-ac/status", "living-ac/select/mode/state", "presence/state"} <= topics
    cli.out.clear()
    s._handle("zigbee2mqtt/Kitchen light/set", json.dumps({"state": "ON"}), False)
    assert ("zigbee2mqtt/Kitchen light", json.dumps({"state": "ON", "linkquality": 150}, separators=(",", ":")), True) in cli.out
    s._handle("living-ac/select/mode/command", "heat", False)
    assert ("living-ac/select/mode/state", "heat", True) in cli.out
    s._handle("demo/sim/weather", "rain", False)
    assert s.w.weather == "rain"


def test_the_reset_clears_retained_topics_then_answers(monkeypatch):
    cli = FakeCli()
    s = simmain.Sim(cli)

    class Probe:
        def __init__(self, *a, **k):
            self.on_message = None

        def connect(self, *a):
            pass

        def subscribe(self, *a):
            pass

        def loop_start(self):
            for t in ("home/state/x/power", "zigbee2mqtt/Old one", "$SYS/broker/uptime", "zigbee2mqtt/bridge/state",
                      simmain._IR_NODE + "/status"):
                self.on_message(None, None, type("M", (), {"topic": t, "retain": True, "payload": b"1"})())

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

    monkeypatch.setattr(simmain.mqtt, "Client", Probe)
    monkeypatch.setattr(simmain.time, "sleep", lambda s: None)
    s.w.command("Kitchen light", {"state": "ON"})
    s.reset()
    cleared = [t for t, p, r in cli.out if r and p == b""]
    assert cleared == ["home/state/x/power", "zigbee2mqtt/Old one"]          # the bridge and the IR node never read offline
    assert not [p for t, p, r in cli.out if t in ("zigbee2mqtt/bridge/state", simmain._IR_NODE + "/status") and "online" not in str(p)]
    assert cli.out[-1][0] == "demo/reset/done" and s.w.state["Kitchen light"]["state"] == "OFF"


def test_the_checked_in_seed_is_what_the_catalog_writes():
    seedgen = importlib.import_module("yashome_plugins.demo.sim.seedgen")
    seed = importlib.import_module("yashome_plugins.demo.seed").SEED
    files = seedgen.files()
    on_disk = {str(p.relative_to(seed)): p.read_bytes() for p in seed.rglob("*") if p.is_file()}
    assert sorted(on_disk) == sorted(files)
    assert [k for k in files if on_disk[k] != files[k]] == [], "run python -m sim.seedgen in plugins-extra/demo"


def test_rooms_start_apart_and_every_room_has_a_reading():
    w = world.World(NOON)
    temps = {r: v["T"] for r, v in w.rooms.items()}
    assert len(set(temps.values())) == len(temps)
    assert {d["room"] for d in catalog.DEVICES if d["type"] in ("climate", "air")} == set(catalog.ROOMS)


def test_a_guest_moves_a_resident_until_their_day_moves_on():
    w = world.World(at(10))                                  # everyone is out
    assert w.move("Alex", "bath") and w.where["Alex"] == "bath"
    w.step(3600)
    assert w.where["Alex"] == "bath"
    w.step(5 * 3600)                                         # 16:00: the day's plan again
    assert w.where["Alex"] is None
    assert not w.move("Eve", "bath") and not w.move("Alex", "garage")


def test_the_panel_summary():
    s = world.summary(world.World(NOON))
    assert set(s) == {"time", "t", "speed", "weather", "held_until", "residents", "rooms", "outdoor"} and s["rooms"]["hall"]["name"] == "Hallway"



def test_a_day_at_x60_goes_through_its_weather():
    w = world.World(at(0))
    seen, last_t, jumps = set(), w.outdoor()[0], 0.0
    for _ in range(24 * 60):                               # a sim day in one-minute steps (24 min of x60)
        w.step(60)
        seen.add(w.weather)
        jumps = max(jumps, abs(w.outdoor()[0] - last_t))
        last_t = w.outdoor()[0]
    assert len(seen) >= 3, seen
    assert jumps < 0.5                                     # the air never jumps when the weather turns


def test_a_guest_s_weather_holds_20_minutes_then_the_day_takes_over():
    w = world.World(NOON)
    script = w.weather
    other = "rain" if script != "rain" else "clear"
    assert w.set_weather(other) and w.weather == other and world.summary(w)["held_until"]
    w.step(19 * 60)
    assert w.weather == other
    w.step(2 * 60)
    assert w.weather == world.WD.mode_at(w.t) and world.summary(w)["held_until"] is None
    w.set_weather(other)
    assert w.set_weather("auto") and w.forced is None and not w.set_weather("snowstorm")



def test_one_physical_thing_is_one_icon_and_the_lines_follow_the_rule():
    import json
    seed = importlib.import_module("yashome_plugins.demo.seed").SEED
    m = json.loads((seed / "plugin-data" / "map" / "map.json").read_text())
    devs = {i["dev"] for i in m["items"] if i["kind"] == "device"}
    tv = [i for i in m["items"] if i.get("type") == "tv" or i.get("dev") == "living_tv"]
    assert [i["kind"] for i in tv if i["kind"] == "load"] == ["load"] and next(i for i in tv if i["kind"] == "load")["dev"] == "living_tv"
    assert "living_tv" in devs                                                  # drawn once: the load stands as the device
    fan = next(i for i in m["items"] if i.get("name") == "Ceiling fan")
    assert fan["dev"] == "ceiling_fan_ir"                                       # the blaster's dashed line has its end
    kinds = {d["id"]: d["type"] for d in catalog.DEVICES}
    for ln in m["links"]:                                                       # a wire starts at a switch, a dimmer, a socket or a controller
        assert kinds[ln["dev"]] in ("switch", "switch2", "dimmer", "plug", "relay"), ln
    names = [i.get("name") for i in m["items"] if i.get("name")]
    assert len(names) == len(set(names))
