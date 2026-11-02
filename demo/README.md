# demo - the public demo of Yashome

A fictional three-room flat with simulated devices, run by the same code as a real house. It works only with
`YASHOME_RESTRICTED=1` (the core's restricted mode); in any other house the plug-in refuses every sign-in.

## What demo mode does

- **Only listed routes run.** `routes.py` names every route of every shipped plug-in: `VIEW` (anyone signed in
  reads, a guest in line too), `CONTROL` (only the guest in control: everything an owner does with the house's own data, names,
  rooms, the map, wiring, IR remotes, rules; the reset takes it back) or `REFUSED`, by group with its reason
  (uploads, firmware, pairing, backups, the helper, anything that reaches the LAN or the internet, the API docs,
  the routes of plug-ins the demo keeps off). A name may not hold a link, an e-mail address or a phone number. The core answers 403 "Not available here" to anything else, a route added later included.
  `tests/plugins/test_demo.py` fails on a route in none of the lists and sends every refused one with the
  controller's token.
- **Bounded input.** A body over 64 KB is refused before it is read; `limits.check` bounds what a guest stores:
  a favourite's name (24 characters), rule conditions (5), the core's own rule actions only, orders and tile
  scopes of known names, a control `{code, value}`.
- **One guest at a time.** The shared demo password (`DEMO_PASSWORD`, no name: one field) signs a browser in and
  takes the flat: control from the first second when it is free, else a place in line with a worst-case wait
  (the page enters by itself when the turn comes). A sign-in that can have neither is refused and makes no
  session. A turn lasts at most 15 min, ends after 3 min without an action, and a closed tab (no heartbeat for
  30 s) frees it. One turn or place in line per network (an IPv4 /24, an IPv6 /48); after a turn, that
  network waits 15 min while others want one. After a turn the session stays signed in, out of turn: "Get in
  line again" at most once in 2 min.
- **A reset after every turn that did something** (a turn under 30 s with no action needs none): the plug-in
  asks the simulator to clear every retained topic of the broker (`demo/reset`, answered on `demo/reset/done`),
  then the backend exits; Docker starts it again and `entry.py` copies `house/` over the house directory, byte
  for byte (its log line `[demo] house seeded <hash>`): settings, rules, history and stats databases, the status
  cache. The event feed lives in memory and starts empty. When the simulator did not answer before the exit,
  the restart asks it again (3 times at most). The next in line gets the flat only after that restart, on the
  pristine house. At most one reset in 2 min: the next in line waits for it. The guest in control may also
  reset once a turn (the page asks first).
- **Sign-in limits.** Per address (IPv4, IPv6 /64): 5 failures, 20 tries and 10 new sessions in 10 min; per
  network (IPv4 /24, IPv6 /48) 20 failures; while 50 networks fail (and 5 min after), 2 failures per network:
  a network that did not fail still signs in. The address
  is the `X-Forwarded-For` of the demo's own proxy (`DEMO_EDGE_IP`); a request from anywhere else is refused
  (503). When the demo is full, the longest idle session out of turn goes, never the guest in control, one in line
  or one whose tab beat in the last 30 s (then a new sign-in gets 503). The log and the lease keep no address, only
  salted hashes: the backend writes no access log, the edge's names no client and no query string (`/ws?token=`).
  One turn or place in line per network; at most 20 in line whose tab beat in the last 90 s (a silent one keeps
  its place but fills none).
- **Only the guest in control is the owner.** A session in line or out of turn passes the house's owner checks only
  on `VIEW` routes (the map); the history and the health page are the guest in control's. A session holds at most 3 WebSockets.
  The guest in control writes at most 2 changes a second; a rule starts at a sensor or a button only (no rule can
  start another), and a rule that repeats is one line of the feed.
- **English only**: the house languages are `["en"]` and the page drops every other dictionary.
- **Nothing refused is offered.** `static/greyed.json` lists the page's controls whose route is REFUSED (a test
  checks each): greyed with "Not available in demo" (Add device; in Settings the
  Forgotten tab, Zigbee pairing, connecting, building and deleting panels; the engine greys the other refused
  pages and tabs by their own needs) or hidden (the Zigbee
  rename, IR learning and blasters). The map is the owner's for the guest in control (drag, the
  long-press menu, a thing's sheet, walls and openings). Icons and room names are bigger, for a phone.

## The guest's page

- **Out of turn, a page of its own over the house** (the house never shows): in line, "Demo is busy", "Free in
  about 12 min" (counting down), the place in line and "Leave the line"; the page beats every 3 s and opens the
  flat by itself when the turn comes. After a turn: the summary (minutes, actions, rules fired, things tried),
  the feedback link (`DEMO_FEEDBACK_URL`), "Get in line again" and "Sign out".
- **The header pill** (in control): "You are in control 12:31" with Reset (asks first) and Release; "Still
  there?" in the last minute before the idle limit. On a narrow screen: the logo, the pill and a menu (History,
  Health, Reset); bottom tabs Map / Devices.
- **The first turn**: the intro (how the flat was set up, on a copy of its map), or 20 s of captions that point at
  the flat (nothing is switched); Skip ends it.
- **Simulate**: the flat's time and weather; for the guest in control the speed (x1, x10, x60), the weather,
  events (doorbell, window, leak, smoke) and where each resident is; six things to try that tick themselves.
- **When a rule fires**: a toast, the devices it touched light up on the map, and a line in "What happened"
  (`GET /api/demo/feed`: the rules, schedules and the guest's own commands).
- **Settings are open to look at** (the gear; on a narrow screen in the menu): every page starts with a box that
  says what it does, why a house needs it and what the demo lets you do there (`WHY` in `ui.js`). A page whose
  routes are refused is greyed by the engine ("Not available here"), its box still explains it; changes that the
  routes allow are real for the turn and go back at the reset.
- **Ask**: example questions, not available in the demo (the house's language model is left out).
- **The showcase** (`/showcase`, no sign-in): the map picture and a 30 s film (`DEMO_STATE_DIR/showcase/map.png`,
  `tour.webm`, made from the running demo) and "Try it yourself".

## The flat

`sim/catalog.py` is the one list of the flat: 42 devices in six rooms (Zigbee through zigbee2mqtt topics,
ESPHome-style nodes, an IR blaster) and the loads they switch. `sim/seedgen.py` writes `house/` from it
(devices, rooms, rules, favourites, the map and its drawing); a test fails when they differ:
`cd plugins-extra/demo && python -m sim.seedgen`. The simulator (`python -m sim`, container `sim`) plays every
device on the broker and steps a small model: sun and weather, each room's temperature, humidity, light and CO2,
the power of every load, three residents moving through a day. `demo/sim/speed` (1, 10, 60), `demo/sim/weather`
(clear, cloudy, rain, heatwave) and `demo/sim/event` (leak, smoke, doorbell, window_open...) steer it.

## Running it

On the demo host (Docker), with a checkout of the house's branch:

    setup/export.sh <engine> <demo> <run dir>  # the engine at ENGINE without tests, docs and the plug-ins kept off, + demo/;
                                              # a running demo is created again on it (the containers mount app/ by path)
    cp setup/demo.env.example <run dir>/demo.env   # then fill it in, mode 600
    docker compose -p yashome-demo --env-file <run dir>/demo.env -f <run dir>/app/plugins-extra/demo/setup/compose.demo.yml up -d --build
    sudo setup/firewall.sh <run dir>/demo.env  # the port answers the front proxy only; the edge starts no connection
    python3 setup/live_check.py <run dir>      # a real turn and reset, refusals through the edge, isolation
    <repo venv>/python setup/ui_check.py <run dir>   # the map at 390 and 1280 px: room names off icons, inside their rooms
    ssh <real house host> 'python3 house_words.py <house dir> <.env>' | python3 setup/leak_scan.py --names-not-in=i18n.js,i18n.json --generic=bedroom <run dir>/app <run dir>/state image:yashome-demo-home:local

("bedroom" is a room of the real house and of the demo flat alike: a generic word, not a leak.)

The backend, the broker (one account, `MQTT_USER` / `MQTT_PASSWORD`) and the simulator sit on an internal network
(no LAN, no internet, no host port); the edge (unprivileged nginx) is the only published port. Every container runs
read-only, without capabilities or new privileges, with a process cap. The edge limits each address to 10 API
requests a second (burst 30), 1 sign-in a second and 20 connections; WebSocket upgrades only on `/ws`.

**The front proxy** (in front of the edge, the only host the firewall lets in: `DEMO_PROXY_IP`) must set
`X-Real-IP` to the guest's address, overwriting any value the client sent (nginx: `proxy_set_header X-Real-IP
$remote_addr;` after its own real-IP step); the edge believes that header from `DEMO_PROXY_IP` only and ignores
`X-Forwarded-For`. `setup/watchdog.sh` (a systemd timer, `setup/yashome-demo-watchdog.*`)
brings the stack back after a reboot, keeps the firewall rules and creates a container again that runs older code
or an older image than the run dir holds.

## Files

| file | what |
|---|---|
| `__init__.py` | sign-in, the lease routes `/api/demo/*`, the sign-in page `/try`, the reset |
| `routes.py`, `limits.py` | the route lists; the sign-in limiter and the checks of what a guest stores |
| `lease.py` | sessions and the turn (pure, tested with a fake clock); kept in `DEMO_STATE_DIR` (hashes only) |
| `seed.py`, `entry.py` | the pristine house and the backend's command in the demo |
| `house/` | the demo house, written by `sim/seedgen.py` |
| `sim/` | the catalog, the wire formats, the model and the simulator |
| `ui.js` | the guest's page: the waiting page and the summary out of turn; in control the pill, bottom tabs, Simulate, Ask, toasts, map highlights, the intro |
| `static/` | the sign-in page, the showcase page, `greyed.json` |
| `setup/` | compose, the edge and broker configuration, export, firewall, watchdog, live check, leak scan |

## Keys

| key | what |
|---|---|
| `YASHOME_RESTRICTED` | `1` turns the core's restricted mode on (the older `YASHOME_DEMO` too) |
| `DEMO_PASSWORD` | the shared password (there is no name); none = nobody signs in |
| `DEMO_STATE_DIR` | where the backend keeps the lease across resets (`DEMO_STATE_HOST` on the host, a directory of uid 1000) |
| `DEMO_EDGE_IP`, `DEMO_INT_SUBNET` | the edge proxy's fixed address on the internal network, and that network |
| `DEMO_FEEDBACK_URL` | the link of the end-of-session summary (none: no link) |
| `DEMO_HOST` | the public name of the demo (the backend accepts browser requests from it) |
| `DEMO_BIND`, `DEMO_PORT`, `DEMO_PROXY_IP` | where the edge listens on the host, and the one front proxy the firewall lets in |
| `DEMO_RUN` | the run dir, for the watchdog's systemd unit (`/etc/yashome-demo.conf`) |
| `DEMO_DIRTY` | `setup/export.sh` takes the checkout's tracked changes too (a try before the commit) |
