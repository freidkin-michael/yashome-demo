"""How each kind of the catalog looks on the wire: a zigbee2mqtt definition (bridge/devices) or a generic MQTT
device of mqtt_devices.json with ESPHome-style topics (<node>/<component>/<object>/state | command, <node>/status)."""
from . import catalog

AC_TEMPS = [str(t) for t in range(16, 31)]
AC_FANS = ["auto", "low", "med", "max"]
AC_MODES = ["cool", "heat", "dry", "fan", "auto"]
TV_INPUTS = ["HDMI 1", "HDMI 2", "Live TV", "Apps"]
MODELS = {   # kind: (model, vendor, description) as zigbee2mqtt describes such devices
    "dimmer": ("TS110E_1gang", "Tuya", "Zigbee dimmer module, 1 gang"),
    "switch": ("QBKG04LM", "Aqara", "Smart wall switch (no neutral, single rocker)"),
    "switch2": ("QBKG03LM", "Aqara", "Smart wall switch (no neutral, double rocker)"),
    "plug": ("A1Z", "Nous", "Smart plug with power monitoring"),
    "climate": ("WSDCGQ11LM", "Aqara", "Temperature, humidity and pressure sensor"),
    "contact": ("MCCGQ11LM", "Aqara", "Door and window sensor"),
    "motion": ("RTCGQ11LM", "Aqara", "Motion sensor with illuminance"),
    "leak": ("SJCGQ11LM", "Aqara", "Water leak sensor"),
    "smoke": ("HS1SA", "Heiman", "Smoke detector"),
    "button": ("WXKG11LM", "Aqara", "Wireless mini switch")}
BOARDS = {   # kind: what an ESPHome node of that kind is built from
    "tv": "ESP32 bridge to the TV's network control (ESPHome)", "ac": "ESP32-C3 with an IR LED: drives the AC's own remote codes (ESPHome)",
    "radar": "ESP32-C3 with an HLK-LD2410C 24 GHz radar (ESPHome)", "weather": "ESP32 with BME280 and BH1750 sensors (ESPHome)",
    "air": "ESP32-C3 with a Sensirion SCD41 CO2 sensor (ESPHome)", "lock": "ESP32 bridge to a Bluetooth lock (ESPHome)",
    "relay": "Sonoff Basic R4 relay (ESPHome)", "heater": "Shelly Plus 1PM relay with power metering (ESPHome)",
    "meter": "ESP32 with a PZEM-004T energy meter (ESPHome)"}


def node(d) -> str:
    """The ESPHome node name of a generic device: its id with dashes."""
    return d["id"].replace("_", "-")


def _bin(prop, on=True, off=False):
    return {"type": "binary", "name": prop, "property": prop, "access": 1, "value_on": on, "value_off": off}


def _num(prop, unit, access=1):
    return {"type": "numeric", "name": prop, "property": prop, "access": access, "unit": unit}


def _state(prop="state"):
    return {"type": "binary", "name": "state", "property": prop, "access": 7, "value_on": "ON", "value_off": "OFF"}


def z2m_exposes(d) -> list:
    t = d["type"]
    batt = _num("battery", "%")
    lqi = _num("linkquality", "lqi")
    if t == "dimmer":
        return [{"type": "light", "features": [_state(), {"type": "numeric", "name": "brightness", "property": "brightness",
                                                          "access": 7, "value_min": 0, "value_max": 254}]}, lqi]
    if t == "switch":
        return [{"type": "switch", "features": [_state()]}, lqi]
    if t == "switch2":
        return [{"type": "switch", "endpoint": e, "features": [_state(f"state_{e}")]} for e in ("l1", "l2")] + [lqi]
    if t == "plug":
        return [{"type": "switch", "features": [_state()]}, _num("power", "W"), _num("energy", "kWh"),
                _num("voltage", "V"), lqi]
    if t == "climate":
        return [_num("temperature", "\u00b0C"), _num("humidity", "%"), batt, lqi]
    if t == "contact":
        return [_bin("contact"), batt, lqi]
    if t == "motion":
        return [_bin("occupancy"), _num("illuminance", "lx"), batt, lqi]
    if t == "leak":
        return [_bin("water_leak"), batt, lqi]
    if t == "smoke":
        return [_bin("smoke"), batt, lqi]
    if t == "button":
        return [{"type": "enum", "name": "action", "property": "action", "access": 1,
                 "values": d.get("actions") or ["single", "double", "hold"]}, batt, lqi]
    raise ValueError(f"no zigbee kind {t}")


def bridge_devices() -> list:
    """zigbee2mqtt/bridge/devices: the coordinator and every z2m device of the catalog."""
    out = [{"ieee_address": "0x0000000000000000", "type": "Coordinator", "friendly_name": "Coordinator",
            "interview_completed": True, "supported": True, "definition": None, "endpoints": {}}]
    n = 0
    for d in catalog.DEVICES:
        if d["via"] != "z2m":
            continue
        n += 1
        model, vendor, desc = MODELS[d["type"]]
        battery = d["type"] in ("climate", "contact", "motion", "leak", "smoke", "button")
        out.append({"ieee_address": f"0x{n:016x}", "type": "EndDevice" if battery else "Router",
                    "friendly_name": d["id"], "network_address": 1000 + n, "interview_completed": True,
                    "supported": True, "power_source": "Battery" if battery else "Mains (single phase)",
                    "definition": {"model": model, "vendor": vendor, "description": desc,
                                   "exposes": z2m_exposes(d), "options": []},
                    "endpoints": {"1": {"clusters": {"input": ["genBasic", "genOnOff"] if not battery else ["genBasic"],
                                                     "output": []}}}})
    return out


def _t(d, comp, obj, role="state"):
    return f"{node(d)}/{comp}/{obj}/{role}"


def _sw(d, code, obj, label, **kw):
    return {"kind": "switch", "code": code, "label": label, "state_topic": _t(d, "switch", obj),
            "command_topic": _t(d, "switch", obj, "command"), "payload_on": "ON", "payload_off": "OFF", **kw}


def _sens(d, code, label, unit="", **kw):
    return {"kind": "sensor", "code": code, "label": label, "unit": unit, "ro": True,
            "state_topic": _t(d, "sensor", code), **kw}


def _enum(d, code, label, rng):
    return {"kind": "setting_enum", "code": code, "label": label, "range": rng,
            "state_topic": _t(d, "select", code), "command_topic": _t(d, "select", code, "command")}


def esp_entry(d) -> dict:
    """The mqtt_devices.json entry of a generic (ESPHome-style) device."""
    t = d["type"]
    base = {"id": d["id"], "name": catalog.name_of(d), "transport": "mqtt", "model": BOARDS.get(t, "ESPHome node"),
            "availability_topic": f"{node(d)}/status", "payload_online": "online", "payload_offline": "offline"}
    if t == "tv":
        return {**base, "category": "tv", "controls": [
            _sw(d, "power", "power", "Power"),
            {"kind": "setting_int", "code": "volume", "label": "Volume", "min": 0, "max": 100,
             "state_topic": _t(d, "number", "volume"), "command_topic": _t(d, "number", "volume", "command")},
            _sw(d, "mute", "mute", "Mute"),
            _enum(d, "input", "Input", TV_INPUTS)]}
    if t == "ac":
        return {**base, "category": "climate", "controls": [
            _sw(d, "power", "power", "Power"), _enum(d, "temp", "Temperature", AC_TEMPS),
            _enum(d, "fan", "Fan", AC_FANS), _enum(d, "mode", "Mode", AC_MODES),
            _sens(d, "room_temp", "In the room", "\u00b0C")]}
    if t == "radar":
        return {**base, "category": "sensor", "controls": [
            {**_sens(d, "presence", "Presence"), "vtype": "bool", "payload_on": "ON",
             "state_topic": _t(d, "binary_sensor", "presence")},
            _sens(d, "distance", "Distance", "cm"), _sens(d, "illuminance", "Illuminance", "lx")]}
    if t == "weather":
        return {**base, "category": "sensor", "controls": [
            _sens(d, "temperature", "Outdoor temperature", "\u00b0C"), _sens(d, "humidity", "Outdoor humidity", "%"),
            _sens(d, "illuminance", "Daylight", "lx"), _sens(d, "wind", "Wind", "m/s"),
            {**_sens(d, "rain", "Rain"), "vtype": "bool", "payload_on": "ON", "state_topic": _t(d, "binary_sensor", "rain")}]}
    if t == "air":
        return {**base, "category": "sensor", "controls": [
            _sens(d, "co2", "CO2", "ppm"), _sens(d, "temperature", "Temperature", "\u00b0C"),
            _sens(d, "humidity", "Humidity", "%")]}
    if t == "lock":
        return {**base, "category": "switch", "controls": [
            {**_sw(d, "locked", "lock", "Lock", text_on="Locked", text_off="Unlocked", confirm=True),
             "payload_on": "LOCKED", "payload_off": "UNLOCKED", "state_topic": _t(d, "lock", "lock"),
             "command_topic": _t(d, "lock", "lock", "command")},
            {"kind": "sensor_text", "code": "door", "label": "Door", "ro": True, "state_topic": _t(d, "text_sensor", "door")},
            _sens(d, "battery", "Battery", "%")]}
    if t == "relay":
        return {**base, "category": "switch", "controls": [_sw(d, "power", "power", "Power")]}
    if t == "heater":
        return {**base, "category": "switch", "controls": [
            _sw(d, "power", "power", "Power"), _sens(d, "watts", "Power draw", "W"),
            _sens(d, "water_temp", "Water temperature", "\u00b0C")]}
    if t == "meter":
        return {**base, "category": "sensor", "controls": [
            _sens(d, "power", "Power", "W"), _sens(d, "energy", "Energy today", "kWh"), _sens(d, "voltage", "Voltage", "V")]}
    raise ValueError(f"no generic kind {t}")


def mqtt_devices() -> list:
    """mqtt_devices.json of the demo house (the IR blaster is the IR plug-in's, not a device here)."""
    return [esp_entry(d) for d in catalog.DEVICES if d["via"] == "esp" and d["type"] != "blaster"]
