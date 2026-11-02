#!/bin/sh
# export.sh <engine checkout> <demo checkout> <run dir>: the code the demo runs: the engine at the commit the demo
# pins (its ENGINE file) without tests, docs, examples, the host helper and every plug-in the demo keeps off, and the
# demo's HEAD (DEMO_DIRTY=1: its tracked changes too, for a try before the commit) as plugins-extra/demo.
# The run dir keeps demo.env.
set -eu
eng=$1 src=$2 run=$3
# one deploy at a time, and the watchdog keeps off while it runs (watchdog.sh takes the same lock)
lock="$run/.deploy.lock"
[ -e "$lock" ] || : > "$lock"
exec 9<"$lock"
flock -w "${DEMO_LOCK_WAIT:-600}" 9 || { echo "another deploy or the watchdog holds $lock"; exit 4; }
keep="transports/zigbee transports/ir devices/climate devices/tv devices/panels sources/presence tools/map tools/history tools/watchdog tools/stats"
pin=$(tr -d ' \n' < "$src/ENGINE")
esha=$(git -C "$eng" rev-parse "$pin^{commit}") || { echo "the engine checkout has no $pin (fetch it first)"; exit 5; }
sha="engine $esha + demo $(git -C "$src" rev-parse HEAD)"
echo "exporting $sha"
if [ "${DEMO_DIRTY:-}" != 1 ] && [ "$(cat "$run/app/COMMIT" 2>/dev/null)" = "$sha" ]; then
    echo "already live: $sha (bring the checkouts up to date first)"; exit 3
fi
new="$run/app.new"
rm -rf "$new" && mkdir -p "$new"
ref=HEAD
[ "${DEMO_DIRTY:-}" != 1 ] || ref=$(git -C "$src" stash create) || true
[ -n "$ref" ] || ref=HEAD
git -C "$eng" archive "$esha" | tar -x -C "$new"
mkdir -p "$new/plugins-extra/demo"
git -C "$src" archive "$ref" demo | tar -x -C "$new/plugins-extra/demo" --strip-components=1
{ echo "$sha"; [ "$ref" = HEAD ] || echo "with local changes"; } > "$new/COMMIT"
rm -rf "$new/tests" "$new/docs" "$new/examples" "$new/helper" "$new/config" "$new/.github" "$new/plugins/_example"
for p in "$new"/plugins/*/*/; do
    rel=${p#"$new/plugins/"}; rel=${rel%/}
    case " $keep " in *" $rel "*) ;; *) rm -rf "$p" ;; esac
done
rm -rf "$run/app.old" && { [ ! -d "$run/app" ] || mv "$run/app" "$run/app.old"; } && mv "$new" "$run/app"
echo "exported $(cat "$run/app/COMMIT") to $run/app"
# the broker's password file, from demo.env (MQTT_USER, MQTT_PASSWORD)
[ ! -f "$run/demo.env" ] || python3 "$run/app/plugins-extra/demo/setup/mqtt_passwd.py" "$run/demo.env" "$run/mosquitto.passwd"
# the containers mount app/ by its path at their creation: a new app/ needs them created again
if [ -f "$run/demo.env" ] && docker compose -p yashome-demo ps -q 2>/dev/null | grep -q .; then
    docker compose -p yashome-demo --env-file "$run/demo.env" -f "$run/app/plugins-extra/demo/setup/compose.demo.yml" up -d --build --force-recreate
fi
