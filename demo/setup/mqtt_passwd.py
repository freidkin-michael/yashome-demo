"""mqtt_passwd.py <demo.env> <out file>: the demo broker's password file (mosquitto's PBKDF2-SHA512 format) for its one
account, MQTT_USER / MQTT_PASSWORD of demo.env, written with mode 600. Nothing else may use the broker."""
import base64
import hashlib
import os
import sys

env = dict(ln.split("=", 1) for ln in open(sys.argv[1], encoding="utf-8").read().splitlines() if "=" in ln and not ln.startswith("#"))
user, pw = env.get("MQTT_USER", "demo"), env.get("MQTT_PASSWORD", "")
if len(pw) < 16:
    sys.exit("MQTT_PASSWORD in demo.env: 16 characters or more")
salt = os.urandom(12)
digest = hashlib.pbkdf2_hmac("sha512", pw.encode(), salt, 101)
line = f"{user}:$7$101${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}\n"
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(line)
