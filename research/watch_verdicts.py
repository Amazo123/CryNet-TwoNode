#!/usr/bin/env python3
"""Follow a capture and print only the moments that matter.

The capture writes every line of every board; this prints the hub's
cry verdicts, the wearable's alerts and any clipping, so a test that is
happening in the room can be watched without reading the raw logs.

Usage:
    python research/watch_verdicts.py --dir research/out/capture_20261106_181058
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

HUB = re.compile(r"node (\d): .*P\(cry\)=([0-9.]+)|link: node (\d): (cry|no cry)|"
                 r"CLIPPED|alert|ALERT|test alert", re.IGNORECASE)
WEAR = re.compile(r"ALERT|alert|mask 0x|haptic|cry", re.IGNORECASE)


def follow(path: Path, pattern: re.Pattern[str], label: str) -> None:
    """Print matching lines from a growing file."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, 2)          # start at the end: only what happens now
        while True:
            line = fh.readline()
            if not line:
                time.sleep(0.4)
                continue
            if pattern.search(line):
                print(f"{label} {line.rstrip()}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--seconds", type=float, default=1800.0)
    args = ap.parse_args()

    d = Path(args.dir)
    end = time.time() + args.seconds
    import threading
    for name, pattern, label in (
        ("hub_COM32.log", HUB, "HUB  "),
        ("wearable_COM30.log", WEAR, "WEAR "),
    ):
        t = threading.Thread(target=follow, args=(d / name, pattern, label),
                             daemon=True)
        t.start()
    while time.time() < end:
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
