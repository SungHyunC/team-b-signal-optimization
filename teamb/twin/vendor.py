"""Download the pinned three.js files for offline demos.

    python -m teamb.twin.vendor

The web app loads three.js through /vendor/three/..., which the server answers with a local copy
from teamb/twin/static/vendor/three@<version>/ when it exists and otherwise redirects to the
pinned CDN. Run this once on the presentation laptop so the twin works without venue Wi-Fi.
"""
from __future__ import annotations

import sys
import urllib.request

from teamb.twin.server import THREE_CDN, VENDOR_DIR

FILES = (
    "build/three.module.js",
    "examples/jsm/controls/OrbitControls.js",
    "examples/jsm/utils/BufferGeometryUtils.js",
)


def main() -> int:
    for rel in FILES:
        target = VENDOR_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(THREE_CDN + rel, timeout=30) as response:
            data = response.read()
        target.write_bytes(data)
        print(f"{rel:45s} {len(data) / 1024:8.1f} KiB")
    print(f"saved to {VENDOR_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
