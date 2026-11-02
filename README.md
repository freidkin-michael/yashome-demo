# Yashome demo

The public demo of Yashome (a fictional flat, a simulator, one guest at a time, the next ones in line) as a plug-in of the engine.
The plug-in itself and its own documentation: [demo/README.md](demo/README.md).

- `ENGINE`: the engine commit (or tag) the demo runs on. The demo is deployed and tested on exactly that.
- `make test ENGINE=<engine checkout>`: the demo's tests in a throwaway engine tree at that commit.
- Deploy: `demo/setup/export.sh <engine checkout> <demo checkout> <run dir>`: the engine at the pin plus this repository's
  `demo/` as `plugins-extra/demo`, then the compose project is created again (one deploy at a time).
- The engine runs it in restricted mode (`YASHOME_RESTRICTED=1`): only the routes `demo/routes.py` lists.
