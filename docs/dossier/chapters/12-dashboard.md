# Chapter 12 — The cry log, the network, and the dashboard

## Why the hub needed a record at all

Until this chapter's subsystems existed, everything the system knew about a cry lived in three
places: the hub's panel (until the power cut), the wrist's buzz (until it faded), and the hub's
serial console (until someone scrolled past it). A caregiver who slept through a buzz had nothing
to look at in the morning. The dashboard is the answer to that, and it is four pieces that were
built in this order:

| Piece | Where | What it is |
|---|---|---|
| **The cry log** | `crynet_log`, on the hub | every event written to the hub's own flash, network or no network |
| **The clock** | `crynet_clock`, on the hub | real timestamps for those records, and honesty about when it has none |
| **The network stage** | `crynet_net`, on the hub | Wi-Fi, SNTP, the uploader, and the presence report |
| **The dashboard** | `dashboard/`, off the hub | a service and a page, in two copies: one offline, one hosted |

One rule governs all four, and it is written at the top of `crynet_net.h`: **the hub must work
exactly as it does now with no internet at all.** Nothing in this chapter is on the path between a
cot's microphone and the caregiver's wrist. The log is written by the audio loop whether or not the
network stage ever runs; the network stage only reads the log afterwards and posts it somewhere.
If the network is absent, misconfigured, or broken, the only thing that changes is that the records
stay on the hub — six megabytes of them — and go up when it returns.

## The cry log — `crynet_log`

### Where it lives

The partition table has always reserved six megabytes for a `storage` partition:

```
storage,  data, spiffs, 0x210000, 0x600000,
```

The space was there from the first build and nothing used it — the component that mounts it did not
exist (D-96). `crynet_log` mounts it and appends to one file. Six megabytes at thirty-two bytes a
record is 196,608 records; at fifty cries a night that is a decade of nights, and the log keeps a
rolling window of *sent* records long before then.

### The record

One fixed-size record per event, thirty-two bytes, so that 128 of them fill a flash page exactly:

| Field | Type | Meaning |
|---|---|---|
| `seq` | u32 | the hub's own number for this record — the number the wrist shows |
| `boot_id` | u32 | which run of the hub it belongs to |
| `uptime_ms` | u32 | when it happened, from the hub's start |
| `epoch_s` | u32 | when it happened in the world, **if the clock knew** |
| `duration_ms` | u32 | how long the episode lasted |
| `peak_rms_milli` | u16 | the loudest moment, in thousandths |
| `mean_rms_milli` | u16 | the average over the episode |
| `kind` | u8 | 1 cry · 2 deaf · 3 heard · 4 boot · 5 console test |
| `cot` | u8 | which cot, 1-based |
| `peak_conf` | u8 | the model's highest confidence during the episode, percent |
| `windows` | u8 | how many windows the model judged |
| `reserved` | u32 | room for the next field |

A cry record is written **once, when the episode ends**, and never changed afterwards. But its
*number* is spent when the episode **starts** — `crynet_log_reserve()` hands it out so the wrist
can show "event #1042" while the episode is still running — and the record is written when it ends.
That one asymmetry broke the first uploader, as the next section describes. The other kinds (a cot
going deaf, a deaf cot coming back, the hub starting) are written immediately; they are the
system's own health, and they belong beside the cry data.

The number is the join between the three surfaces: the wrist shows it in the alert, the panel's
footer counts it, and the dashboard stores it as the record's key. A caregiver who saw an alert at
three in the morning can find that exact cry afterwards. The BLE packet's field is sixteen bits, so
on the wrist the number wraps at 65,536 (about three years of nights); the dashboard keeps the
whole thirty-two. If the log could not be opened, the hub passes 0 and counts its own events as it
always did — the wrist still shows a number that rises.

### The ordering rule (D-94)

The uploader sends the records that have not been sent yet, oldest first, in batches, and after
each batch it may claim *a number* as sent: everything up to it has gone, nothing above it has.
Getting that number wrong loses cries in exactly the way nobody notices — the hub says everything
has gone, and the dashboard simply never shows one.

Two facts make it subtle. First, **the file is not sorted by number**: a record's number is spent
when the episode starts and written when it ends, so two cots crying at once can end in the
opposite order they started, and the file can hold `…, 47, 49, 48, …`. The original binary search
over the file was invalid in exactly that case — asked for the first record above a number it
could land *past* a record with a lower number, and that record was then never sent. Second, the
watermark cannot simply be the highest number in the batch: an episode that has started but not
yet ended holds a spent number that has no record yet, and claiming it would say "sent up to #50"
while #48 is still being measured.

The rule that survived: the batch is the **lowest unsent numbers** (a linear scan, not file order —
taking file order could re-send the same high-numbered record forever while a lower one sits behind
it), and the watermark is **clamped below the lowest number that did not fit in the batch and the
lowest number an open episode still holds**.

This property is proved twice, on purpose:

- `firmware/tools/test_log_order.py` models the algorithm on the host — six tests including a
  ten-thousand-case soak, plus a companion test that runs the *old* algorithm and shows it losing
  records, so the guard cannot silently stop guarding;
- the hub's `logtest` console command runs the same scenario against the real component on the
  real chip, on its own scratch file, touching nothing real: two cots crying at once, the first cry
  to start ending last, the uploader running in between — every record must still be sent.

### What happens when it fills

`crynet_log_trim()` keeps the log to a rolling window, but only over records that have been sent.
Unsent records are never dropped unless the log has genuinely run out of room, and when that
happens the count is kept in `crynet_log_dropped()` and said out loud — a full log is not a silent
loss, it is an alarm in the console. Clearing the log does not reset the numbering, so the
dashboard never confuses new records with old ones.

## The clock — `crynet_clock`

A record without a time is not much of a record — the point of the dashboard is seeing that the
baby was up at three in the morning, in that cot, most nights this week. But the hub has no
real-time clock and no battery-backed one. It gets the time from an NTP server when it is on the
network, and two rules make that trustworthy anyway:

- **The hub's monotonic uptime is the authority for *how long*.** The wall clock is stored as a
  pair — *at this uptime, the time was that* — so a correction from the network moves the wall
  clock without moving the uptime, and no record is ever stamped twice.
- **The last known time survives a restart.** It is written to NVS as the hub runs and read back at
  boot, so the clock starts from where it was and runs on the uptime again. It is wrong by however
  long the hub was switched off — the price of not having a battery — and the network corrects it
  within a minute or two of connecting. Two NTP servers are configured, so one being unreachable
  does not leave the hub without a clock.

And the honesty rule: before the first correction of a boot, the clock reads as *unknown*, and the
records written in that window carry `epoch_s = 0`. The dashboard **counts untimed cries but never
places them on a timeline** — the contract test holds this as a first-class property, because an
untimed cry placed on the wrong day would be a lie the page tells in pastel colours.

## The network stage — `crynet_net`

### One radio, two jobs, one non-negotiable rule

The cot nodes and the hub talk ESP-NOW on channel 6, fixed (Chapter 9). Joining a Wi-Fi network
moves the radio to the router's channel — and if that is not 6, the cot link dies while the
dashboard looks perfectly healthy. That failure mode is the one real hazard of this whole
subsystem, and the firmware defends against it outright: **the moment the station associates,
`crynet_net` checks the channel, and if it is not 6 it drops the connection, puts the radio back
on 6, and says what to do about it.** The router's 2.4 GHz channel has to be set to 6. That is a
one-time change in the router's admin page, and it is the price of one radio doing two jobs.

Two build-level facts belong beside it:

- the station interface is created **before** the radio starts, not after — the original order
  failed in the field and became D-98, along with refusing uploads reported by HTTP status rather
  than as a silent retry;
- BLE and Wi-Fi share the one radio, so software coexistence (`CONFIG_ESP_COEX_SW_COEXIST_ENABLE`)
  arbitrates airtime between the ESP-NOW link and the BLE connection — and the burst measurements
  of Chapter 9 were re-checked with a Wi-Fi network joined.

### Configuration lives in NVS, and the token lives off Git

Nothing about the network is compiled into the image. The hub's serial console carries the words:

```
net status                       what the network stage knows right now
net set <url>                    where records go, e.g. http://192.168.1.50:8787/api/v1/events
net ssid <ssid> <password>       which network to join
net token <token>                the shared secret, sent as X-CryNet-Token
name <name>                      the name the caregiver sees on the dashboard
log / log clear                  read or clear the cry log
logtest                          the ordering proof, on the chip
```

All of it survives a reflash. The token deserves its own sentence: it was once a string in a
tracked file, and it was removed from Git deliberately (D-103) — it now exists only in the
service's secret store and in the hub's NVS. A credential that authenticates uploads does not
belong in a repository anyone can read.

### The uploader

The uploader posts batches of 32 records, up to 32 batches per turn, oldest first, and **marks
records sent only when the dashboard acknowledges them** — a dropped connection costs a retry, not
a record. It is the watermark rule of D-94, running. `https://` targets are supported with the
full certificate bundle (about 60 KB of flash, read only when a connection is made), so the hub
can verify who it is talking to.

### The presence report

The uploader answered one question — *what happened?* — but the dashboard also needs the other
one: *is the system even on?* A dashboard that only learns of a hub when a cry happens cannot tell
a quiet baby from a dead hub. So once every 30 seconds (D-105), whether or not there is anything
to record, the hub posts who is here: itself, its firmware, its name, and for each cot whether it
is answering, whether it has gone deaf, and how strong its radio is.

The cadence was picked twice. The first cut (D-104) was 15 seconds — a hub switched off reads as
offline in about a minute (15 s report, 45 s staleness, 10 s page poll). That was too eager: the
report wanted the radio while a cot's 64 KB burst was in flight. The final rule is that **the
presence yields to the cots**: the hub reports every 30 s, a report may wait up to 20 s for a
burst to finish (the link stage registers the guard that knows; a stuck guard can delay a report
but never stop the reports), and the service calls a hub gone after 90 s. Nothing costs the cots
anything, and a hub that is switched off still reads as gone in about two minutes.

The panel carries its own view of the same fact: a wireless mark drawn **only while the hub is on
the network** — green when it is, nothing at all when it is not (D-100, redrawn in D-103). A dim
grey "off" glyph was tried first and rejected: on a device that is *usually* offline by design,
a permanent badge trains the eye to ignore it.

### The freshness rule (D-108)

The first bench nights produced the one lie a monitor must not tell: the hub had been switched off
for a while, the panel said hub offline — and both cots *online*. The cause was structural. The
presence store keeps one row per cot, and that row is the hub's last word about that cot — but the
row carried the hub's verdict (`online: true`) with no freshness check of its own, so the post the
hub made just before a power cut held its cots "online" for ever.

The rule now: **a cot is online only while the hub's word about it is fresh.** The row is stamped
when it is written, and on the same clock the hub itself is judged by — 90 seconds — a row the hub
has stopped refreshing reads offline. A row with no stamp reads offline too; the default is
closed. The hub's own row already had this discipline; the cots' rows were missing it, in both
copies of the service. The regression test that proves it *fails on the old code* — aged store,
old server, "cots [1, 2] read online long after the hub that sees them stopped speaking" — and
that failure-on-old-code check is part of how the fix was accepted, not an afterthought.

## The dashboard — two copies, one contract

There are two copies of the service, and they must agree field for field:

- **The offline copy** — `dashboard/server.py`, Python's standard library only, SQLite, one file.
  It runs on anything: a laptop on the nursery Wi-Fi, a Raspberry Pi on a shelf. No dependencies,
  no account, no internet.
- **The hosted copy** — a Cloudflare Worker on D1 (D-95), live at
  `https://amazings-crynet.amazingadelowo.workers.dev` (D-97). It is the copy that works when the
  caregiver is not on the nursery's Wi-Fi, which is the whole point of hosting it.

Both serve the same API, documented in `dashboard/API.md`:

| Endpoint | Direction | What it does |
|---|---|---|
| `POST /api/v1/events` | hub → service | a batch of cry-log records; idempotent on `seq` |
| `POST /api/v1/presence` | hub → service | who is here, every 30 s |
| `GET /api/v1/presence` | page ← service | the hub and its cots, with freshness |
| `GET /api/v1/summary` | page ← service | KPIs, per-cot, per-day, per-hour |
| `GET /api/v1/analytics` | page ← service | duration histogram, patterns, insights |
| `GET /api/v1/events` | page ← service | the record list, filterable |
| `GET /api/v1/devices` | page ← service | the hubs known to the service |
| `GET /api/v1/health` | both | liveness, for tests and monitors |

Authentication has two doors. The hub authenticates with `X-CryNet-Token` — the secret from NVS.
The browser authenticates with HTTP Basic auth — a username and password the caregiver types once.
The two secrets are separate on purpose: leaking the upload token lets someone *write* to the
record; leaking the password only lets someone *read* it. Both live in the platform's secret store
and in one git-ignored local file; neither is in the repository, and every commit is scanned for
them before it is made.

The page itself (`dashboard/web/` — one HTML file, one stylesheet, one script, no framework, no
build step) reads like an instrument and not like a paragraph (D-102): presence cards with
per-cot signal bars, a smooth daily curve, the duration histogram, the record list with the
log's own numbers. It is named for the system and wears the hub's teal, with a dark and a light
palette that both passed a contrast validator (D-99). It polls presence every 10 s and renders
exactly what the service says — including, after D-108, the freshness rule.

## The contract test — the one thing no compiler checks

The hub builds its upload bodies by hand with `snprintf`, because ESP-IDF ships no JSON library.
The page is JavaScript, the service is Python. There is no type system, interface, or schema that
joins them: a field renamed on either side would fail *silently* — the hub would report success
and the dashboard would show nothing.

`firmware/tools/test_dashboard_contract.py` is the check. It builds the **same body, byte for
byte**, from the same fields the hub's `build_batch()` uses — formatting, rounding, field order
and all — posts it to a running dashboard, and checks that what comes back out of the API is what
went in. Then the presence body likewise. It covers the properties the system has already been
wrong about once each:

- a repeat batch (what a retry after a dropped connection looks like) must add **nothing**;
- an untimed record must be **counted but never placed** on the day or hour axes;
- a hub that just posted reads online, with its cots online **with it**;
- a store aged past the staleness window reads offline — hub *and* cots (D-108).

It starts its own throwaway server on a free port and writes nowhere inside the repository, so it
runs anywhere, any time; `--port` points it at an already-running local dashboard instead. (The
hosted copy is verified live in the same terms — a real login, the real presence rows — but the
test itself stays local, so it can age the store to prove the staleness rule.) It is part of the
pre-merge battery, and it failed on the old server the day D-108 was fixed, which is the strongest
statement that can be made about a test.

## The boot banner, and the stack that was too small

Two reliability findings closed this phase, and they are a pair because the second overturned the
first.

**The banner was lying (D-106).** The hub's boot banner is the identity check — it is how the
owner knows what is running. But it reported a firmware version inherited from a stale configure,
so a fresh build could describe itself as an old one; and the "restarts" the banner counted were
diagnosed as power-class resets, not crashes, on the strength of a clean-power soak: ten minutes,
zero restarts, zero cot flap, live telemetry on both cots, and 15 presence posts at the exact
30-second cadence.

**It was a stack overflow (D-107).** The very next capture caught the hub dying mid-run: a stack
overflow in task `main`. The whole live system ran on one 3,584-byte stack that ESP-IDF had sized
for an `app_main` that *returns* — and nothing in this system's `app_main` ever returns. The
restarts were never the power supply. The stacks are now sized for what actually runs on them, and
the same clean-power soak that exonerated the power now runs silent: zero restarts, presence posts
on the dot. The cot's "offline for a split second", reported alongside, is a 0.1-second staleness
blip that loses nothing.

The lesson recorded in D-107's row is worth repeating here: a soak proves the configuration that
ran during the soak. The banner fix and the power diagnosis were real, but the stack overflow sat
underneath both, waiting for a load pattern the soak had not produced. The connectivity feature
stayed in the system because after both fixes the soak was repeated and held.

## What this subsystem deliberately does not do

- **No audio leaves the room.** The records are metadata — numbers, durations, confidences. There
  is no microphone feed on the network, no recording of the child, nothing to leak.
- **No remote control.** The dashboard reads. It cannot silence the wrist, change a threshold,
  or reconfigure the hub — every one of those is a physical act on the unit, on purpose.
- **No cloud dependency for detection.** With the network unplugged, detection, alerting, logging
  and display are exactly what Chapter 6 describes; the dashboard empties when it can.
- **No router gymnastics beyond one setting.** The one deployment requirement is that the
  router's 2.4 GHz channel is 6. Everything else about the network is optional.
