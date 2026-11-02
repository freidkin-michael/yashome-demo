# demo - the public demo of Yashome

A fictional flat of six rooms with simulated devices, run by the same code as a real house. It works only with
`YASHOME_RESTRICTED=1` (the engine's restricted mode); in any other house the plug-in refuses every sign-in.
Paths below are inside `demo/` unless they start with `tests/` (the repository's tests).

## What demo mode does

- **Only listed routes run.** `routes.py` names every route of every shipped plug-in: `VIEW` (anyone signed in,
  a guest in line too), `CONTROL` (only the guest in control: everything an owner does with the house's own data,
  names, rooms, the map, wiring, IR remotes, rules, the playground panel, the history; the reset takes it back) or
  `REFUSED`, by group with its reason (uploads, backups, firmware and builds, pairing, the helper, voice, the family
  app, the house's computers and players, NFC cards, the API docs, the routes of plug-ins the demo keeps off).
  The engine answers 403 "Not available here" to any route not in `VIEW` or `CONTROL`, a route added later included,
  and 403 "Not yet: wait for your turn" to a `CONTROL` route from a session that is not in control.
  `tests/test_demo.py` fails on a route in none of the lists and sends every refused one with the controller's token.
- **Bounded input.** The engine refuses a body over 64 KB before it is read (413). `limits.check` bounds what a
  guest stores: a control is `{code, value}`; a favourite's name is up to 24 letters, digits and spaces; a rule
  starts at a sensor or a button, uses the core's own actions only (on, off, toggle, brighter, darker, press) and
  has at most 5 conditions; a schedule has at most 8 times a day; orders and tile sizes name known devices, tabs
  and rooms only; other bodies are at most 2 KB, except whole documents (the map, its rooms and zones, wiring).
  No name may hold a link, an e-mail address or a phone number. The guest in control writes at most 2 changes a
  second (a burst of 6).
- **One guest at a time.** The shared demo password (`DEMO_PASSWORD`, no name: one field) signs a browser in and
  takes the flat: control at once when it is free, else a place in line with a worst-case wait (the page enters by
  itself when the turn comes). A sign-in that can have neither is refused and makes no session.
  A turn lasts at most 15 min and ends after 3 min without an action ("Still there?" in the last minute).
  A tab beats every 9 s in control and every 3 s in line. A closing page sends a goodbye; unless it beats again
  within 30 s (a reload), its turn or place ends. A hidden tab keeps its turn until the idle limit.
  A place in line whose tab was not heard for 3 min is skipped; a session out of turn not seen for 10 min is
  signed out.
- **One turn or place in line per network** (an IPv4 /24, an IPv6 /48). After a turn, that network waits 15 min
  while others want one. After a turn the session stays signed in, out of turn: "Get in line again" at most once in
  2 min. At most 20 in line whose tab beat in the last 90 s (a silent one keeps its place but fills none).
- **A reset after every turn that did something** (a turn under 30 s with no action needs none): the plug-in
  asks the simulator to clear every retained topic of the broker (`demo/reset`, answered on `demo/reset/done`),
  then the backend exits. Docker starts it again and `entry.py` empties the house directory and copies `house/`
  into it, byte for byte (log line `[demo] house seeded <hash> (seed <hash>)`): whatever the guest changed
  (settings, rules, history and stats databases, the status cache) is gone. The event feed lives in memory and
  starts empty. When the simulator did not answer before the exit, the restart asks it again (3 times at most).
  The next in line gets the flat only after that restart, on the pristine house. At most one reset in 2 min: the
  next in line waits for it. The guest in control may also reset once a turn (the page asks first).
- **Sign-in limits.** Per address (IPv4, IPv6 /64): 5 failures, 20 tries and 10 new sessions in 10 min. Per
  network (IPv4 /24, IPv6 /48): 20 failures. While 50 networks fail (and 5 min after): 2 failures per network, so a
  network that did not fail still signs in. The address is the `X-Forwarded-For` set by the demo's own edge proxy
  (`DEMO_EDGE_IP`); a sign-in that comes from anywhere else is refused (503). When the demo is full (300
  sessions), the longest idle session out of turn goes: never the guest in control, one in line or one whose tab
  beat in the last 30 s (if none can go, the new sign-in gets 503).
- **No addresses kept.** The lease and the log keep only salted hashes. The backend writes no access log; the
  edge's access log has no client address and no query string (`/ws?token=` holds a session token).
- **Only the guest in control is the owner.** A session in line or out of turn passes the house's owner checks
  only on `VIEW` routes; the history and the health page are the guest in control's. A session holds at most 3
  WebSockets. A rule that repeats is one line of the feed. Nobody holds the house token: `entry.py` sets a random
  one at each start.
- **English only**: in restricted mode the engine offers only `en`, drops every other dictionary and hides the
  language button.
- **Nothing refused is offered.** `static/greyed.json` lists the page's controls whose route is `REFUSED` (a test
  checks each): greyed with "Not available in demo" (Add device; in Settings the Forgotten tab, Zigbee pairing,
  panel pairing, starter firmware, building the launcher, deleting panels) or hidden (the Zigbee rename, IR
  learning and blasters). The engine greys the other refused Settings pages by the routes they need. For the guest
  in control the map is the owner's (drag, the long-press menu, a thing's sheet, walls and openings); in restricted
  mode the engine draws the map's labels at phone size and hides the underlay picture.
- **The playground panel.** The panel builder offers one panel, `playground`: an Android tablet without status
  bar buttons, at most 40 widgets and 32 KB, bound only to the flat's devices and topics. It cannot be renamed,
  deleted or built, and goes back at the reset.
- **Weather and a camera from the simulator.** The weather and cameras plug-ins are off in the demo; the plug-in
  answers `/api/weather` (an Open-Meteo-shaped forecast from the simulator's day) and `/api/cameras` with one
  drawn balcony camera whose sky follows the simulator's clock and weather.

## The guest's page

- **Out of turn, a page of its own over the house** (the house never shows): in line, "Demo is busy" (or "The
  flat is being reset"), "Free in about 12 min", the place in line and "Leave the line"; the page opens the flat
  by itself when the turn comes. After a turn: why it ended, the summary (minutes, actions, rules fired, things
  tried), the feedback link (`DEMO_FEEDBACK_URL`), "Get in line again" and "Sign out".
- **The header pill** (in control): Intro (replays it), "You are in control 12:31", Reset (once a turn, asks
  first) and Release; "Still there?" with Yes and Release in the last minute before the idle limit. On a narrow
  screen: the pill and a menu (History, Health, Reset the flat, Settings); bottom tabs Map / Devices.
- **The first turn**: the intro (how the flat was set up, drawn on a copy of its map), or without it 20 s of
  captions that point at the flat (nothing is switched); Skip ends it.
- **Simulate** (the panel beside the map): seven things to try that tick themselves (a light, the bedroom AC, the
  front door lock, a window, the doorbell, a resident to the bathroom and back, dragging a device), the playground
  tablet ("See the tablet", "Shape it in the builder"), the speed (x1, x10, x60), the weather (clear, cloudy,
  rain, heatwave, back to normal), events (doorbell, window open and closed, a kitchen leak and smoke, each with
  its clear), and where each resident is.
- **When a rule fires**: a toast, the devices it touched light up on the map, and a line in "What happened"
  (`GET /api/demo/feed`: rules, schedules, timers and the guest's own commands).
- **Settings are open to look at** (in the menu): every page starts with a box that says what it does, why a house
  needs it and what the demo lets you do there (`WHY` in `ui.js`). A page whose routes are refused is greyed by
  the engine ("Not available here"), its box still explains it; changes that the routes allow are real for the
  turn and go back at the reset.
- **Ask**: example questions, answered from the flat as it is now; the language model is not connected.
- **The showcase** (`/showcase`, no sign-in): the map picture and a short film with "Try it yourself". The page
  serves `DEMO_STATE_DIR/showcase/map.png` and `tour.webm` when they are there (404 until then); nothing in this
  repository makes them.

## The flat

`sim/catalog.py` is the one list of the flat: 42 devices in six rooms (Zigbee devices on zigbee2mqtt topics,
ESPHome-style nodes, an IR blaster) and the 11 loads they switch; three fictional residents (Alex, Sam, Mia).
`sim/seedgen.py` writes `house/` from it (devices, rooms, rules, favourites, the map and its drawing, an IR ceiling
fan); `tests/test_demo_sim.py` fails when they differ. To write it again: `cd demo && python -m sim.seedgen`.
The simulator (`python -m sim`, container `sim`) plays every device on the broker, steps a small model every 2 s
(sun and weather, each room's temperature, humidity, light and CO2, the power of every load, the residents moving
through a day) and has every device report every 20 s. `demo/sim/speed` (1, 10, 60), `demo/sim/weather` (clear,
cloudy, rain, heatwave, auto), `demo/sim/event` (doorbell, leak, leak_dry, smoke, smoke_clear, window_open,
window_close) and `demo/sim/move` (`Alex=kitchen`, `Alex=` for out) steer it; `demo/sim/state` (retained) says
the time, speed, weather and who is where.

## Running it

On the demo host (Docker), from a checkout of this repository, with an engine checkout that has the `ENGINE` tag:

    mkdir -p <run dir> && cp demo/setup/demo.env.example <run dir>/demo.env   # fill it in, mode 600
    demo/setup/export.sh <engine> . <run dir>   # the engine at ENGINE + demo/; also writes the broker's password file
    docker compose -p yashome-demo --env-file <run dir>/demo.env -f <run dir>/app/plugins-extra/demo/setup/compose.demo.yml up -d --build
    sudo demo/setup/firewall.sh <run dir>/demo.env  # the port answers the front proxy only
    python3 demo/setup/live_check.py <run dir>      # a real turn and reset, refusals through the edge, isolation
    <venv>/python demo/setup/ui_check.py <run dir>  # the map at 390 and 1280 px: room names clear of icons and walls
    <on the real house host> python3 house_words.py <house dir> <.env> \
      | python3 demo/setup/leak_scan.py --names-not-in=i18n.js,i18n.json --generic=bedroom <run dir>/app <DEMO_STATE_HOST> image:yashome-demo-home:local

`demo.env` must exist before the export: `export.sh` writes `<run dir>/mosquitto.passwd` from its `MQTT_USER` /
`MQTT_PASSWORD` (16 characters or more). `export.sh` stops with exit 3 when that code is live already
(`DEMO_DIRTY=1` exports anyway). `ui_check.py` needs a Python with `websockets` and Chromium. `house_words.py`
lists the real house's names and secret values to a pipe (nothing on disk); `leak_scan.py` prints where a word,
a home LAN address or a real MAC address was found, never what. ("bedroom" is a room of the real house and of the
demo flat alike: a generic word, not a leak.)

The backend, the broker (one account, `MQTT_USER` / `MQTT_PASSWORD`, nothing kept on disk) and the simulator sit
on an internal network (no LAN, no internet, no host port); the edge (unprivileged nginx) has the only published
port. Every container runs with a read-only root, no capabilities, no new privileges, a process cap and a memory
cap. The house directory is a tmpfs. The edge limits each address to 10 API requests a second (burst 30),
1 sign-in a second (burst 3) and 20 connections; bodies up to 64 KB; WebSocket upgrades only on `/ws`.
`firewall.sh` also keeps every container of the demo from starting a connection out of its network or to the
host itself.

**The front proxy** (in front of the edge, the only host the firewall lets in: `DEMO_PROXY_IP`) must set
`X-Real-IP` to the guest's address, overwriting any value the client sent (nginx: `proxy_set_header X-Real-IP
$remote_addr;` after its own real-IP step); the edge believes that header from `DEMO_PROXY_IP` only.

`setup/watchdog.sh` runs every minute (the systemd timer `setup/yashome-demo-watchdog.timer`, the run dir in
`/etc/yashome-demo.conf` as `DEMO_RUN`): it applies the firewall rules, creates a container again that runs older
code or an older image than the run dir holds, starts any service that is down (after a reboot or a crash) and
checks that the edge answers. It skips a run while an export holds the run dir's lock.

## Files

| file | what |
|---|---|
| `__init__.py` | sign-in, the lease routes `/api/demo/*`, the sign-in page `/try`, the feed, the simulator routes, the demo's weather and camera, the showcase, the reset |
| `routes.py`, `limits.py` | the route lists; the sign-in limiter and the checks of what a guest stores |
| `lease.py` | sessions, the turn and the line (pure, tested with a fake clock); kept in `DEMO_STATE_DIR` (hashes only) |
| `seed.py`, `entry.py` | the pristine house and the backend's command in the demo |
| `house/` | the demo house, written by `sim/seedgen.py` |
| `sim/` | the catalog, the wire formats, the model, the weather day and the simulator |
| `ui.js` | the guest's page: the waiting page and the summary out of turn; in control the pill, bottom tabs, Simulate, Ask, toasts, map highlights, the intro |
| `static/` | the sign-in page, the showcase page, `greyed.json` |
| `setup/` | compose, the edge and broker configuration, export, firewall, watchdog and its systemd units, live check, UI check, leak scan |

## Keys

| key | what |
|---|---|
| `YASHOME_RESTRICTED` | `1` turns the engine's restricted mode on (`YASHOME_DEMO=1` too) |
| `DEMO_PASSWORD` | the shared password (there is no name); none = nobody signs in |
| `DEMO_STATE_DIR` | where the backend keeps the lease and the showcase files across resets (`DEMO_STATE_HOST` on the host, a directory of uid 1000) |
| `DEMO_EDGE_IP`, `DEMO_INT_SUBNET` | the edge proxy's fixed address on the internal network, and that network |
| `DEMO_FEEDBACK_URL` | the link of the end-of-session summary (none: no link) |
| `DEMO_HOST` | the public name of the demo (the backend accepts browser requests from it) |
| `DEMO_BIND`, `DEMO_PORT`, `DEMO_PROXY_IP` | where the edge listens on the host (port 8780 by default), and the one front proxy the firewall lets in |
| `MQTT_USER`, `MQTT_PASSWORD` | the broker's one account (the backend and the simulator) |
| `TZ` | the containers' time zone (UTC by default) |
| `DEMO_RUN` | the run dir, for the watchdog's systemd unit (`/etc/yashome-demo.conf`) |
| `DEMO_DIRTY` | `setup/export.sh` takes the checkout's tracked changes too (a try before the commit) |
| `DEMO_LOCK_WAIT` | how long `setup/export.sh` waits for the run dir's lock (600 s by default) |
