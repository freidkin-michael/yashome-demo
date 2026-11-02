"""The demo flat's devices: one list both the seed (mqtt_devices.json, the map) and the simulator read.
`via` is the protocol the simulator speaks for it: "z2m" (zigbee2mqtt topics, the zigbee plug-in) or "esp"
(ESPHome-style topics, a generic MQTT device of mqtt_devices.json). Positions are metres on the 12 x 8 m plan.
`loads` are what a channel switches (name, map type, watts at full power) for the map and the power model."""

ROOMS = {   # id: (name, polygon in metres)
    "living": ("Living room", [(0, 0), (6, 0), (6, 4.6), (0, 4.6)]),
    "kitchen": ("Kitchen", [(6, 0), (9, 0), (9, 4.6), (6, 4.6)]),
    "bedroom": ("Bedroom", [(9, 0), (12, 0), (12, 4.6), (9, 4.6)]),
    "kids": ("Kids room", [(0, 4.6), (4, 4.6), (4, 8), (0, 8)]),
    "hall": ("Hallway", [(4, 4.6), (12, 4.6), (12, 6), (9, 6), (9, 8), (4, 8)]),
    "bath": ("Bathroom", [(9, 6), (12, 6), (12, 8), (9, 8)]),
}

DEVICES = [
    # ---- living room ----
    {"id": "Living room ceiling", "via": "z2m", "type": "dimmer", "room": "living", "at": (3, 2.3),
     "loads": {"state": ("Ceiling lamp", "lamp", 40, (3, 2.0))}},
    {"id": "Living room wall switch", "via": "z2m", "type": "switch2", "room": "living", "at": (3.4, 3.0),
     "loads": {"state_l1": ("Floor lamp", "lamp", 30, (0.6, 3.8)), "state_l2": ("LED strip", "led", 15, (1.0, 0.3))}},
    {"id": "tv_socket", "name": "TV socket", "via": "z2m", "type": "plug", "room": "living", "at": (4.1, 3.8), "feeds": "living_tv"},
    {"id": "living_tv", "name": "Living room TV", "via": "esp", "type": "tv", "room": "living", "at": (2.7, 4.2), "watts": 90},
    {"id": "living_ac", "name": "Living room AC", "via": "esp", "type": "ac", "room": "living", "at": (0.3, 1.5), "watts": 900},
    {"id": "living_radar", "name": "Living room radar", "via": "esp", "type": "radar", "room": "living", "at": (5.7, 0.4)},
    {"id": "Living room climate", "via": "z2m", "type": "climate", "room": "living", "at": (4.5, 2.5)},
    {"id": "Living room window", "via": "z2m", "type": "contact", "room": "living", "at": (2, 0.15), "window": True},
    {"id": "Sofa button", "via": "z2m", "type": "button", "room": "living", "at": (1.6, 3.2)},
    {"id": "living_ir", "name": "Living room IR blaster", "via": "esp", "type": "blaster", "room": "living", "at": (1.2, 2.5)},
    {"id": "balcony_weather", "name": "Balcony weather station", "via": "esp", "type": "weather", "room": "living", "at": (4.6, -0.3),
     "outdoor": True},             # on the balcony, in no room of the flat ("room": the simulator's air next to it)
    # ---- kitchen ----
    {"id": "Kitchen light", "via": "z2m", "type": "switch", "room": "kitchen", "at": (6.2, 4.3),
     "loads": {"state": ("Kitchen ceiling", "lamp", 36, (7.5, 2.3))}},
    {"id": "Under-cabinet lights", "via": "z2m", "type": "dimmer", "room": "kitchen", "at": (8.3, 1.5),
     "loads": {"state": ("Cabinet strip", "led", 12, (6.4, 0.4))}},
    {"id": "Kettle socket", "via": "z2m", "type": "plug", "room": "kitchen", "at": (8.6, 2.9), "appliance": "kettle"},
    {"id": "Fridge socket", "via": "z2m", "type": "plug", "room": "kitchen", "at": (6.6, 1.1), "appliance": "fridge"},
    {"id": "Kitchen motion", "via": "z2m", "type": "motion", "room": "kitchen", "at": (8.7, 4.3)},
    {"id": "Kitchen leak", "via": "z2m", "type": "leak", "room": "kitchen", "at": (7.4, 0.9)},
    {"id": "Kitchen smoke", "via": "z2m", "type": "smoke", "room": "kitchen", "at": (7.6, 1.9)},
    {"id": "Kitchen climate", "via": "z2m", "type": "climate", "room": "kitchen", "at": (7.1, 3.3)},
    # ---- bedroom ----
    {"id": "Bedroom ceiling", "via": "z2m", "type": "dimmer", "room": "bedroom", "at": (10.5, 2.3),
     "loads": {"state": ("Bedroom lamp", "lamp", 40, (10.5, 2.0))}},
    {"id": "Bedside lamp", "via": "z2m", "type": "plug", "room": "bedroom", "at": (11.6, 1.2),
     "loads": {"state": ("Reading lamp", "lamp", 8, (11.6, 0.8))}},
    {"id": "bedroom_ac", "name": "Bedroom AC", "via": "esp", "type": "ac", "room": "bedroom", "at": (11.8, 3.0), "watts": 700},
    {"id": "Bedroom climate", "via": "z2m", "type": "climate", "room": "bedroom", "at": (9.4, 2.0)},
    {"id": "Bedroom window", "via": "z2m", "type": "contact", "room": "bedroom", "at": (10.8, 0.15), "window": True},
    {"id": "Bedside button", "via": "z2m", "type": "button", "room": "bedroom", "at": (11.3, 1.6)},
    # ---- kids room ----
    {"id": "Kids room ceiling", "via": "z2m", "type": "dimmer", "room": "kids", "at": (2, 6.3),
     "loads": {"state": ("Kids ceiling lamp", "lamp", 30, (2, 6.0))}},
    {"id": "Night light", "via": "z2m", "type": "dimmer", "room": "kids", "at": (0.4, 7.6),
     "loads": {"state": ("Star lamp", "lamp", 5, (0.8, 7.5))}},
    {"id": "Kids room climate", "via": "z2m", "type": "climate", "room": "kids", "at": (3.6, 5.2)},
    {"id": "kids_air", "name": "Kids room air quality", "via": "esp", "type": "air", "room": "kids", "at": (3.6, 7.6)},
    {"id": "Kids room door", "via": "z2m", "type": "contact", "room": "kids", "at": (3.85, 6.6)},
    # ---- hallway ----
    {"id": "Hallway light", "via": "z2m", "type": "switch", "room": "hall", "at": (6.6, 7.7),
     "loads": {"state": ("Hallway ceiling", "lamp", 20, (6.5, 5.6))}},
    {"id": "Hallway motion", "via": "z2m", "type": "motion", "room": "hall", "at": (4.3, 5.0)},
    {"id": "Hallway climate", "via": "z2m", "type": "climate", "room": "hall", "at": (11.6, 4.95)},
    {"id": "front_lock", "name": "Front door lock", "via": "esp", "type": "lock", "room": "hall", "at": (7.0, 7.8)},
    {"id": "Front door", "via": "z2m", "type": "contact", "room": "hall", "at": (7.5, 7.85), "door": True},
    {"id": "Doorbell", "via": "z2m", "type": "button", "room": "hall", "at": (6.0, 7.85), "actions": ["single"]},
    # ---- bathroom ----
    {"id": "Bathroom light", "via": "z2m", "type": "switch", "room": "bath", "at": (9.3, 6.4),
     "loads": {"state": ("Bathroom ceiling", "lamp", 24, (10.5, 6.4))}},
    {"id": "bath_fan", "name": "Bathroom fan", "via": "esp", "type": "relay", "room": "bath", "at": (11.7, 6.4), "watts": 25},
    {"id": "Bathroom climate", "via": "z2m", "type": "climate", "room": "bath", "at": (10.5, 7.0)},
    {"id": "bathroom_radar", "name": "Bathroom radar", "via": "esp", "type": "radar", "room": "bath", "at": (9.3, 7.6)},
    {"id": "water_heater", "name": "Water heater", "via": "esp", "type": "heater", "room": "bath", "at": (11.7, 7.3), "watts": 1500},
    # ---- the whole flat ----
    {"id": "energy_meter", "name": "Energy meter", "via": "esp", "type": "meter", "room": "hall", "at": (4.3, 7.7)},
]

RESIDENTS = ["Alex", "Sam", "Mia"]     # fictional; Mia is the child of the flat


def name_of(d) -> str:
    return d.get("name") or d["id"]


def by_id() -> dict:
    return {d["id"]: d for d in DEVICES}
