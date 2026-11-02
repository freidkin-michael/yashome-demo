#!/bin/sh
# watchdog.sh <run dir> (root, every minute from yashome-demo-watchdog.timer): the firewall rules are in place,
# every service of the demo runs (started again after a reboot or a crash), and the edge answers.
set -u
run=$1
cd "$run" || exit 1
# an export holds this lock from its first write to its `up -d`: nothing of the stack is judged meanwhile
[ -e .deploy.lock ] || : > .deploy.lock
exec 9<.deploy.lock
flock -n 9 || { echo "watchdog: an export runs: skipped"; exit 0; }
sh app/plugins-extra/demo/setup/firewall.sh "$run/demo.env" || echo "watchdog: firewall failed"
dc="docker compose -p yashome-demo --env-file $run/demo.env -f $run/app/plugins-extra/demo/setup/compose.demo.yml"
# a container that runs older code (app/ was exported again) or an older image is created again
code=$(cat "$run/app/COMMIT" 2>/dev/null | head -1)
img=$(docker image inspect -f '{{.Id}}' yashome-demo-home:local 2>/dev/null)
for c in home sim; do
    id=$($dc ps -q "$c" 2>/dev/null)
    [ -n "$id" ] || continue
    if [ "$(docker exec "$id" head -1 /app/COMMIT 2>/dev/null)" != "$code" ] || [ "$(docker inspect -f '{{.Image}}' "$id")" != "$img" ]; then
        echo "watchdog: $c runs stale code or image: recreate"
        $dc up -d --force-recreate >/dev/null 2>&1 || echo "watchdog: recreate failed"
        sh app/plugins-extra/demo/setup/firewall.sh "$run/demo.env" || true
        break
    fi
done
want=$($dc config --services | sort | tr '\n' ' ')
have=$($dc ps --status running --services | sort | tr '\n' ' ')
if [ "$want" != "$have" ]; then
    echo "watchdog: running [$have] of [$want]: up -d"
    $dc up -d >/dev/null 2>&1 || echo "watchdog: up -d failed"
    sh app/plugins-extra/demo/setup/firewall.sh "$run/demo.env" || true
fi
. "$run/demo.env"
curl -s -m 5 -o /dev/null "http://$DEMO_BIND:${DEMO_PORT:-8780}/try" || echo "watchdog: the edge does not answer"
