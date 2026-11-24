# The cry record — the caregiver's dashboard

Every cry the hub hears is written into the hub's own flash. When the hub
has the network, it sends what it has stored here, and this page turns it
into a record a caregiver can read: which cot, when, how long, how loud,
and whether the nights are getting better or worse.

**Nothing here is required for the monitor to work.** With no Wi-Fi, no
router, and this server switched off, the hub hears a cry and buzzes the
wrist exactly as it always did, and keeps the record in its own flash
until a network appears. The dashboard is a reader, not a dependency.

---

## 1. Running it

You need Python 3.10 or newer. Nothing else — no packages, no build step.

```bash
python dashboard/server.py
```

That is the whole installation. It serves on port 8787 and writes its
database to `dashboard/data/crynet.db`. Open the address it prints in a
browser on this machine, or on a phone on the same Wi-Fi.

The server prints the exact line to type into the hub. It looks like:

```
[dashboard]     net set http://192.168.1.50:8787/api/v1/events
```

Copy that line. You will paste it into the hub's serial console in §3.

### Options

| Flag | What it does |
|---|---|
| `--port 8787` | Which port to serve on. |
| `--db path\to\file.db` | Where the record lives. One file; copy it to back it up. |
| `--host 127.0.0.1` | Serve to this machine only. The default `0.0.0.0` lets the hub and your phone reach it. |
| `--token SECRET` | Require the hub to send `X-CryNet-Token: SECRET` on every upload. Optional. |
| `--demo` | Write a week of invented cries into the database and exit, so you can see the page before the hub has sent anything. Use a throwaway `--db` for this. |

To see the page with invented data:

```bash
python dashboard/server.py --demo --db dashboard/data/demo.db
python dashboard/server.py --db dashboard/data/demo.db
```

To keep it running after you close the terminal, use whatever your machine
already has — Task Scheduler on Windows, `systemd` or `nohup` on Linux.
There is nothing special about the process; it is one Python file.

---

## 2. The one thing you must change on your router

> **Set the router's 2.4 GHz channel to 6.**

This is not optional and it is not a preference. The cot nodes and the hub
talk to each other over ESP-NOW on **channel 6, fixed**. The hub has one
radio. When it joins your Wi-Fi it moves that radio to your router's
channel — and if your router is on channel 1 or 11, the cots can no longer
be heard.

That failure is the dangerous kind: the dashboard would look healthy while
the wrist had gone silent. So the hub refuses to allow it. The moment it
associates it checks the channel, and if it is not 6 it drops the
connection immediately, puts the radio back on 6, prints an instruction,
and tries again in five minutes. The monitor always wins over the record.

In the router's admin page, under wireless settings for the **2.4 GHz**
band, change *Channel* from *Auto* to **6**. (5 GHz is irrelevant — the
ESP32 cannot see it.) Then the hub will join and stay.

If you cannot change the router, the system still works perfectly as a
monitor and still records every cry to the hub's flash. It simply has
nowhere to send them until it meets a network on channel 6.

---

## 3. Pointing the hub at this dashboard

The hub is already built with your Wi-Fi name and password, so it joins on
boot without any setup. What it cannot know at build time is *where this
server is* — that depends on which machine you run it on.

Connect the hub over USB and open its serial port at 115200. That is the
same port its log goes to; the console listens on the same line. Type:

```
net set http://192.168.1.50:8787/api/v1/events
```

using the address the server printed. That is all. The setting is stored in
the hub's own flash and **survives a reflash**, so you type it once.

Then check:

```
net
```

which prints whether the Wi-Fi is up, which channel the radio is on, where
it is posting, and how much it has sent. To make it send immediately
rather than wait for its next turn:

```
upload
```

### Every console command for the record

| Command | What it does |
|---|---|
| `history` | The last 10 records, newest first. `history 40` for more. |
| `log` | How many records the hub holds, how many are still unsent, and whether it knows the time. |
| `log clear` | Throw the hub's log away. The record numbers carry on, so the dashboard does not confuse new records with old ones. Already-uploaded records on the dashboard are not touched. |
| `net` | The network: connection, channel, address, what it has sent, last problem. |
| `net set <url>` | Where to post. An empty value turns uploading off and leaves the record alone. |
| `net ssid <name> <password>` | Join a different Wi-Fi. |
| `net name <name>` | The name this hub shows as on the dashboard. |
| `net token <secret>` | The shared secret, if you started the server with `--token`. |
| `upload` | Try to send the unsent records now. |
| `logtest` | Prove, on the hub itself, that a cry is never lost when two cots cry at once. Runs on its own scratch file; your log is untouched. Answers `PASS` or `FAIL`. |

The older commands are unchanged: `help`, `status`, `alert <cot>`, `clear`.

---

## 4. What the page shows

**Overview** — the headline numbers for the range you pick (7, 14, 30 or 90
days), per cot or for all of them: how many cries, how long they lasted,
how many nights were affected, the typical gap between cries. Then the
shape of it: cries by day, by night, by hour of the clock, and a
day-by-hour heatmap that shows at a glance whether the difficult stretch
is 2 a.m. or 5 a.m. The most recent episodes are listed underneath, with
the same record number the wrist showed.

**Patterns** — the analytics: how long cries last (a histogram), how
confident the model was, the gaps between cries, night by night, and a
plain-language reading of what stands out.

**A night is 20:00 to 06:00**, named by the evening it starts on. "Night of
the 14th" means the night that began on the evening of the 14th and ran
into the morning of the 15th. That is how a caregiver thinks about a
night, and it is not the same as a calendar day.

**Times are shown in your browser's own time zone.** The hub records in
UTC; the page converts. The hub's own console prints UTC.

### Records with no time

The hub has no battery-backed clock (D-90). Until it has reached a time
server it knows only how long it has been awake. Those records are marked
*untimed*: they are **counted in the totals** — a cry happened, and that is
true whether or not the hub knew the date — but they are **never placed on
a time axis**, because placing them would be a guess. The page says how
many there are. Once the hub reaches the network it learns the time and
every record after that is placed properly.

### System records

Not every record is a cry. The hub also writes down when it started, when
a cot went **deaf** (its audio stopped reaching the hub, so it was not
being watched), when that cot came back, and when a test alert was raised
from the console. These appear in the system strip, because a quiet
stretch on the chart means something quite different if the cot was deaf
through it.

---

## 5. Where the data lives, and how much

**On the hub:** a 6 MB flash partition, holding up to 8192 records of 32
bytes. At 50 cries a night that is over five months of nights with no
network at all. After a successful upload the hub trims to the most recent
2000 records. If it ever fills while offline it drops the oldest and says
so out loud, on the console and in `log`.

**On the dashboard:** one SQLite file, wherever `--db` points. It keeps
everything it is given, forever — there is no retention limit. Uploading
the same record twice is harmless: records are keyed by hub and record
number, so a retry after a dropped connection does not double-count.

**On the wire:** batches of 32 records, oldest first, over plain HTTP on
your own network, or HTTPS if you give it an `https://` address (the hub
carries the standard root certificates). The hub marks records as sent
only when the server answers that it has them.

The full request and response shapes are in [`API.md`](API.md).

---

## 6. If it is not working

**The page says nothing has been uploaded.** That is the normal first-run
state. Check, in order: is the server running; does `net` on the hub show
the right address; does it show *connected*; does it show channel 6.

**`net` says "NOT the cots' channel".** Your router is not on channel 6.
See §2. The hub has deliberately disconnected to protect the cot link.

**`net` shows connected but nothing is sent.** The address is probably
wrong or unreachable from the hub. Check that the machine running the
server is on the same network, that its firewall allows the port, and that
you used the machine's LAN address (not `localhost` or `127.0.0.1` — those
mean the hub itself). `net` prints the last problem it hit.

**The wrist works but the dashboard is empty.** Correct behaviour when
there is no network. The record is on the hub; `log` shows how much is
waiting.

**Records appear with no time.** The hub has not reached a time server.
It needs the network for that too. See §4.