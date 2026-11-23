# Chapter 9 — The radio link, and the airtime problem

## Why ESP-NOW

The nodes must reach the hub without a Wi-Fi access point, without an IP stack, without a DHCP
lease, and without a connection that can drop and need re-establishing. ESP-NOW is Espressif's
connectionless 802.11 vendor-frame protocol: a MAC address and a channel, and frames go out. No
association, no handshake, no reconnection state machine.

Its constraints are the design's constraints:

| Constraint | Value | Consequence |
|---|---|---|
| Max payload per frame | 250 bytes | a 64,000-byte window must be fragmented |
| Delivery | **unacknowledged for broadcast** | the protocol must supply its own reliability |
| Queue depth | 10 frames | the sender must throttle itself |
| Channel | fixed, both ends | must be set explicitly, after `esp_now_init()` |
| Radio | shared with BLE on the hub | **the central problem of this chapter** |

Channel **6** on both sides, set with `esp_wifi_set_channel()` after `esp_now_init()`.

## The wire format

`crynet_proto.h` on the hub and the `LINK_TYPE_*` block in the node sketch were **written from the
same table**. There is no code generation and no shared header between an ESP-IDF component and an
Arduino sketch — so the table is duplicated deliberately and documented as such, and both sides'
constants are asserted against the same numbers.

| Type | Value | Direction | Payload |
|---|---|---|---|
| `TELEMETRY` | 1 | node → hub | 32 B |
| `FRAGMENT` | 2 | node → hub | index, total, 224 B, CRC-16 |
| `REQUEST` | 3 | hub → node | sequence wanted |
| `HEARTBEAT` | 4 | both | liveness |
| `RESEND` | 5 | hub → node | seq + 36-byte bitmap, 54 B total |

`FRAG_PAYLOAD = 224`, `FRAG_COUNT = 286`, `RESEND_BITMAP_BYTES = 36`.
`CRYNET_PROTO_MAX_PAYLOAD = MAX_FRAME − HEADER_BYTES − 2` — the 2 being the CRC-16.

### Two checksums, and why two

**CRC-16/CCITT-FALSE per fragment.** Check vector `0x29B1` over `"123456789"`. This catches a
corrupted fragment *at arrival*, so a bad fragment's bit is never set in the received bitmap and the
resend logic asks for it. Without a per-fragment check, a corrupted fragment would be marked received
and the window would be silently wrong.

**CRC-32/IEEE 802.3 over the whole 64,000-byte window.** Computed by the node over the exact bytes it
uploads, advertised in telemetry, and recomputed by the hub over what it reassembled. `MATCH` is the
end-to-end proof. It is the same polynomial as `zlib.crc32`, chosen so that a host-side Python tool
can verify a captured window in one line without reimplementing a CRC.

Two levels because they answer different questions: *is this piece intact?* and *is the whole thing
the thing that was sent?*

## The airtime problem — the hardest issue in the project

This is worth being able to tell in full, because **the reasoning was wrong twice before it was
right**, and the way it was finally settled is a model of how to debug a system.

### The symptom (I-24)

The burst never completed. **267–274 of 286 fragments arrived**, then the burst timed out. Every
time, roughly the same fraction missing.

### Hypothesis (a): the Wi-Fi channel — wrong

Both ends were moved to channel 6 and the node was heard. But the loss fraction did not change. If
interference from other networks on the channel were the cause, changing channel should have changed
the loss rate. It did not. **The loss was independent of the channel** — a fact that would later be
the decisive clue.

### Hypothesis (b): the node is dropping frames — wrong

The node's own counters: **7,667 frames sent, 0 lost, 2.3 ms average send wait.** The node was not
dropping anything. (Getting to trust that number required first fixing `g_tx_failed`, which had been
hard-wired to zero because the send callback's status was thrown away — a counter that cannot fail is
not evidence.)

### Hypothesis (c): the hub's own Bluetooth — right

The decisive experiment was **subtractive**: build the hub **without BLE at all** and run the same
burst.

> **286/286 fragments in 3.75 s, four complete bursts in a row.** With BLE on, the same build lost
> ~6 % of every burst.

One variable removed, symptom gone. That is a controlled experiment, not a guess.

### The mechanism

BLE advertises on channels **37, 38 and 39**. The hub has **one radio**. To send an advertisement it
must *retune* to each of those channels in turn — and while it is retuned, **the Wi-Fi receiver is
deaf**.

NimBLE's default advertising interval is 30–60 ms, and each advertisement is three events (one per
channel). That is roughly **100 transmissions a second** and about **9 % deafness**, independent of
the Wi-Fi channel and independent of the frame rate.

That single mechanism explains every observation, including the one that had ruled out the first two
hypotheses: **why the loss was independent of the channel.**

> The root cause was confirmed. It is not a bug in either end's code; it is the physical reality of
> one radio carrying two protocols.

This is the sentence to be able to say in a defence. Not everything that breaks is a bug.

### The four fixes

| Issue | Fix | Result |
|---|---|---|
| **I-25** — no way to recover lost frames | Implement `RESEND` (D-26): a 36-byte bitmap of what is missing in a 54-byte request; the node replays exactly those from the same frozen window with the same sequence number | **286/286 with BLE on**, CRC-32 MATCH, and the first end-to-end cry alert |
| **I-26** — a resend request can itself be lost | Send the request **three times** (D-28). Broadcast is never acknowledged, and the request goes out at the moment the radio has been busiest | A lost request no longer costs a round |
| **I-27** — the node served the same request 2–3 times | Dedupe repeats within 800 ms (D-28). With 128 fragments missing, three servings meant 384 fragments of air instead of 128, and a 9.6 s burst instead of 5 | One serving per round; the burst settles in ~5–7 s |
| **I-28** — *"no frozen window for it"* | The node **holds** an uploaded window (D-29), and the hub **abandons** a burst the node can no longer complete, asking for the newer window at once (D-30) | The resend is served; a hopeless burst recovers in ~3 s instead of 15 |
| **The heartbeat came out 16 bytes, not 12** | `crynet_proto_build()` gave the payload-less layout only to a REQUEST; a HEARTBEAT fell through to the full 14-byte header. The far end parses a heartbeat like a request, so **every heartbeat would have been rejected as malformed** and the node's link bar would have sat dark on a hub that was answering. One condition fixes it; `research/test_heartbeat_framing.py` now holds it, and was checked by reverting the fix | The node's link bar is live: `link   [####] -12 dBm (hub frame 445 ms ago)` |

### The fix that made I-27's cure into a new bug

The 800 ms dedupe window was **longer than the hub's own resend round**, which comes about
**670–770 ms** after the last ask. So the node classified *every round after the first* as a repeat
and answered none of them.

> A burst that lost one fragment could never be completed. The hub asked for the missing fragment
> five times, the node answered none of the five requests, the burst sat at 285 of 286 until it timed
> out, and the whole two-second window — the one that held the cry — was thrown away.

The rule became **two-sided**: a repeat must name the same window **and the same fragments** and
arrive within **250 ms**. A round asking for a different fragment is always answered. Comparing the
bitmap is what makes the shorter window safe.

The lesson generalises: *a dedupe window must be shorter than the interval it is deduplicating
against, and identity must be content, not just timing.*

### The live test that closed it

Hub + node + a real BLE client connected, cry recording played through speakers:

```
W (37022) link: node 1: the burst stalled with 268 of 286 fragments; asking for the 18 that are missing
W (38562) link: node 1: the burst stalled with 285 of 286 fragments; asking for the 1 that are missing
I (39830) link: node 1: 286/286 fragments in 6.58 s
I (39830) link: node 1: window crc32 0x336F318E, the node advertised 0x336F318E -> MATCH
...
I (60681) link: node 1: window crc32 0x6230F1C4, the node advertised 0x6230F1C4 -> MATCH
I (60842) link: node 1: ALERT — cry
```

and on the phone:

```
ALERT {'cot': 1, 'alert': 'cry', 'confidence_pct': 100, 'event_id': 1}
STATE {'cots': 1, 'crying_mask': 1, 'confidence_pct': 100, 'started_at_s': 0}
ALERT {'cot': 1, 'alert': 'cleared', 'confidence_pct': 100, 'event_id': 2}
```

Note what that log shows: the mechanism **working as designed**, not a link with no losses. Eighteen
fragments lost, asked for, delivered; then one lost, asked for, delivered; then MATCH. The reliability
is in the repair, not in the absence of loss.

## Reducing the deafness itself (D-61)

Repair made the link correct; it did not make it fast. Three changes made it fast:

1. **The hub advertises only when it must** — not at all while a caregiver's device is connected,
   because nobody needs to *find* a hub that is already connected and the notifications travel over
   the connection.
2. **When it must, at 100 ms** (`ADV_INTERVAL 0x00A0`) instead of NimBLE's fastest default
   (`0x0020` = 20 ms, about 150 radio transmissions a second across the three BLE channels); and at
   **320 ms** (`ADV_INTERVAL_SLOW 0x0200`) while a burst is in the air.
3. **The node paces fragments at ~4 ms** instead of ~10 ms.

**Measured: 5.54–6.93 s before → 2.06–2.11 s after, 286/286 fragments every time, with no resend
rounds.** Request-to-verdict latency 2.23–3.57 s.

The burst-time policy is *slow*, not *silent*, and the reason is a measurement from the bench: in the
busiest session recorded the radio was busy **89 % of the time** — 230 s of burst airtime in a 260 s
session — so a wearable waiting for a gap could take **a minute to attach**. (That session is the
upper bound on airtime, not the two-cot steady state; it has not been re-measured with exactly two
cots transmitting, and Chapter 18 says so.) An advertisement every 320 ms costs the burst a frame or two, and the
resend path recovers them; silence cost the caregiver the device altogether. That is the trade stated
plainly, and it is the right way round — a slightly slower burst is a nuisance, an unattachable
wearable is a failure.

Later sessions gave a wider range — **2.06–5.19 s, median 3.55 s** — because the per-fragment cost is
the *channel's* contention on shared channel 6, not the pacing. The honest figure is a range, and the
reason the range exists is understood.

## The air counters

`-DCRYNET_LINK_PROMISCUOUS=1` enables promiscuous-mode counting: how many frames carrying the CryNet
magic the radio *hears*, against how many the ESP-NOW layer *hands up*. That distinction is what
separates "lost in the air" from "dropped by the hub's own receive path" — the two possibilities that
hypothesis (b) could not distinguish from the node's side alone.

It is off by default in the code and currently enabled in `platformio.ini`, because it is cheap and
the question it answers is the one that keeps recurring.

## Two nodes on one channel

There is no collision-avoidance protocol, no token, no time slots. Two nodes share channel 6 — with
every Wi-Fi network in the building — by three mechanisms:

1. **Telemetry is tiny and rare in bytes** — 32 bytes at 10 Hz ≈ 3.2 KB/s per node.
2. **Bursts are pulled, not pushed.** The hub requests one window at a time, so at most one node is
   ever transferring 64 KB. That is the whole arbitration scheme, and it needs no coordination
   between nodes at all.
3. **Cry mode** stops one node from queuing six windows ahead of itself.

The hub is the scheduler, and it schedules by choosing whom to ask. This is why the pull model was
chosen over a push model, and it is a genuinely elegant answer to a problem that looks like it needs a
MAC protocol.

## What was measured, finally

| Claim | Number |
|---|---|
| Bad frames / bad payloads | **0 / 0** over thousands of frames (hub's own counters) |
| Burst completion with a BLE client connected | **286/286, CRC-32 MATCH** |
| Burst duration | 2.06–5.19 s, median 3.55 s |
| Request → verdict | 2.23–5.35 s, mean 4.03 s |
| Live demo session | 45 bursts, **45/45 complete**, no stall, timeout, CRC error or resend round |