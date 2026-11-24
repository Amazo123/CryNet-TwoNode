#!/usr/bin/env python3
"""CryNet dashboard — the caregiver's record of the baby's cries.

The hub always writes every cry it hears to its own flash, whether or not
there is a network.  When the hub can reach this service it uploads what
it has; this service stores it, and the web dashboard in ``web/`` turns it
into the record a caregiver actually wants: how many times the baby cried,
in which cot, at what hour of the night, and whether that is changing.

It is deliberately plain: the Python standard library and SQLite, no
framework, no build step.  A caregiver's machine can run it with

    python dashboard/server.py

and that is the whole installation.  It binds every interface, so a phone
on the same network reaches it at http://<this machine's address>:8787.

The API is documented in API.md.  The short version:

    POST /api/v1/events        the hub uploads a batch of cry records
    GET  /api/v1/summary       the numbers and the charts for the dashboard
    GET  /api/v1/analytics     the patterns and the plain-language findings
    GET  /api/v1/events        the raw record, filtered
    GET  /api/v1/devices       the hubs that have reported in
    GET  /api/v1/health        is it alive

Usage:
    python dashboard/server.py
    python dashboard/server.py --port 8787 --db dashboard/data/crynet.db
    python dashboard/server.py --demo      # seed a week of made-up cries
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sqlite3
import statistics
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:                                  # Python < 3.9
    ZoneInfo = None

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"

# The kinds of record the hub sends.  "cry" is the one that matters; the
# others are the system's own health, which a caregiver wants to see
# beside the cry data (a cot that went deaf explains a silent night).
KINDS = ("cry", "deaf", "heard", "boot", "test")

# The night runs from eight in the evening until six in the morning.  The
# caregiver's question is usually "how many times was the baby up last
# night", so the night is counted as one bucket rather than as two
# calendar days.
NIGHT_START_HOUR = 20
NIGHT_END_HOUR = 6

# Duration buckets for the histogram, in seconds.  A short cry is a
# complaint and a long one is pain; the buckets are chosen around that
# difference rather than at even intervals.
DURATION_BUCKETS = (5, 15, 30, 60, 120, 300, 600)


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device     TEXT PRIMARY KEY,
    name       TEXT,
    fw         TEXT,
    first_seen INTEGER,
    last_seen  INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    device      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    cot         INTEGER,
    start_at    INTEGER,   -- epoch seconds, 0 = the hub did not know the time
    end_at      INTEGER,
    duration_s  INTEGER,
    peak_conf   INTEGER,
    windows     INTEGER,
    peak_rms    REAL,
    mean_rms    REAL,
    boot        INTEGER,
    uptime_ms   INTEGER,
    received_at INTEGER,
    PRIMARY KEY (device, seq)
);

CREATE INDEX IF NOT EXISTS idx_events_start ON events (start_at);
CREATE INDEX IF NOT EXISTS idx_events_kind  ON events (kind);
"""


class Store:
    """The SQLite record.  One connection per thread."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._local = threading.local()
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        db = getattr(self._local, "db", None)
        if db is None:
            db = sqlite3.connect(self.path, timeout=30)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            self._local.db = db
        return db

    # -- writing ---------------------------------------------------------

    def record(self, device: str, ev: dict, fw: str, name: str) -> bool:
        """Store one event.  Returns True if it was new.

        The hub sends the same record more than once if a reply is lost, so
        the store has to be idempotent: the pair (device, seq) is the key,
        and a record that is already there is simply acknowledged.
        """
        db = self.connect()
        now = int(time.time())
        with db:
            cur = db.execute(
                "INSERT OR IGNORE INTO events (device, seq, kind, cot, start_at,"
                " end_at, duration_s, peak_conf, windows, peak_rms, mean_rms,"
                " boot, uptime_ms, received_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    device,
                    int(ev.get("seq", 0)),
                    str(ev.get("kind", "cry")),
                    _int_or_none(ev.get("cot")),
                    _int_or_none(ev.get("start")),
                    _int_or_none(ev.get("end")),
                    _int_or_none(ev.get("duration_s")),
                    _int_or_none(ev.get("peak_conf")),
                    _int_or_none(ev.get("windows")),
                    _float_or_none(ev.get("peak_rms")),
                    _float_or_none(ev.get("mean_rms")),
                    _int_or_none(ev.get("boot")),
                    _int_or_none(ev.get("uptime_ms")),
                    now,
                ),
            )
            inserted = cur.rowcount > 0
            db.execute(
                "INSERT INTO devices (device, name, fw, first_seen, last_seen)"
                " VALUES (?,?,?,?,?)"
                " ON CONFLICT(device) DO UPDATE SET"
                "   name=COALESCE(excluded.name, devices.name),"
                "   fw=COALESCE(excluded.fw, devices.fw),"
                "   last_seen=excluded.last_seen",
                (device, name, fw, now, now),
            )
        return inserted

    def device_seen(self, device: str, fw: str = "", name: str = "") -> None:
        db = self.connect()
        now = int(time.time())
        with db:
            db.execute(
                "INSERT INTO devices (device, name, fw, first_seen, last_seen)"
                " VALUES (?,?,?,?,?)"
                " ON CONFLICT(device) DO UPDATE SET"
                "   last_seen=excluded.last_seen",
                (device, name or None, fw or None, now, now),
            )

    # -- reading ---------------------------------------------------------

    def devices(self) -> list[dict]:
        rows = self.connect().execute(
            "SELECT * FROM devices ORDER BY last_seen DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def events(self, since: int = 0, until: int = 0, cot: int = 0,
               kind: str = "", limit: int = 500) -> list[dict]:
        """The records in a window, including the ones with no time.

        A record with `start_at = 0` is one the hub made before it knew
        the time (D-90).  It is evidence that a cry happened, so it is
        returned and counted; it is simply never placed on a time axis.
        For windowing it falls back to `received_at` -- we cannot know
        when the cry was, but we do know when we learned about it, and
        that is the only honest bound available.
        """
        when = "(CASE WHEN start_at > 0 THEN start_at ELSE received_at END)"
        sql = "SELECT * FROM events WHERE 1=1"
        args: list = []
        if since:
            sql += f" AND {when} >= ?"
            args.append(since)
        if until:
            sql += f" AND {when} <= ?"
            args.append(until)
        if cot:
            sql += " AND cot = ?"
            args.append(cot)
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        sql += f" ORDER BY {when} DESC, seq DESC LIMIT ?"
        args.append(limit)
        rows = self.connect().execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def all_cry_events(self, since: int = 0, until: int = 0) -> list[dict]:
        """Every cry, oldest first, for the analytics."""
        sql = "SELECT * FROM events WHERE kind IN ('cry','test')"
        args: list = []
        if since:
            sql += " AND start_at >= ?"
            args.append(since)
        if until:
            sql += " AND start_at <= ?"
            args.append(until)
        sql += " ORDER BY start_at ASC"
        return [dict(r) for r in self.connect().execute(sql, args).fetchall()]


def _int_or_none(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------

def make_local(tz: str = ""):
    """Turn epoch seconds into a datetime in the caregiver's timezone.

    The page sends its zone with every request (web/app.js) because the
    hosted copy of this service runs in UTC and the caregiver does not.
    An unknown or missing zone falls back to this machine's local time,
    which is what the service has always done when it ran on the
    caregiver's own computer.
    """
    if tz and ZoneInfo is not None:
        try:
            zone = ZoneInfo(tz)
        except Exception:
            zone = None
        if zone is not None:
            return lambda ts: datetime.fromtimestamp(ts, zone)
    return datetime.fromtimestamp


def night_key(ts: int, lt=make_local()) -> str:
    """The night a timestamp belongs to.

    A cry at 02:00 on the 12th happened during the night of the 11th --
    the evening of the 11th into the morning of the 12th -- so the night
    is named by the day it started.  That is how a caregiver counts a
    night, and it is the only way the numbers add up.
    """
    d = lt(ts)
    if d.hour >= NIGHT_START_HOUR:
        return d.date().isoformat()
    if d.hour < NIGHT_END_HOUR:
        return (d - timedelta(days=1)).date().isoformat()
    return d.date().isoformat()


def local_date(ts: int, lt=make_local()) -> str:
    return lt(ts).date().isoformat()


def build_summary(store: Store, days: int, cot: int = 0, tz: str = "") -> dict:
    """The numbers and the series the dashboard draws."""
    lt = make_local(tz)
    now = int(time.time())
    since = now - days * 86400
    events = store.events(since=since, until=now + 86400, cot=cot,
                          kind="cry", limit=100000)
    events = [e for e in events if e["kind"] in ("cry", "test")]
    events.sort(key=lambda e: e["start_at"] or 0)

    durations = [int(e["duration_s"] or 0) for e in events]
    total_s = sum(durations)

    per_cot: dict[int, dict] = {}
    per_day: dict[str, dict] = {}
    per_hour = [0] * 24
    per_hour_s = [0] * 24
    per_weekday = [0] * 7
    nights: dict[str, dict] = {}
    heat_counts: dict[int, list[int]] = {}
    heat_seconds: dict[int, list[int]] = {}

    untimed = 0
    for e in events:
        ts = int(e["start_at"] or 0)
        c = int(e["cot"] or 0)
        dur = int(e["duration_s"] or 0)

        # Which cot cried, how often and how loudly are facts whether or
        # not the hub knew the date, so they are counted for every
        # record.  Only `last_at` needs a time.
        bucket = per_cot.setdefault(c, {"cot": c, "cries": 0, "seconds": 0,
                                        "max_seconds": 0, "last_at": 0,
                                        "confidences": []})
        bucket["cries"] += 1
        bucket["seconds"] += dur
        bucket["max_seconds"] = max(bucket["max_seconds"], dur)
        if e["peak_conf"] is not None:
            bucket["confidences"].append(int(e["peak_conf"]))
        if not ts:
            untimed += 1
            continue
        bucket["last_at"] = max(bucket["last_at"], ts)
        local = lt(ts)

        day = per_day.setdefault(local_date(ts, lt), {"day": local_date(ts, lt),
                                                  "cries": 0, "seconds": 0,
                                                  "cots": set()})
        day["cries"] += 1
        day["seconds"] += dur
        if c:
            day["cots"].add(c)

        per_hour[local.hour] += 1
        per_hour_s[local.hour] += dur
        per_weekday[local.weekday()] += 1

        nk = night_key(ts, lt)
        night = nights.setdefault(nk, {"night": nk, "cries": 0, "seconds": 0,
                                       "cots": set()})
        night["cries"] += 1
        night["seconds"] += dur
        if c:
            night["cots"].add(c)

        if c:
            hc = heat_counts.setdefault(c, [0] * 24)
            hs = heat_seconds.setdefault(c, [0] * 24)
            hc[local.hour] += 1
            hs[local.hour] += dur

    for b in per_day.values():
        b["cots"] = sorted(b["cots"])
    for b in nights.values():
        b["cots"] = sorted(b["cots"])

    night_list = sorted(nights.values(), key=lambda n: n["night"])
    gaps = []
    for a, b in zip(events, events[1:]):
        if a["start_at"] and b["start_at"]:
            gaps.append(b["start_at"] - a["start_at"])

    cots_sorted = sorted(per_cot.values(), key=lambda b: b["cot"])
    for b in cots_sorted:
        confs = b.pop("confidences")
        b["avg_conf"] = round(sum(confs) / len(confs), 1) if confs else None

    heat_cots = sorted(heat_counts.keys())
    devices = store.devices()

    return {
        "device": devices[0] if devices else None,
        "devices": devices,
        "range": {"from": since, "to": now, "days": days},
        "kpis": {
            "total_cries": len(events),
            "timed_cries": len(events) - untimed,
            "untimed_cries": untimed,
            "cries_per_day": round(len(events) / days, 2) if days else 0,
            "total_cry_seconds": total_s,
            "avg_cry_seconds": round(total_s / len(events), 1) if events else 0,
            "longest_cry_seconds": max(durations) if durations else 0,
            "median_cry_seconds": round(statistics.median(durations), 1)
            if durations else 0,
            "cots_crying": len(per_cot),
            "nights_affected": len(nights),
            "nights_per_week": round(len(nights) / (days / 7.0), 2)
            if days >= 7 else 0,
            # A per-night average must divide like by like: a record with
            # no time cannot be attributed to a night.
            "avg_cries_per_night": round((len(events) - untimed) / len(nights), 2)
            if nights else 0,
            "last_cry_at": max((int(e["start_at"] or 0) for e in events),
                               default=0),
            "median_gap_min": round(statistics.median(gaps) / 60.0, 1)
            if gaps else None,
        },
        "per_cot": cots_sorted,
        "per_day": [per_day[k] for k in sorted(per_day)],
        "per_night": night_list,
        "per_hour": [{"hour": h, "cries": per_hour[h], "seconds": per_hour_s[h]}
                     for h in range(24)],
        "per_weekday": [{"weekday": w, "cries": per_weekday[w]}
                        for w in range(7)],
        "heatmap": {
            "cots": heat_cots,
            "counts": [heat_counts[c] for c in heat_cots],
            "seconds": [heat_seconds[c] for c in heat_cots],
        },
        "recent": [
            {
                "seq": e["seq"], "cot": e["cot"], "kind": e["kind"],
                "start": e["start_at"], "end": e["end_at"],
                "duration_s": e["duration_s"], "peak_conf": e["peak_conf"],
                "windows": e["windows"], "peak_rms": e["peak_rms"],
                "mean_rms": e["mean_rms"],
            }
            for e in events[-400:]
        ],
    }


def build_analytics(store: Store, days: int, tz: str = "") -> dict:
    """The patterns: distributions, gaps, nights, and what they mean."""
    lt = make_local(tz)
    now = int(time.time())
    since = now - days * 86400
    events = [e for e in store.all_cry_events(since=since, until=now + 86400)
              if e["start_at"]]
    untimed = sum(
        1 for e in store.events(since=since, until=now + 86400, kind="cry",
                                limit=100000)
        if not e["start_at"])

    durations = [int(e["duration_s"] or 0) for e in events]
    confs = [int(e["peak_conf"]) for e in events if e["peak_conf"] is not None]

    hist = [{"label": _bucket_label(lo, hi), "count": 0} for lo, hi in
            _bucket_pairs(DURATION_BUCKETS)]
    for d in durations:
        for i, (lo, hi) in enumerate(_bucket_pairs(DURATION_BUCKETS)):
            if lo <= d < hi:
                hist[i]["count"] += 1
                break

    gaps = []
    for a, b in zip(events, events[1:]):
        gaps.append(b["start_at"] - a["start_at"])

    nights: dict[str, list[dict]] = {}
    for e in events:
        nights.setdefault(night_key(int(e["start_at"]), lt), []).append(e)

    # The hour each cot is most often heard in, and how sharp that peak
    # is -- a caregiver wants to know "cot 2 always wakes at 03:00".
    per_cot = []
    for e_cot in sorted({int(e["cot"] or 0) for e in events}):
        sub = [e for e in events if int(e["cot"] or 0) == e_cot]
        by_hour = [0] * 24
        for e in sub:
            by_hour[lt(int(e["start_at"])).hour] += 1
        peak_hour = max(range(24), key=lambda h: by_hour[h])
        total = sum(by_hour)
        share = round(100.0 * by_hour[peak_hour] / total, 1) if total else 0
        secs = sum(int(e["duration_s"] or 0) for e in sub)
        per_cot.append({
            "cot": e_cot,
            "cries": len(sub),
            "seconds": secs,
            "avg_seconds": round(secs / len(sub), 1) if sub else 0,
            "max_seconds": max(int(e["duration_s"] or 0) for e in sub) if sub else 0,
            "median_seconds": round(statistics.median(
                [int(e["duration_s"] or 0) for e in sub]), 1) if sub else 0,
            "by_hour": by_hour,
            "peak_hour": peak_hour,
            "peak_share": share,
            "night_cries": sum(1 for e in sub
                               if lt(int(e["start_at"])).hour
                               >= NIGHT_START_HOUR
                               or lt(int(e["start_at"])).hour
                               < NIGHT_END_HOUR),
        })

    return {
        "range": {"from": since, "to": now, "days": days},
        "duration_hist": hist,
        "confidence": {
            "min": min(confs) if confs else None,
            "median": round(statistics.median(confs), 1) if confs else None,
            "max": max(confs) if confs else None,
        },
        "gaps": {
            "count": len(gaps),
            "median_min": round(statistics.median(gaps) / 60.0, 1) if gaps else None,
            "max_min": round(max(gaps) / 60.0, 1) if gaps else None,
            "min_min": round(min(gaps) / 60.0, 1) if gaps else None,
        },
        "nights": [
            {
                "night": k,
                "cries": len(v),
                "seconds": sum(int(e["duration_s"] or 0) for e in v),
                "cots": sorted({int(e["cot"] or 0) for e in v}),
                "first": min(int(e["start_at"]) for e in v),
                "last": max(int(e["start_at"]) for e in v),
            }
            for k, v in sorted(nights.items())
        ],
        "per_cot": per_cot,
        # Every pattern on this page is a statement about *when*.  A
        # record with no time cannot take part in one, so it is counted
        # and reported rather than quietly folded in.
        "untimed_cries": untimed,
        "insights": build_insights(events, per_cot, nights, gaps),
    }


def _bucket_pairs(edges):
    pairs = []
    lo = 0
    for hi in edges:
        pairs.append((lo, hi))
        lo = hi
    pairs.append((lo, 10 ** 9))
    return pairs


def _bucket_label(lo, hi):
    if hi >= 10 ** 9:
        return f"{lo / 60:.0f}+ min"
    return f"{lo}-{hi}s" if hi - lo <= 60 else f"{lo // 60}-{hi // 60} min"


def build_insights(events, per_cot, nights, gaps) -> list[str]:
    """The plain-language findings a caregiver can act on.

    These are read by a person, not a machine, so they are written as
    sentences and they only say what the data actually shows.
    """
    out: list[str] = []
    if not events:
        return ["No cries have been recorded yet."]

    total = len(events)
    out.append(f"{total} cry episode{'s' if total != 1 else ''} recorded.")

    for c in per_cot:
        if c["cries"] < 3:
            continue
        hour = c["peak_hour"]
        if c["peak_share"] >= 40:
            out.append(
                f"Cot {c['cot']} is usually heard around {hour:02d}:00 "
                f"({c['peak_share']}% of its cries fall in that hour)."
            )
        if c["night_cries"] / c["cries"] > 0.6:
            out.append(
                f"Cot {c['cot']} cries are mostly at night "
                f"({c['night_cries']} of {c['cries']})."
            )

    if nights:
        counts = [len(v) for v in nights.values()]
        avg = sum(counts) / len(counts)
        out.append(
            f"On average {avg:.1f} cry episodes per night across "
            f"{len(nights)} night{'s' if len(nights) != 1 else ''}."
        )
        worst = max(nights.items(), key=lambda kv: len(kv[1]))
        if len(counts) > 1 and len(worst[1]) > avg * 1.5:
            out.append(
                f"The night of {worst[0]} was the heaviest, with "
                f"{len(worst[1])} episodes."
            )

    if gaps:
        med = statistics.median(gaps) / 60.0
        if med < 30:
            out.append(
                f"Cries come roughly every {med:.0f} minutes on average, "
                f"which is a dense pattern."
            )
        elif med > 240:
            out.append(
                f"Cries are well spread out -- about every {med / 60:.1f} hours."
            )

    durs = [int(e["duration_s"] or 0) for e in events]
    if durs:
        med_d = statistics.median(durs)
        if med_d >= 60:
            out.append(
                f"The median cry lasts {med_d / 60:.1f} minutes, which is "
                f"long for settling complaints."
            )
        elif med_d <= 15:
            out.append(
                f"The median cry lasts {med_d:.0f} seconds -- short, "
                f"settling sounds."
            )
    return out


# --------------------------------------------------------------------------
# the demo data
# --------------------------------------------------------------------------

def seed_demo(store: Store, days: int = 7) -> None:
    """A week of invented cries, so the dashboard can be seen working
    before a hub has ever uploaded anything."""
    now = datetime.now()
    rng = random.Random(20261123)
    device = "demo-hub"
    store.device_seen(device, fw="demo", name="Demo hub")
    seq = 0
    for day in range(days, 0, -1):
        d = now - timedelta(days=day)
        # More cries at night than in the day: that is what a baby's
        # record looks like, and it is what the dashboard is for.
        for cot, n in ((1, rng.randint(0, 3)), (2, rng.randint(1, 5))):
            for _ in range(n):
                seq += 1
                hour = rng.choice([2, 3, 4, 13, 14, 18, 19, 20, 21])
                minute = rng.randint(0, 59)
                start = int(d.replace(hour=hour, minute=minute,
                                      second=0, microsecond=0).timestamp())
                dur = rng.randint(8, 150)
                store.record(device, {
                    "seq": seq, "kind": "cry", "cot": cot,
                    "start": start, "end": start + dur,
                    "duration_s": dur,
                    "peak_conf": rng.randint(94, 100),
                    "windows": rng.randint(1, 6),
                    "peak_rms": round(rng.uniform(0.01, 0.22), 4),
                    "mean_rms": round(rng.uniform(0.005, 0.10), 4),
                    "boot": 1, "uptime_ms": 0,
                }, fw="demo", name="Demo hub")


# --------------------------------------------------------------------------
# the HTTP service
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "CryNetDashboard/1.0"
    store: Store
    token: str = ""

    def log_message(self, fmt, *args):
        print(f"[dashboard] {self.address_string()} {fmt % args}")

    # -- helpers ---------------------------------------------------------

    def _send_json(self, obj, status: int = 200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, ctype: str):
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self) -> bool:
        if not self.token:
            return True
        got = self.headers.get("X-CryNet-Token", "")
        return got == self.token

    # -- routes ----------------------------------------------------------

    def do_GET(self):
        route = urlparse(self.path)
        query = parse_qs(route.query)
        path = route.path

        if path in ("/", "/index.html"):
            return self._send_file(WEB / "index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self._send_file(WEB / "app.js",
                                   "application/javascript; charset=utf-8")
        if path == "/style.css":
            return self._send_file(WEB / "style.css", "text/css; charset=utf-8")

        if path == "/api/v1/health":
            return self._send_json({
                "ok": True,
                "time": int(time.time()),
                "devices": len(self.store.devices()),
            })

        if path == "/api/v1/devices":
            return self._send_json({"devices": self.store.devices()})

        if path == "/api/v1/summary":
            days = int(_first(query, "days", 14))
            cot = int(_first(query, "cot", 0) or 0)
            tz = _first(query, "tz", "") or ""
            return self._send_json(build_summary(self.store, days, cot, tz))

        if path == "/api/v1/analytics":
            days = int(_first(query, "days", 30))
            tz = _first(query, "tz", "") or ""
            return self._send_json(build_analytics(self.store, days, tz))

        if path == "/api/v1/events":
            limit = min(int(_first(query, "limit", 200)), 2000)
            since = int(_first(query, "from", 0) or 0)
            until = int(_first(query, "to", 0) or 0)
            cot = int(_first(query, "cot", 0) or 0)
            kind = _first(query, "kind", "") or ""
            rows = self.store.events(since=since, until=until, cot=cot,
                                     kind=kind, limit=limit)
            return self._send_json({"events": rows})

        return self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        route = urlparse(self.path)
        path = route.path
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._send_json({"error": "bad json"}, 400)

        if path == "/api/v1/events":
            if not self._authorised():
                return self._send_json({"error": "unauthorised"}, 401)
            device = str(body.get("device") or "unknown")
            hub = body.get("hub") or {}
            self.store.device_seen(device, str(hub.get("fw", "")),
                                   str(hub.get("name", "")))
            events = body.get("events") or []
            accepted = 0
            for ev in events:
                if self.store.record(device, ev, str(hub.get("fw", "")),
                                     str(hub.get("name", ""))):
                    accepted += 1
            print(f"[dashboard] {device}: {len(events)} record(s), "
                  f"{accepted} new")
            return self._send_json({
                "accepted": accepted,
                "received": len(events),
                "server_time": int(time.time()),
            })

        if path == "/api/v1/admin/seed":
            if not self._authorised():
                return self._send_json({"error": "unauthorised"}, 401)
            seed_demo(self.store)
            return self._send_json({"ok": True})

        return self._send_json({"error": "not found"}, 404)


def _first(query: dict, key: str, default):
    v = query.get(key)
    if not v:
        return default
    try:
        return v[0]
    except (IndexError, TypeError):
        return default


def local_addresses() -> list[str]:
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="the CryNet caregiver dashboard")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--db", default=str(HERE / "data" / "crynet.db"))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--token", default=os.environ.get("CRYNET_TOKEN", ""),
                    help="shared secret the hub must send (X-CryNet-Token)")
    ap.add_argument("--demo", action="store_true",
                    help="seed a week of invented cries and exit")
    args = ap.parse_args()

    store = Store(Path(args.db))
    if args.demo:
        seed_demo(store)
        print(f"[dashboard] demo data written to {args.db}")
        return 0

    Handler.store = store
    Handler.token = args.token
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True

    addrs = local_addresses()
    shown = addrs[0] if addrs else "localhost"
    print(f"[dashboard] serving on http://{args.host}:{args.port}")
    print(f"[dashboard]   the caregiver's browser: http://{shown}:{args.port}")
    print("[dashboard]")
    print("[dashboard] To point the hub here, type this on the hub's own")
    print("[dashboard] serial console (the same port its log goes to):")
    print("[dashboard]")
    for a in addrs or ["<this machine's address>"]:
        print(f"[dashboard]     net set http://{a}:{args.port}/api/v1/events")
    if args.token:
        print(f"[dashboard]     net token {args.token}")
        print("[dashboard]   (a token is required on every upload)")
    print("[dashboard]")
    print("[dashboard] The hub already knows the Wi-Fi it was built with.")
    print("[dashboard] To change it:  net ssid <name> <password>")
    print("[dashboard] The router's 2.4 GHz channel MUST be 6 -- the cots")
    print("[dashboard] talk on channel 6 and the hub has only one radio.")
    print("[dashboard] Check with:    net        Send now with:  upload")
    print("[dashboard] Nothing above changes how the hub answers a cry.")
    print("[dashboard] With no network it records to its own flash, as ever.")
    print("[dashboard] Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
