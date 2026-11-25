# The dashboard's API

The dashboard service (`dashboard/server.py`) speaks JSON over HTTP. The
web page in `dashboard/web/` is the only consumer that matters, but the
API is documented here because the **hub** is a consumer too: it uploads
its cry records to `POST /api/v1/events`.

Everything is plain HTTP on the local network. If the service is put
behind the internet, put a TLS-terminating proxy in front of it and have
the hub talk to the proxy.

**The hosted copy.** There is now one: a Cloudflare Worker in
`dashboard/worker/` that serves the same API from a D1 database, on
Cloudflare's free tier. See `dashboard/worker/README.md` for how it is
deployed and pointed at. It differs from the local copy in two ways, and
both matter:

- **Every read needs a login.** The local copy on a home network leaves
  the GETs open; the hosted copy puts a login in front of them, because
  on the internet an open `/api/v1/summary` publishes the baby's whole
  cry record to anyone who finds the URL. The hub is unaffected: it
  sends `X-CryNet-Token` on uploads, and the same token is accepted on
  reads for scripts.
- **Reads may carry `?tz=<IANA zone>`.** Days, hours and nights are
  counted in that zone, which is how a copy hosted in UTC can still show
  the caregiver's own night. The page sends it automatically. With no
  `tz`, the local copy uses the machine's own timezone and the hosted
  copy uses UTC.

---

## `POST /api/v1/events` — the hub uploads a batch

The hub uploads in batches, and it may upload the same batch twice if a
reply is lost on the way back. The store is idempotent: the pair
`(device, seq)` identifies a record, and a record that is already there is
acknowledged but not duplicated.

Request:

```json
{
  "device": "hub-7c9ebd12",
  "hub": { "fw": "2.0-dashboard", "name": "Nursery hub" },
  "events": [
    {
      "seq": 1042,
      "kind": "cry",
      "cot": 2,
      "start": 1794182400,
      "end": 1794182434,
      "duration_s": 34,
      "peak_conf": 99,
      "windows": 5,
      "peak_rms": 0.2134,
      "mean_rms": 0.0981,
      "boot": 118447,
      "uptime_ms": 512340
    }
  ]
}
```

| field | type | meaning |
|---|---|---|
| `device` | string | the hub's identity (its MAC, in the firmware) |
| `hub.fw` | string | the firmware version, free-form |
| `hub.name` | string | a name for the caregiver to read |
| `events[].seq` | int | the hub's own record number; it only ever goes up, and it is what makes an upload idempotent |
| `events[].kind` | string | `cry`, `deaf`, `heard`, `boot`, or `test` |
| `events[].cot` | int | which cot the cry was heard on (1-based) |
| `events[].start`, `events[].end` | int | epoch seconds; `0` means the hub did not know the wall clock when it happened |
| `events[].duration_s` | int | how long the episode lasted |
| `events[].peak_conf` | int | the model's highest confidence for that episode, in percent |
| `events[].windows` | int | how many windows the model judged in that episode |
| `events[].peak_rms`, `events[].mean_rms` | float | the loudness of the episode |
| `events[].boot` | int | the hub's boot number, so a record can be traced to a session |
| `events[].uptime_ms` | int | milliseconds since that boot when the record was written |

Response:

```json
{ "accepted": 1, "received": 1, "server_time": 1794182435 }
```

`accepted` is how many records were **new**. The hub advances its
"uploaded" pointer by the number of records it sent, not by `accepted` —
it must not re-send what it already sent.

---

## `GET /api/v1/summary?days=14&cot=0`

The numbers and the series the dashboard draws. `cot=0` means every cot.

```json
{
  "device": { "device": "hub-7c9ebd12", "name": "Nursery hub", "fw": "2.0-dashboard",
               "first_seen": 1793000000, "last_seen": 1794182435 },
  "devices": [ ...same shape... ],
  "range": { "from": 1792978835, "to": 1794182435, "days": 14 },
  "kpis": {
    "total_cries": 37,
    "timed_cries": 35,
    "untimed_cries": 2,
    "cries_per_day": 2.64,
    "total_cry_seconds": 1180,
    "avg_cry_seconds": 31.9,
    "longest_cry_seconds": 214,
    "median_cry_seconds": 27.0,
    "cots_crying": 2,
    "nights_affected": 11,
    "nights_per_week": 5.5,
    "avg_cries_per_night": 3.36,
    "last_cry_at": 1794182400,
    "median_gap_min": 42.0
  },
  "per_cot": [
    { "cot": 1, "cries": 12, "seconds": 420, "max_seconds": 90,
      "avg_seconds": 35.0, "avg_conf": 98.4, "last_at": 1794100000 }
  ],
  "per_day": [
    { "day": "2026-11-20", "cries": 4, "seconds": 130, "cots": [1, 2] }
  ],
  "per_night": [
    { "night": "2026-11-20", "cries": 3, "seconds": 96, "cots": [2] }
  ],
  "per_hour": [ { "hour": 0, "cries": 0, "seconds": 0 }, ... 24 entries ... ],
  "per_weekday": [ { "weekday": 0, "cries": 4 }, ... 7 entries, Monday = 0 ... ],
  "heatmap": {
    "cots": [1, 2],
    "counts": [ [ 24 counts for cot 1 ], [ 24 counts for cot 2 ] ],
    "seconds": [ [ 24 totals for cot 1 ], [ 24 totals for cot 2 ] ]
  },
  "recent": [
    { "seq": 1042, "cot": 2, "kind": "cry", "start": 1794182400,
      "end": 1794182434, "duration_s": 34, "peak_conf": 99, "windows": 5,
      "peak_rms": 0.2134, "mean_rms": 0.0981 }
  ]
}
```

`recent` holds up to the last 400 episodes, oldest first — this is what
the timeline is drawn from.

### Records with no time

A record whose `start` is `0` is one the hub made **before it knew the
time** — the hub has no battery-backed clock (D-90). Such a record is
evidence that a cry happened, and it is **counted**:

- `total_cries` includes it;
- `per_cot` includes it — which cot cried is known, even when the date
  is not;
- `untimed_cries` says how many there are, and `timed_cries` how many
  have a time.

It is **never placed on a time axis**. It appears in no `per_day`, no
`per_night`, no `per_hour`, no `per_weekday`, no `heatmap` entry, and it
contributes to no gap. `avg_cries_per_night` divides the timed count by
the number of nights, so the two sides of that fraction are like for
like.

For windowing, an untimed record falls back to the moment the dashboard
received it. That is the only honest bound available: we cannot know
when the cry was, but we know when we learned of it.

The same rule applies to `/api/v1/analytics`, where every pattern is a
statement about *when*: untimed records take no part in them, and
`untimed_cries` says how many were left out.

---

## `GET /api/v1/analytics?days=30`

The patterns and the plain-language findings.

```json
{
  "range": { "from": ..., "to": ..., "days": 30 },
  "duration_hist": [ { "label": "0-5s", "count": 2 }, { "label": "5-15s", "count": 9 } ],
  "confidence": { "min": 94, "median": 99.0, "max": 100 },
  "gaps": { "count": 36, "median_min": 42.0, "max_min": 611.0, "min_min": 3.0 },
  "nights": [
    { "night": "2026-11-20", "cries": 3, "seconds": 96, "cots": [2],
      "first": 1794182400, "last": 1794182434 }
  ],
  "per_cot": [
    { "cot": 2, "cries": 21, "seconds": 810, "avg_seconds": 38.6,
      "max_seconds": 214, "median_seconds": 33.0, "by_hour": [ 24 counts ],
      "peak_hour": 3, "peak_share": 42.9, "night_cries": 17 }
  ],
  "untimed_cries": 2,
  "insights": [ "Cot 2 is usually heard around 03:00 (42.9% of its cries fall in that hour)." ]
}
```

`insights` is written to be read by a person. The page shows them as they
are; it must not invent findings of its own.

---

## `GET /api/v1/events?limit=200&cot=0&from=0&to=0&kind=cry`

The raw record, newest first. `from`/`to` are epoch seconds, `cot` is
1-based (0 = every cot), `kind` is one of the kinds above.

```json
{ "events": [ { "device": "...", "seq": 1042, "kind": "cry", "cot": 2,
                "start_at": 1794182400, "end_at": 1794182434, "duration_s": 34,
                "peak_conf": 99, "windows": 5, "peak_rms": 0.2134,
                "mean_rms": 0.0981, "boot": 118447, "uptime_ms": 512340,
                "received_at": 1794182435 } ] }
```

**The field names here are not the same as the ones in `summary.recent`.**
This endpoint returns the stored columns, so the times are `start_at` and
`end_at`; `summary.recent` returns them as `start` and `end`. A page that
reads both has to know which is which — the shipped page does, and says so
at the top of `web/app.js`.

## `GET /api/v1/devices`

```json
{ "devices": [ { "device": "hub-7c9ebd12", "name": "Nursery hub",
                 "fw": "2.0-dashboard", "first_seen": ..., "last_seen": ... } ] }
```

---

## `POST /api/v1/presence` — the hub says who is here

The cots have no network of their own — they talk to the hub over its
radio — so the hub is the only thing that can answer for them. It posts
this **once a minute**, and again immediately whenever a cot's state
changes, whether or not there is anything to record.

The owner still configures **one** address: the presence endpoint is the
events endpoint with its last path segment changed, so
`net set https://…/api/v1/events` needs no second setting.

Request:

```json
{
  "device": "hub-7c9ebd12",
  "hub": { "fw": "2.0-dashboard", "name": "Nursery hub" },
  "nodes": [
    { "cot": 1, "online": true, "deaf": false, "rssi": -47 },
    { "cot": 2, "online": false, "deaf": false, "rssi": 0 }
  ]
}
```

| field | type | meaning |
|---|---|---|
| `nodes[].cot` | int | the cot number, 1-based |
| `nodes[].online` | bool | the hub has heard from it lately |
| `nodes[].deaf` | bool | the hub cannot get a window from it, so it cannot announce a cry from it |
| `nodes[].rssi` | int | the telemetry signal strength in dBm; `0` = unknown |

Response:

```json
{ "ok": true, "cots": 2, "server_time": 1794182435 }
```

One row per cot is stored, replaced each time the hub speaks, so what is
stored is always the last thing the hub knew.

---

## `GET /api/v1/presence`

Who is here: the hubs, and the cots each hub can see.

```json
{
  "now": 1794182435,
  "hubs": [
    { "device": "hub-7c9ebd12", "name": "Nursery hub", "fw": "2.0-dashboard",
      "at": 1794182435, "age_s": 0, "online": true, "demo": false }
  ],
  "nodes": [
    { "device": "hub-7c9ebd12", "cot": 1, "online": true,
      "deaf": false, "rssi": -47, "at": 1794182435 }
  ]
}
```

A hub is taken to be **there** if it has spoken in the last three
minutes. The hub says once a minute, so three is three chances missed
before the dashboard calls it gone: long enough that one dropped request
does not make the caregiver think the hub has died, short enough that a
hub that has been switched off is gone before anyone has looked away.

A cot's `online` is what the hub last said about it. `deaf` is a
separate thing: a cot can be answering and still deaf, which means it
is transmitting and the hub cannot get a window from it, so it cannot
announce a cry.

## `GET /api/v1/health`

```json
{ "ok": true, "time": 1794182435, "devices": 1 }
```

---

## Notes for the page

- Every timestamp is **epoch seconds in UTC**; the page shows them in the
  browser's own local time.
- `start` of `0` means the hub did not know the wall clock. Those records
  are counted in the totals but are not placed on a timeline.
- The page polls `/api/v1/summary` every 30 seconds. It must not assume
  the numbers change between two polls.
- The page must work with **no data at all**: an empty state that says so,
  rather than a broken chart.
