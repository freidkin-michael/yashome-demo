"""The demo flat as a small physical model, stepped in simulated time: sun and weather outside, each room's
temperature, humidity, light and CO2, the power every load draws, and three residents moving through a day.
Pure (no MQTT): `state` holds each device's values in its own wire names; the runner publishes what changed."""
import math
import random
import time

from . import catalog, devices
from . import weather_day as WD

WEATHER = {   # mode: (mean outdoor C, day swing C, cloud 0..1, humidity %, wind m/s, rain)
    "clear": (17, 7, 0.1, 55, 2, False), "cloudy": (13, 3, 0.7, 70, 4, False),
    "rain": (11, 2, 0.95, 92, 6, True), "heatwave": (31, 6, 0.0, 35, 1, False)}
DAY = [   # hour -> where each resident is (None = away), from that hour on
    (0, {"Alex": "bedroom", "Sam": "bedroom", "Mia": "kids"}),
    (7, {"Alex": "bath", "Sam": "kitchen", "Mia": "kids"}),
    (8, {"Alex": "kitchen", "Sam": "hall", "Mia": "kitchen"}),
    (9, {"Alex": None, "Sam": None, "Mia": None}),
    (15, {"Alex": None, "Sam": "living", "Mia": "kids"}),
    (18, {"Alex": "kitchen", "Sam": "living", "Mia": "living"}),
    (20, {"Alex": "living", "Sam": "bath", "Mia": "bath"}),
    (21, {"Alex": "living", "Sam": "living", "Mia": "kids"}),
    (23, {"Alex": "bedroom", "Sam": "bedroom", "Mia": "kids"}),
]
WINDOW_ROOMS = {"Living room window": "living", "Bedroom window": "bedroom"}
START = {   # room: (temperature, humidity, sun through its windows 0..1): each room has its own climate on entry
    "living": (22.6, 44, 1.0), "kitchen": (23.1, 48, 0.5), "bedroom": (20.4, 46, 0.3),
    "kids": (21.8, 43, 0.6), "hall": (20.9, 41, 0.0), "bath": (24.2, 58, 0.0)}
ROOM_NAMES = {r: n for r, (n, _p) in catalog.ROOMS.items()}


class World:
    def __init__(self, now=None, seed=7):
        self.rnd = random.Random(seed)
        self.t = float(now if now is not None else time.time())       # simulated epoch seconds
        self.speed = 1
        self.forced = None                 # (mode, until): a guest's weather, held a while; None = the day script
        self.weather = WD.mode_at(self.t)
        self.t_out = WD.target(self.t, self.weather)
        self.cat = catalog.by_id()
        self.rooms = {r: {"T": START[r][0], "H": float(START[r][1]), "co2": 520.0, "lux": 0.0} for r in catalog.ROOMS}
        self.where = dict(DAY[0][1])
        self.pinned: dict = {}         # resident -> (room or None, until): a guest moved them (Simulate)
        self.state: dict = {}
        self.online: dict = {}
        self.kettle_until = 0.0
        self.fridge_phase = 0.0
        self.energy_kwh = 3.2
        self.events: list = []         # (device id, payload dict) one-off messages: a button press, arrival
        for d in catalog.DEVICES:
            self.state[d["id"]] = self._initial(d)
            self.online[d["id"]] = True
        self.step(0)

    # ---- devices at the start ----
    def _initial(self, d) -> dict:
        t = d["type"]
        if t == "dimmer":
            return {"state": "OFF", "brightness": 180, "linkquality": 140}
        if t == "switch":
            return {"state": "OFF", "linkquality": 150}
        if t == "switch2":
            return {"state_l1": "OFF", "state_l2": "OFF", "linkquality": 130}
        if t == "plug":
            on = d.get("appliance") == "fridge" or d.get("feeds") is not None
            return {"state": "ON" if on else "OFF", "power": 0.0, "energy": 1.4, "voltage": 230.0, "linkquality": 160}
        if t == "climate":
            return {"temperature": 21.5, "humidity": 45.0, "battery": 87, "linkquality": 110}
        if t == "contact":
            return {"contact": True, "battery": 92, "linkquality": 120}
        if t == "motion":
            return {"occupancy": False, "illuminance": 0, "battery": 78, "linkquality": 100}
        if t in ("leak", "smoke"):
            return {("water_leak" if t == "leak" else "smoke"): False, "battery": 95, "linkquality": 105}
        if t == "button":
            return {"battery": 81, "linkquality": 90}
        if t == "tv":
            return {"power": "OFF", "volume": 18, "mute": "OFF", "input": "Live TV"}
        if t == "ac":
            return {"power": "OFF", "temp": "23", "fan": "auto", "mode": "cool", "room_temp": 21.5}
        if t == "radar":
            return {"presence": "OFF", "distance": 0, "illuminance": 0}
        if t == "weather":
            return {"temperature": 15.0, "humidity": 60.0, "illuminance": 0, "wind": 2.0, "rain": "OFF"}
        if t == "air":
            return {"co2": 520, "temperature": 21.5, "humidity": 45.0}
        if t == "lock":
            return {"locked": "LOCKED", "door": "closed", "battery": 74}
        if t == "relay":
            return {"power": "OFF"}
        if t == "heater":
            return {"power": "ON", "watts": 0, "water_temp": 52.0}
        if t == "meter":
            return {"power": 0, "energy": 3.2, "voltage": 230.0}
        if t == "blaster":
            return {}
        raise ValueError(t)

    # ---- commands from the house ----
    def command(self, dev_id: str, values: dict) -> bool:
        """A /set or a command topic: the device takes what it can. False = unknown device or channel."""
        d, st = self.cat.get(dev_id), self.state.get(dev_id)
        if d is None or not self.online.get(dev_id):
            return False
        ok = False
        for k, v in values.items():
            if k not in st or k not in self._writable(d):
                continue
            if k.startswith("state") or d["via"] == "esp" and isinstance(st[k], str) and st[k] in ("ON", "OFF"):
                v = _onoff(v, st[k])
                if dev_id == "Kettle socket" and v == "ON" and st[k] != "ON":
                    self.kettle_until = self.t + 150
            elif k == "locked":
                v = "UNLOCKED" if str(v).upper() in ("UNLOCKED", "OFF", "FALSE", "0") else "LOCKED"
            elif k in ("brightness", "volume"):
                v = max(0, min(254 if k == "brightness" else 100, int(float(v))))
            elif k in ("temp", "fan", "mode", "input"):
                rng = {"temp": devices.AC_TEMPS, "fan": devices.AC_FANS, "mode": devices.AC_MODES,
                       "input": devices.TV_INPUTS}[k]
                v = str(int(float(v))) if k == "temp" and _is_num(v) else str(v)
                if v not in rng:
                    continue
            st[k] = v
            ok = True
        if ok and d["type"] == "dimmer" and "brightness" in values and "state" not in values:
            st["state"] = "ON" if st["brightness"] > 0 else "OFF"
        return ok

    @staticmethod
    def _writable(d) -> set:
        if d["via"] == "z2m":
            return {"state", "state_l1", "state_l2", "brightness"}
        if d["type"] == "blaster":
            return set()
        return {c["code"] for c in devices.esp_entry(d)["controls"] if c.get("command_topic")}

    def press(self, dev_id: str, action: str = "single"):
        self.events.append((dev_id, {"action": action, "battery": self.state[dev_id].get("battery", 80)}))

    def set_weather(self, mode: str, minutes: float = 20) -> bool:
        """A guest's weather, held `minutes` of sim time; "auto" gives the day back to its script."""
        if mode == "auto":
            self.forced = None
            self.weather = WD.mode_at(self.t)
            return True
        if mode not in WEATHER:
            return False
        self.forced, self.weather = (mode, self.t + minutes * 60), mode
        return True

    def move(self, who: str, room) -> bool:
        """A guest sends a resident to a room (None: out of the flat) until the next change of their day."""
        if who not in catalog.RESIDENTS or room not in (None, *catalog.ROOMS):
            return False
        h, nxt = self._hour(), 24.0
        for start, _p in DAY:
            if start > h:
                nxt = start
                break
        self.pinned[who] = (room, self.t + (nxt - h) * 3600)
        self._residents()
        return True

    def set_speed(self, x: int):
        if x in (1, 10, 60):
            self.speed = x

    def event(self, name: str):
        """A scenario event: leak, smoke, doorbell, window_open, window_close, arrive, leave."""
        st = self.state
        if name == "leak":
            st["Kitchen leak"]["water_leak"] = True
        elif name == "leak_dry":
            st["Kitchen leak"]["water_leak"] = False
        elif name == "smoke":
            st["Kitchen smoke"]["smoke"] = True
        elif name == "smoke_clear":
            st["Kitchen smoke"]["smoke"] = False
        elif name == "doorbell":
            self.press("Doorbell")
        elif name in ("window_open", "window_close"):
            st["Living room window"]["contact"] = name == "window_close"
        else:
            return False
        return True

    # ---- the model ----
    def _hour(self) -> float:
        lt = time.localtime(self.t)
        return lt.tm_hour + lt.tm_min / 60 + lt.tm_sec / 3600

    def outdoor(self):
        _mean, _swing, cloud, hum, wind, rain = WEATHER[self.weather]
        h = self._hour()
        temp = self.t_out                                 # the day's curve and the weather's offset, followed smoothly
        sun = max(0.0, math.sin((h - 6.5) / 12.5 * math.pi)) if 6.5 <= h <= 19 else 0.0
        lux = 60000 * sun * (1 - 0.8 * cloud)
        return temp, hum, lux, wind, rain

    def _occupants(self, room) -> int:
        return sum(1 for r in self.where.values() if r == room)

    def _residents(self):
        h, plan = self._hour(), DAY[0][1]
        for start, p in DAY:
            if h >= start:
                plan = p
        before = any(self.where.values())
        self.pinned = {w: p for w, p in self.pinned.items() if p[1] > self.t}
        self.where = {**plan, **{w: p[0] for w, p in self.pinned.items()}}
        after = any(self.where.values())
        if before != after:
            self.events.append(("presence", {"event": "arrival" if after else "departure"}))

    def _on(self, dev_id, code="state") -> bool:
        return self.state.get(dev_id, {}).get(code) in ("ON", True)

    def loads(self) -> dict:
        """Watts per device right now (lamps by their brightness, appliances by what they do)."""
        w = {}
        for d in catalog.DEVICES:
            st, did = self.state[d["id"]], d["id"]
            for code, (_name, _typ, watts, _at) in (d.get("loads") or {}).items():
                if d["type"] == "heater":
                    continue
                if st.get(code) in ("ON", True):
                    frac = st.get("brightness", 254) / 254 if d["type"] == "dimmer" else 1.0
                    w[did] = w.get(did, 0) + watts * frac
            if d["type"] == "tv" and self._on(did, "power") and self._on("tv_socket"):
                w[did] = d["watts"]
            if d["type"] == "ac" and self._on(did, "power"):
                room = self.rooms[d["room"]]
                gap = abs(room["T"] - float(st["temp"]))
                w[did] = d["watts"] * (0.25 + 0.75 * min(1, gap / 2)) if st["mode"] != "fan" else 60
            if d["type"] == "relay" and self._on(did, "power"):
                w[did] = d.get("watts", 0)
            if d["type"] == "heater" and self._on(did, "power") and st["water_temp"] < 60:
                w[did] = d["watts"]
        if self._on("Kettle socket") and self.t < self.kettle_until:
            w["Kettle socket"] = 2000
        if self._on("Fridge socket") and (self.t / 60) % 40 < 16:
            w["Fridge socket"] = 120
        return w

    def step(self, dt: float):
        """Advance dt simulated seconds."""
        self.t += dt
        if self.forced and self.t >= self.forced[1]:
            self.forced = None
        self.weather = self.forced[0] if self.forced else WD.mode_at(self.t)
        self.t_out += (WD.target(self.t, self.weather) - self.t_out) * min(1.0, dt / 3600)    # the air follows within the hour
        temp_o, hum_o, lux_o, wind, rain = self.outdoor()
        self._residents()
        loads = self.loads()
        for rid, room in self.rooms.items():
            occ = self._occupants(rid)
            leak = 0.00003 + (0.0006 if any(WINDOW_ROOMS.get(w) == rid and not self.state[w]["contact"]
                                            for w in WINDOW_ROOMS) else 0)
            heat = 0.00002 * occ * 4 + (0.00004 if rid == "kitchen" and loads.get("Kettle socket") else 0)
            sun = START[rid][2] * lux_o / 60000
            room["T"] += dt * (leak * (temp_o - room["T"]) + heat + 0.00006 * sun)
            room["T"] = 15 + (room["T"] - 15) * (1 - 0.000004 * dt) if temp_o < 15 else room["T"]   # heating keeps 15+
            for d in catalog.DEVICES:
                if d["type"] == "ac" and d["room"] == rid and self._on(d["id"], "power"):
                    st = self.state[d["id"]]
                    target, mode = float(st["temp"]), st["mode"]
                    if mode in ("cool", "auto") and room["T"] > target or mode in ("heat", "auto") and room["T"] < target:
                        room["T"] += dt * 0.0015 * (target - room["T"])
                    if mode == "dry":
                        room["H"] += dt * 0.0005 * (35 - room["H"])
            gain = (0.06 if rid == "bath" and occ else 0.0) + 0.0004 * occ
            vent = 0.004 if rid == "bath" and self._on("bath_fan", "power") else 0.0
            room["H"] += dt * (gain + (leak * 20 + vent) * (hum_o * 0.7 - room["H"]) + 0.00005 * (45 - room["H"]))
            room["H"] = max(20.0, min(99.0, room["H"]))
            room["co2"] += dt * (0.04 * occ - (leak * 30 + 0.0006) * (room["co2"] - 420))
            lamps = sum(150 * (loads.get(d["id"], 0) > 0) for d in catalog.DEVICES
                        if d["room"] == rid and d.get("loads") and d["type"] != "heater")
            day = lux_o * (0.012 if rid in ("living", "bedroom", "kitchen", "kids") else 0.001)
            room["lux"] = day + lamps
        self._apply_sensors(temp_o, hum_o, lux_o, wind, rain, loads, dt)

    def _apply_sensors(self, temp_o, hum_o, lux_o, wind, rain, loads, dt):
        total = 80 + sum(loads.values())
        self.energy_kwh += total * dt / 3.6e6
        for d in catalog.DEVICES:
            did, t, st = d["id"], d["type"], self.state[d["id"]]
            room = self.rooms[d["room"]]
            occ = self._occupants(d["room"])
            if t == "climate":                     # a sensor reads its room with a little noise of its own
                st["temperature"] = round(room["T"] + self.rnd.uniform(-0.06, 0.06), 1)
                st["humidity"] = round(room["H"] + self.rnd.uniform(-0.4, 0.4))
            elif t == "motion":
                st["occupancy"], st["illuminance"] = occ > 0, int(room["lux"])
            elif t == "radar":
                st["presence"] = "ON" if occ else "OFF"
                st["distance"] = 120 + 40 * occ if occ else 0
                st["illuminance"] = int(room["lux"])
            elif t == "air":
                st["co2"], st["temperature"], st["humidity"] = int(room["co2"]), round(room["T"], 1), round(room["H"])
            elif t == "ac":
                st["room_temp"] = round(room["T"], 1)
            elif t == "weather":
                st.update(temperature=round(temp_o, 1), humidity=round(hum_o), illuminance=int(lux_o),
                          wind=round(wind + self.rnd.random(), 1), rain="ON" if rain else "OFF")
            elif t == "plug":
                fed = d.get("feeds")
                w = loads.get(fed, 0) if fed else loads.get(did, 0)
                st["power"] = round(w if self._on(did) else 0, 1)
                st["energy"] = round(st["energy"] + st["power"] * dt / 3.6e6, 3)
            elif t == "heater":
                heating = loads.get(did, 0) > 0
                st["watts"] = d["watts"] if heating else 0
                st["water_temp"] = round(min(60.0, st["water_temp"] + dt * (0.004 if heating else -0.0004)), 1)
            elif t == "meter":
                st["power"], st["energy"] = int(total), round(self.energy_kwh, 2)
                st["voltage"] = round(229 + self.rnd.random() * 3, 1)
        self.online["living_tv"] = self._on("tv_socket")    # the TV hangs off its socket
        if not self.online["living_tv"]:
            self.state["living_tv"]["power"] = "OFF"


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _onoff(v, cur) -> str:
    s = str(v).strip().upper()
    if s == "TOGGLE":
        return "OFF" if cur == "ON" else "ON"
    return "ON" if s in ("ON", "TRUE", "1") else "OFF"


def summary(w: World) -> dict:
    """What the Simulate panel shows: the simulated time, speed, weather and where everyone is."""
    lt = time.localtime(w.t)
    until = time.strftime("%H:%M", time.localtime(w.forced[1])) if w.forced else None
    return {"time": f"{lt.tm_hour:02d}:{lt.tm_min:02d}", "t": int(w.t), "speed": w.speed, "weather": w.weather, "held_until": until,
            "residents": {r: w.where.get(r) for r in catalog.RESIDENTS},
            "rooms": {r: {"name": ROOM_NAMES[r], "t": round(v["T"], 1), "h": round(v["H"])} for r, v in w.rooms.items()},
            "outdoor": round(w.outdoor()[0], 1)}
