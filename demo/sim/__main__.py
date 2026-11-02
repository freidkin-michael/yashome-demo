"""The demo simulator: `python -m plugins.tools.demo.sim` (container demo-sim). It plays zigbee2mqtt and the
ESPHome nodes of the catalog on the broker, steps the world every 2 s and publishes what changed.
demo/reset: every retained topic is cleared, the world starts again, demo/reset/done answers.
demo/sim/speed (1, 10, 60), demo/sim/weather (clear, cloudy, rain, heatwave), demo/sim/event (world.event),
demo/sim/move ("Alex=kitchen", "Alex=" for out); demo/sim/state (retained) says time, speed, weather and who is where."""
import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt

from . import catalog, devices, world

log = logging.getLogger("demo-sim")
NS = "zigbee2mqtt"
TICK_S = 2.0
REPORT_S = 20.0
_IR_NODE = devices.node(catalog.by_id()["living_ir"])


class Sim:
    def __init__(self, cli):
        self.cli, self.lock = cli, threading.RLock()
        self.w = world.World()
        self.sent: dict = {}          # topic -> last payload published
        self.esp_topics = self._esp_topics()

    def _esp_topics(self) -> dict:
        """command topic -> (device id, code) and code -> state topic, from the mqtt_devices.json entries."""
        cmd, state = {}, {}
        for e in devices.mqtt_devices():
            for c in e["controls"]:
                if c.get("command_topic"):
                    cmd[c["command_topic"]] = (e["id"], c["code"])
                if c.get("state_topic"):
                    state[(e["id"], c["code"])] = c["state_topic"]
        return {"cmd": cmd, "state": state}

    def pub(self, topic, payload, retain=True, force=False):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, separators=(",", ":"))
        payload = str(payload)
        if not force and self.sent.get(topic) == payload:
            return
        self.sent[topic] = payload
        self.cli.publish(topic, payload, retain=retain)

    def publish_all(self, force=False):
        with self.lock:
            if force:
                self.pub(f"{NS}/bridge/state", {"state": "online"}, force=True)
                self.pub(f"{NS}/bridge/devices", devices.bridge_devices(), force=True)
                self.pub(f"{_IR_NODE}/status", "online", force=True)
            for d in catalog.DEVICES:
                self.publish_device(d, force)
            for did, payload in self.w.events:
                if did == "presence":
                    self.cli.publish("presence/event", payload["event"])
                else:
                    self.cli.publish(f"{NS}/{did}", json.dumps(payload))
            self.w.events.clear()
            self.pub("presence/state", "ON" if any(self.w.where.values()) else "OFF", force=force)
            self.pub("demo/sim/state", world.summary(self.w), force=force)

    def publish_device(self, d, force=False):
        did, st = d["id"], self.w.state[d["id"]]
        online = self.w.online.get(did, True)
        if d["via"] == "z2m":
            self.pub(f"{NS}/{did}/availability", {"state": "online" if online else "offline"}, force=force)
            if st:
                self.pub(f"{NS}/{did}", st, force=force)
            return
        if d["type"] == "blaster":
            return
        node = devices.node(d)
        self.pub(f"{node}/status", "online" if online else "offline", force=force)
        if not online:
            return
        for code, v in st.items():
            topic = self.esp_topics["state"].get((did, code))
            if topic:
                self.pub(topic, v, force=force)

    # ---- incoming ----
    def on_message(self, _cli, _ud, msg):
        try:
            self._handle(msg.topic, msg.payload.decode("utf-8", "replace"), msg.retain)
        except Exception as e:                       # noqa: BLE001  one bad message must not stop the flat
            log.warning(f"{msg.topic}: {e!r}")

    def _handle(self, topic, payload, retain):
        if retain:
            return
        parts = topic.split("/")
        with self.lock:
            if parts[0] == NS and len(parts) == 3 and parts[2] in ("set", "get"):
                d = self.w.cat.get(parts[1])
                if d is None:
                    return
                if parts[2] == "set":
                    self.w.command(parts[1], json.loads(payload or "{}"))
                self.publish_device(d, force=True)
            elif topic in self.esp_topics["cmd"]:
                did, code = self.esp_topics["cmd"][topic]
                self.w.command(did, {code: payload})
                self.publish_device(self.w.cat[did], force=True)
            elif topic.startswith(f"{_IR_NODE}/tx/"):
                log.info(f"IR sent: {payload[:40]}")
            elif topic == "demo/sim/speed":
                self.w.set_speed(int(float(payload)))
                self.publish_all()
            elif topic == "demo/sim/weather":
                self.w.set_weather(payload.strip())
                self.publish_all()
            elif topic == "demo/sim/move":
                who, _, room = payload.partition("=")
                self.w.move(who.strip(), room.strip() or None)
                self.publish_all()
            elif topic == "demo/sim/event":
                self.w.event(payload.strip())
                self.publish_all()
            elif topic == "demo/reset":
                self.reset()

    def reset(self):
        """Clear every retained topic of the broker, start the world again, then say so."""
        seen = set()
        probe = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"demo-sim-sweep-{os.getpid()}")
        if os.environ.get("MQTT_USER"):
            probe.username_pw_set(os.environ["MQTT_USER"], os.environ.get("MQTT_PASSWORD", ""))
        probe.on_message = lambda _c, _u, m: seen.add(m.topic) if m.retain and m.payload else None
        probe.connect(os.environ.get("MQTT_HOST", "mosquitto"), int(os.environ.get("MQTT_PORT", "1883")))
        probe.subscribe("#")
        probe.loop_start()
        time.sleep(1.5)
        probe.loop_stop()
        probe.disconnect()
        alive = {f"{NS}/bridge/state", f"{_IR_NODE}/status"}      # never cleared: an empty one reads as offline
        for t in sorted(seen):
            if not t.startswith("$") and t not in alive:
                self.cli.publish(t, b"", retain=True)
        self.w = world.World()
        self.sent.clear()
        self.publish_all(force=True)
        self.cli.publish("demo/reset/done", str(len(seen)))
        log.info(f"reset: {len(seen)} retained topics cleared")

    def on_connect(self, cli, _ud, _flags, rc, _props=None):
        log.info(f"broker: {rc}")
        cli.subscribe([(f"{NS}/+/set", 0), (f"{NS}/+/get", 0), (f"{_IR_NODE}/tx/+", 0), ("demo/reset", 0), ("demo/sim/+", 0)]
                      + [(t, 0) for t in self.esp_topics["cmd"]])
        self.publish_all(force=True)

    def run(self):
        last = report = time.monotonic()
        while True:
            time.sleep(TICK_S)
            now = time.monotonic()
            with self.lock:
                self.w.step((now - last) * self.w.speed)
                self.publish_all()
                if now - report >= REPORT_S:          # every device reports now and then, as real ones do: a backend
                    report = now                      # that just started knows each sensor's live value, so the first
                    for d in catalog.DEVICES:         # change after it (an opened window) fires its rules
                        self.publish_device(d, force=True)
            last = now


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="demo-sim")
    sim = Sim(cli)
    cli.on_connect, cli.on_message = sim.on_connect, sim.on_message
    cli.will_set(f"{NS}/bridge/state", json.dumps({"state": "offline"}), retain=True)
    if os.environ.get("MQTT_USER"):
        cli.username_pw_set(os.environ["MQTT_USER"], os.environ.get("MQTT_PASSWORD", ""))
    cli.connect(os.environ.get("MQTT_HOST", "mosquitto"), int(os.environ.get("MQTT_PORT", "1883")))
    cli.loop_start()
    sim.run()


if __name__ == "__main__":
    main()
