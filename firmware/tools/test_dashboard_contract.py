#!/usr/bin/env python3
"""Prove the hub and the dashboard agree, without any hardware.

The hub builds its upload body by hand with snprintf (ESP-IDF ships no
JSON library).  This script builds the *same* body, byte for byte, from
the same fields, posts it to a running dashboard, and checks that what
comes back out of the API is what went in.

That is the one contract in the system that no compiler checks: the
firmware and the page are written in different languages and a field
renamed on either side would fail silently -- the hub would report
success and the dashboard would show nothing.

    python firmware/tools/test_dashboard_contract.py
    python firmware/tools/test_dashboard_contract.py --port 8787 --token SECRET

It starts its own throwaway server on a free port unless you point it at
one, and it never writes inside the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "dashboard" / "server.py"

FW_VERSION = "2.0-dashboard"       # CRYNET_FW_VERSION in crynet_net.c


def hub_body(device: str, name: str, records: list[dict]) -> str:
    """Exactly what build_batch() in crynet_net.c produces.

    Keep this in step with that function.  The formatting is deliberate:
    %.4f for the levels, integers everywhere else, no spaces.
    """
    parts = []
    for r in records:
        dur_s = (r["duration_ms"] + 500) // 1000
        end = r["epoch_s"] + dur_s if r["epoch_s"] else 0
        parts.append(
            '{"seq":%d,"kind":"%s","cot":%d,'
            '"start":%d,"end":%d,"duration_s":%d,'
            '"peak_conf":%d,"windows":%d,'
            '"peak_rms":%.4f,"mean_rms":%.4f,'
            '"boot":%d,"uptime_ms":%d}'
            % (r["seq"], r["kind"], r["cot"], r["epoch_s"], end, dur_s,
               r["peak_conf"], r["windows"],
               r["peak_rms_milli"] / 1000.0, r["mean_rms_milli"] / 1000.0,
               r["boot_id"], r["uptime_ms"])
        )
    return ('{"device":"%s","hub":{"fw":"%s","name":"%s"},"events":[%s]}'
            % (device, FW_VERSION, name, ",".join(parts)))


def post(url: str, body: str, token: str) -> dict:
    req = urllib.request.Request(
        url, data=body.encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    if token:
        req.headers["X-CryNet-Token"] = token
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_up(base: str, proc=None, seconds: float = 20.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            raise SystemExit("the dashboard exited during startup")
        try:
            get(base + "/api/v1/health")
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    raise SystemExit("the dashboard did not come up")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=0,
                    help="an already-running dashboard; 0 starts a throwaway one")
    ap.add_argument("--token", default="")
    args = ap.parse_args()

    tmp = None
    proc = None
    port = args.port
    if port == 0:
        port = free_port()
        tmp = tempfile.TemporaryDirectory(prefix="crynet-contract-")
        db = Path(tmp.name) / "contract.db"
        cmd = [sys.executable, "-I", str(SERVER), "--port", str(port),
               "--host", "127.0.0.1", "--db", str(db)]
        if args.token:
            cmd += ["--token", args.token]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    failures = []

    try:
        wait_up(base, proc)

        # A night's worth of records, in the hub's own units.  Two cots,
        # a boot, a cot going deaf and coming back, and one record with
        # no clock at all -- the case the hub is in before it reaches a
        # time server.
        now = int(time.time())
        evening = now - (now % 86400) - 3600      # late yesterday evening
        recs = [
            dict(seq=1, kind="boot", cot=0, epoch_s=evening - 600,
                 duration_ms=0, peak_conf=0, windows=0,
                 peak_rms_milli=0, mean_rms_milli=0, boot_id=7,
                 uptime_ms=1200),
            dict(seq=2, kind="cry", cot=1, epoch_s=evening,
                 duration_ms=23400, peak_conf=100, windows=11,
                 peak_rms_milli=412, mean_rms_milli=187, boot_id=7,
                 uptime_ms=612000),
            dict(seq=3, kind="cry", cot=2, epoch_s=evening + 1800,
                 duration_ms=8600, peak_conf=99, windows=4,
                 peak_rms_milli=233, mean_rms_milli=140, boot_id=7,
                 uptime_ms=2412000),
            dict(seq=4, kind="deaf", cot=2, epoch_s=evening + 2400,
                 duration_ms=0, peak_conf=0, windows=0,
                 peak_rms_milli=0, mean_rms_milli=0, boot_id=7,
                 uptime_ms=3012000),
            dict(seq=5, kind="heard", cot=2, epoch_s=evening + 2700,
                 duration_ms=0, peak_conf=0, windows=0,
                 peak_rms_milli=0, mean_rms_milli=0, boot_id=7,
                 uptime_ms=3312000),
            dict(seq=6, kind="cry", cot=1, epoch_s=0,      # no clock yet
                 duration_ms=15000, peak_conf=100, windows=7,
                 peak_rms_milli=305, mean_rms_milli=190, boot_id=8,
                 uptime_ms=45000),
        ]
        device = "hub-7c9ebd12"
        body = hub_body(device, "Nursery hub", recs)

        # The body must be valid JSON before anything else is worth saying.
        try:
            json.loads(body)
        except ValueError as e:
            raise SystemExit(f"FAIL  the hub's body is not valid JSON: {e}")

        ans = post(base + "/api/v1/events", body, args.token)
        if ans.get("received") != len(recs):
            failures.append(f"the server received {ans.get('received')} "
                            f"of {len(recs)} records")
        print(f"  posted {len(recs)} records -> {ans}")

        # Posting the same batch again is what a retry after a dropped
        # connection looks like.  It must not double-count.
        ans2 = post(base + "/api/v1/events", body, args.token)
        if ans2.get("accepted") != 0:
            failures.append(f"a repeat batch added {ans2.get('accepted')} "
                            f"records; it should add none")
        print(f"  posted the same batch again -> {ans2}")

        s = get(base + "/api/v1/summary?days=90")
        k = s["kpis"]
        if k["total_cries"] != 3:
            failures.append(f"summary counts {k['total_cries']} cries, "
                            f"expected 3 (two timed, one untimed)")
        cots = {c["cot"]: c for c in s["per_cot"]}
        if set(cots) != {1, 2}:
            failures.append(f"per_cot has {sorted(cots)}, expected [1, 2]")
        if 1 in cots and cots[1]["cries"] != 2:
            failures.append(f"cot 1 shows {cots[1]['cries']} cries, expected 2")

        # The untimed record must be counted but never placed on a time
        # axis.  This is the honesty rule (D-90).
        placed = sum(d["cries"] for d in s["per_day"])
        if placed != 2:
            failures.append(f"{placed} cries placed on the day axis, "
                            f"expected 2 -- the untimed record must not be placed")
        hour_total = sum(h["cries"] for h in s["per_hour"])
        if hour_total != 2:
            failures.append(f"{hour_total} cries placed on the hour axis, "
                            f"expected 2")

        a = get(base + "/api/v1/analytics?days=90")
        if "duration_hist" not in a or "insights" not in a:
            failures.append("analytics is missing duration_hist or insights")

        ev = get(base + "/api/v1/events?limit=50")
        rows = ev["events"] if isinstance(ev, dict) else ev
        kinds = {r["kind"] for r in rows}
        if not {"cry", "deaf", "heard", "boot"} <= kinds:
            failures.append(f"the event list is missing kinds: {sorted(kinds)}")
        by_seq = {r["seq"]: r for r in rows if r["device"] == device}
        if 2 in by_seq:
            r = by_seq[2]
            if r["duration_s"] != 23:
                failures.append(f"record 2 lasted {r['duration_s']}s, "
                                f"expected 23 (23400 ms rounded)")
            if abs(r["peak_rms"] - 0.412) > 1e-6:
                failures.append(f"record 2 peak_rms {r['peak_rms']}, "
                                f"expected 0.412")
        else:
            failures.append("record 2 is not in the event list")

        d = get(base + "/api/v1/devices")
        names = d["devices"] if isinstance(d, dict) else d
        if not any((x.get("device") if isinstance(x, dict) else x) == device
                   for x in names):
            failures.append(f"{device} is not in the device list")

    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if tmp is not None:
            tmp.cleanup()

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("OK  the hub's upload body and the dashboard's API agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())