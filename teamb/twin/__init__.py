"""Digital twin: a FastAPI server that steps one live SimEnv and a 3D web app that draws it.

    python -m teamb twin            # http://127.0.0.1:8000

- `session.py`  the one live simulation, stepped on its own thread (all TraCI calls live there)
- `server.py`   HTTP + WebSocket API, static web app, signal-data router for navigation apps
- `meta.py`     what the UI can offer: controllers, scenarios, closable roads, EV routes, attack targets
- `static/`     the web app (three.js, plain ES modules, no build step)

See docs/roles/twin.md for how it fits together and how to extend it.
"""
from __future__ import annotations


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    from teamb.twin.server import main as _main

    _main(host=host, port=port)
