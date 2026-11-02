#!/bin/sh
# run_tests.sh <engine checkout> [pytest args]: the demo's tests in a throwaway engine tree at the ENGINE pin, the demo where
# the engine's test harness loads plug-ins (plugins/tools/demo) and its tests beside the engine's (tests/plugins).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
eng=$1; shift
pin=$(tr -d ' \n' < "$here/ENGINE")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git -C "$eng" archive "$pin" | tar -x -C "$tmp"
mkdir -p "$tmp/plugins/tools/demo"
cp -r "$here/demo/." "$tmp/plugins/tools/demo/"
cp "$here"/tests/test_demo*.py "$tmp/tests/plugins/"
cd "$tmp" && "${PYTHON:-python3}" -m pytest -q -p no:cacheprovider "$@" tests/plugins/test_demo.py tests/plugins/test_demo_sim.py tests/plugins/test_demo_playground.py tests/plugins/test_demo_map_labels.py
