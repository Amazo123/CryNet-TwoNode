# Chapter 7 — The cot node firmware

## What the node is responsible for

`firmware/node/node_crynet/node_crynet.ino` — 1,808 lines of Arduino-framework C++ on the ESP32-C3.
It has five jobs, in strict priority order:

1. **Never miss a sample.** The I²S capture task is the only thing on the node that must not be
   delayed.
2. **Decide when something is worth sending.** The adaptive trigger.
3. **Freeze the right two seconds.** Not the two seconds before the cry, not the two after.
4. **Deliver them intact.** 286 fragments, CRC-16 each, CRC-32 overall, resend on request.
5. **Report itself.** Telemetry at 10 Hz, a serial console, counters.

Everything else on the node is subordinate to those, and several of the hardest bugs in the project
were cases where a lower-priority job interfered with a higher one.

## The audio path

### I²S configuration

```cpp
g_i2s.setPins(PIN_SCK /*4*/, PIN_WS /*5*/, -1 /*no MCLK*/, PIN_DIN /*6*/);
g_i2s.setTimeout(500);
```

The INMP441 needs no master clock — it generates its own from SCK. It is configured **stereo with
both slots**, because the peripheral must be given the whole 64-bit frame; the microphone drives
only the slot selected by its L/R pin (tied to GND = left). The firmware then keeps the **top 16
bits** of the 32-bit slot. Narrowing it any other way would shift the audio by a byte — a mistake
that produces plausible-looking noise rather than an obvious failure.

Sample rate 16 kHz, DMA-backed. `i2s_pump()` reads blocks and writes them into `g_window`, a
32,000-sample ring, advancing `g_write`.

`capture_task` is a bare loop:

```cpp
for (;;) { i2s_pump(); }
```

with the comment *"The read itself paces this task: it returns when the samples have arrived."* No
`vTaskDelay`, no yield — the blocking read is the scheduler.

### Level measurement

Every 100 ms the main loop computes:

- `g_mean` — the running DC estimate;
- `g_rms` — `rms_of_last(mean, n)` over the most recent 100 ms, accumulated in **int64** so 32,000
  squared 16-bit deviations cannot overflow;
- `buffer_rms()` — the same computation over a whole frozen window, used for `g_frozen_rms`.

Both remove the mean first, exactly as the hub's front end does, so the number the node reports and
the number the hub computes describe the same thing.

## The adaptive trigger — D-63

This is the node's most important logic and the one with the clearest empirical justification.

### The problem it solved

The trigger used to be a fixed **0.030 RMS**, the same constant as the hub's. The in-domain confusion
session measured what that meant: **a cry played one metre from the node has median RMS 0.0070, and
not one of its 590 readings reached 0.030.** The system's reach was set by a constant, not by the
classifier. The model never got the chance to be right.

### The rule

```cpp
if (g_floor < 0.0f)      g_floor = g_rms;                    // first reading
else if (g_rms < g_floor) g_floor = g_rms;                    // fall instantly
else                      g_floor += (g_rms - g_floor) * 0.002f;  // rise slowly

g_level = 3.0f * g_floor;
clamp(g_level, 0.005f, 0.030f);
```

| Constant | Value | Reasoning |
|---|---|---|
| `TRIGGER_MULT` | **3.0** | chosen by `research/adaptive_trigger_study.py` over the recorded sessions, not by taste |
| `TRIGGER_MIN` | 0.005 | keeps the level above the microphone's own noise, where a trigger would mean nothing |
| `TRIGGER_MAX` | **0.030** | *exactly the fixed level this replaces* — so the rule is **never worse than before** in a loud room |
| `FLOOR_RISE` | 0.002 | 0.2 % of the gap per reading; ten readings a second ⇒ **50 s time constant** |

The asymmetry — instant fall, 50-second rise — is the whole design. If the floor rose as fast as it
fell, a cry lasting a minute would drag the floor up to its own level and **switch the trigger off
half way through the episode**. The slow rise means a long cry keeps triggering; the instant fall
means the system re-sensitises the moment a room goes quiet.

### The evidence for the multiple

From `adaptive_trigger_study.py` over the recorded sessions:

| Condition | Fixed 0.030 | 3× floor |
|---|---|---|
| Cry at one metre | **0 trigger events/min** | **39** |
| Quiet room | ~0 | 5 |
| Loud sessions | capped at 0.030 | capped at 0.030 (identical) |

Measured on the boards afterwards: the level tracks the room (0.006–0.016 in a noisy room), the node's
log shows it settling (`rms 0.0063 floor 0.0028 level 0.0083`), and the hub went from asking 1–2 times
a minute to 5–11.

### The consequence nobody wanted

A lower trigger asks the model about **near-silent windows**, and the model is not a reliable judge of
those: the same quiet room produced verdicts of **0.0000 and 0.9766** for windows that differ by
nothing a person could hear, and the second was a false alarm.

That is not a model bug to be fixed by retraining — it is a consequence of asking a question the model
was never trained to answer. The fix belongs in the **announcement rule** (D-64, Chapter 10), not in
the trigger. Recognising which layer owns a fault is the difference between a fix and a regression.

### Two consecutive readings

`g_loud_streak` counts consecutive readings at or above `g_level`; a freeze needs **≥ 2**. One 100 ms
transient — a door catch, a chair leg — is not a cry.

## Freezing the right two seconds

A trigger sets `g_peak_pending` and records `g_peak_ms`. The freeze happens when:

```cpp
cry_stopped = (g_loud_streak < 2);
if (age >= PEAK_DELAY_MS || (cry_stopped && age >= PEAK_STOP_DELAY_MS)) {
    if (age < PEAK_EXPIRE_MS) freeze_window();
    g_peak_pending = false;
}
```

| Constant | Value | Meaning |
|---|---|---|
| `PEAK_DELAY_MS` | 2000 | the cap: two seconds *after* the peak, for a cry that goes on |
| `PEAK_STOP_DELAY_MS` | 500 | if the cry **stopped**, freeze after half a second |
| `PEAK_EXPIRE_MS` | 4000 | the peak must still be inside the ring |

The source documents the design space explicitly: `PEAK_DELAY_MS = 0` gives the two seconds *before*
the peak, `500` puts the peak in the middle, `2000` gives the two seconds *after*. The stop-capped rule
takes the best of them: a short cry is captured whole and immediately; a long cry is captured after
two seconds rather than making the system wait for it to end.

`research/simulate_freeze.py` verified that this catches as many of the corpus's cry episodes as the
old peak-centred rule, and that the hub announced no room window under any of the three variants.

`freeze_window()` copies the ring oldest-first, computes `g_frozen_rms` and the **CRC-32 of the exact
bytes that will be uploaded**, and increments `g_burst_seq`.

## Cry mode — D-69

```cpp
if (g_frozen_rms >= 0.05f) g_cry_mode = true;
...
if (g_cry_mode && g_rms < 0.01f && g_loud_streak == 0) g_cry_mode = false;
...
allow_freeze = !g_cry_mode || (g_frozen_rms > 0 && g_rms >= 3.0f * g_frozen_rms);
```

While in cry mode the node will not freeze another window unless a new moment is **three times
louder** than the one it is holding. A sustained cry therefore produces one window, not six queued
ahead of itself.

**The entry threshold is absolute (0.05 RMS), not relative to the floor**, and the reason is worth
being able to give from memory: a quiet room has a floor near 0.001, and 5× that is 0.005 — which
ordinary quiet windows exceed. A relative cry-mode threshold would put a silent room into cry mode
permanently, and the node would then freeze one window and stop listening.

## Protecting a window that is in flight

Three timers, and each exists because of a measured failure:

| Timer | Value | The failure it fixed |
|---|---|---|
| `TRANSFER_HOLD_MS` | 4000 ms, **refreshed on every fragment sent** | a louder moment used to be able to preempt a window mid-burst; the ring overwrote it and *"the burst died with a third of it on the floor"* |
| `FROZEN_HOLD_MS` | **3000 ms** | pure resend coverage after the upload. Was 8000, then 4000 (D-71), now 3000: at 8 s the three-minute session measured **6.5–7.0 s of hold-driven gap between every burst** |
| `FROZEN_EXPIRE_MS` | 20000 ms | five seconds was not enough — the window expired while the hub was still waiting for the pieces it had asked for |

The progression 8000 → 4000 → 3000 tracks the burst getting faster. That is the right way to tune a
timer: measure what it is protecting, and shrink it as the thing it protects shrinks.

## Identity: this node must be 1 or 2

The hub watches two cots and refuses every other id in its receive path, so a node's id is not a
label — it is the difference between being monitored and being invisible.

`CRYNET_COT_COUNT = 2` in the sketch mirrors the hub's `NODE_LINK_MAX_NODES`. The id is set over the
serial console (`id 1`, `id 2`) and stored in **NVS**, so it survives a reflash. A node left on a
MAC-derived id outside 1..2 prints a warning at boot rather than silently failing to be heard.

That last sentence is the whole reason the warning exists. Without it the symptom is *"the hub does
not see my cot"*, and the natural places to look are the radio, the channel, the antenna and the
microphone — all of which are fine. On the bench both ids were checked **after** flashing, not before:
COM31 came up with derived id 1 and COM37 with its saved id 2, which is the check that matters because
the id lives in NVS and a flash could have cleared it.

## The node's own view of the link

The node keeps `g_hub_rssi` and `g_hub_rssi_ms`: the RSSI of the last frame **the hub** sent, and when
it arrived. The filter is the important part:

```cpp
if (info != NULL && info->rx_ctrl != NULL &&
    (data[2] == LINK_TYPE_REQUEST || data[2] == LINK_TYPE_HEARTBEAT ||
     data[2] == LINK_TYPE_RESEND)) {
    g_hub_rssi = (int8_t)info->rx_ctrl->rssi;
    g_hub_rssi_ms = millis();
}
```

Everything on channel 6 is broadcast, so this node also hears the *other* cot's telemetry and its
286-fragment bursts. The first version of this code took the RSSI of any frame it heard, which would
have reported the loudest transmitter in the room and labelled it "the hub" — a link bar that reads
full while the hub is unplugged. Restricting it to the three hub-only frame types is what makes the
reading mean what its label says.

The hub's heartbeat is what keeps the reading live between pulls: it arrives once a second whether or
not any audio is wanted. `status` prints it as a bar on the same scale the panel uses:

```
link   [####] -12 dBm (hub frame 445 ms ago)
```

| Bars | Threshold |
|---|---|
| 4 | ≥ −60 dBm |
| 3 | ≥ −70 dBm |
| 2 | ≥ −80 dBm |
| 1 | ≥ −90 dBm |
| 0 | below −90, or no reading (`0` is the sentinel for "never heard") |

Both ends of the link now show a bar, and **they measure different directions**: the node's bar is
the hub's transmitter as heard at the cot, the panel's bar is the cot's transmitter as heard at the
hub. On the bench they read −12 dBm and −23 dBm for the same cot. That is not a contradiction; the
two transmitters run at different powers (the node is deliberately at 8.5 dBm, D-65) and sit in
different noise environments.

There is **no connection LED** (D-83). `SYSTEM_WIRING.md` §5.1 used to specify one on GPIO10, lit
while a valid heartbeat had arrived inside a timeout. It worked and it was removed: the hub's panel
already says which cots are answering, and a second, slower copy of the same answer on the cot itself
was saying it in a place nobody was looking. The heartbeat and its reading stay — they are how the
node knows the hub is there — and GPIO10 is free.

## The I²S zero watchdog — D-79, committed, not yet flashed

A microphone that has stopped producing data does not produce an error. It produces **zeros**, and
zeros look exactly like a very quiet room: RMS 0.0000, no trigger, no burst, no alert. The system
fails silent, which for a monitor is the worst way to fail.

The watchdog counts *consecutive exact zeros*:

```cpp
static const uint32_t I2S_ZERO_LIMIT = SAMPLE_RATE * 5u;   /* five seconds */
...
if (s == 0) { if (g_zero_samples < I2S_ZERO_LIMIT) g_zero_samples++; }
else if (g_zero_samples < I2S_ZERO_LIMIT) { g_zero_samples = 0; }
```

Five seconds of exact zeros is not a quiet room — a live INMP441 always has noise in its low bits. On
reaching the limit the node tears down and restarts I²S from its owning task, marks the live ring
damaged so no half-real window can be frozen, and increments `g_i2s_restarts`. **A frozen upload is
deliberately left intact**: a window already in flight is real audio and must not be destroyed by a
recovery. If the teardown or the warm-up fails, the node reboots rather than reusing handles the
driver may have invalidated.

Two honest limits on this code, both recorded as O-1c:

- it detects **exact** zeros only. A microphone that fails to a stuck DC value or to low-level noise
  is not caught.
- the fault-injection test proved the code executes and refills a window; it did **not** prove it
  recovers the original physical fault, because the original fault has never been reproduced on
  demand.

It is committed but **not flashed** (D-79): the owner is soldering the final wiring, and a node should
not be reflashed mid-solder. After it goes on, it needs a played-cry end-to-end run to confirm the node
still streams and the hub still hears it.

## The radio

### Channel and power

`LINK_CHANNEL = 6`, set with `esp_wifi_set_channel()` **after** `esp_now_init()`. Both sides must
agree; ESP-NOW does not negotiate.

TX power **8.5 dBm** (D-65), down from the 20 dBm default. The radio sits centimetres from the
microphone and was putting its own noise into the audio it was about to be judged on. Five minutes of
a noisy room after the change: **32 verdicts, 0 false alerts**.

`esp_wifi_set_ps(WIFI_PS_NONE)` — modem sleep disabled. A node that sleeps between beacons misses
requests.

### The peer rule — the bug that wedged the radio

```cpp
static volatile bool g_hub_peer_pending = false;
```

> Set from the receive callback, acted on in the loop: the callback runs in the WiFi task, and
> `esp_now_add_peer()` waits for that very task, which wedged the radio — the send callback stopped
> firing and every `radio_send` burned its two-second cap. The hub's `node_link` carries the same
> rule: peers are added from a normal task.

This is a deadlock, not a race: the callback is *in* the task that `esp_now_add_peer()` blocks on.
Both firmwares now defer peer registration to a normal task. It is the single most transferable
lesson in the codebase for anyone writing ESP-NOW.

### Broadcast and unicast

Telemetry is broadcast to `FF:FF:FF:FF:FF:FF`. The burst is **unicast to the hub**, whose MAC the node
learns from the first request it receives — *"a broadcast destination is filtered more aggressively
by the receiver's radio."*

### The transmit queue

ESP-NOW's queue is **ten frames deep**. A burst is 286 fragments; handing them all over at once would
lose every frame past the tenth, permanently.

The first implementation waited for each frame's own acknowledgement before handing over the next.
That cost **~12 ms per fragment — 3.5 seconds for a burst**, which was most of the system's response
time.

The current implementation keeps up to `TX_INFLIGHT_MAX = 4` frames in the radio at once:

```cpp
g_tx_queued++;                     // handed over
on_send: g_tx_acks++;              // actually left
         if (status != OK) g_tx_failed++;
radio_wait_room(): while (inflight() >= 4) wait;
```

Four, not ten, for two reasons stated in the source: it leaves room for the telemetry and heartbeats
that share the queue, and it keeps the far end's receive queue from overflowing — one fragment in
three hundred was being lost on the way to the hub, and the far end's queue overflowing was the
likeliest cause.

`g_tx_failed` counts frames the radio itself could not carry. **The callback's status used to be
thrown away**, so this was always zero and the node reported a clean sheet even while the radio was
dropping its burst. A counter that cannot fail is not a counter.

### The resend dedupe — the most expensive line in the firmware

The hub sends each request three times because a broadcast is never acknowledged. The node must
answer once. The dedupe window was **800 ms** — and the hub's own resend round comes about
**670–770 ms** after the last ask. So the node threw away *every round after the first* as a repeat.

The consequence, quoted from the source:

> A burst that lost one fragment could never be completed. The hub asked for the missing fragment
> five times, the node answered none of the five requests, the burst sat at 285 of 286 until it timed
> out, and the whole two-second window — the one that held the cry — was thrown away. A burst that is
> one frame short is the *commonest* failure on a weak link, so this was the single most expensive
> line in the firmware.

The rule is now **two-sided**:

```cpp
RESEND_DEDUPE_MS = 250;
repeat = (same seq) && (same bitmap) && (within 250 ms);
```

A round asking for a *different* fragment is a new round and is always answered. The bitmap
comparison is what makes shortening the window safe.

## Framing

| Type | Value | Direction | Payload |
|---|---|---|---|
| `TELEMETRY` | 1 | node → hub | 32 bytes: id, seq, rms, floor, level (milli-RMS), frozen rms/peak, counters |
| `FRAGMENT` | 2 | node → hub | index, total, **224 bytes**, CRC-16 |
| `REQUEST` | 3 | hub → node | the sequence number wanted |
| `HEARTBEAT` | 4 | hub → node, 1 Hz | nothing — a 12-byte frame whose only job is to give the node an RSSI reading of the hub |
| `RESEND` | 5 | hub → node | seq + **36-byte bitmap** (286 bits), in a 54-byte frame |

`FRAG_PAYLOAD = 224`, `FRAG_COUNT = ceil(64000 / 224) = 286`.
`RESEND_BITMAP_BYTES = ceil(286 / 8) = 36`.

CRC-16/CCITT-FALSE per fragment (check vector `0x29B1` for `"123456789"`), CRC-32/IEEE 802.3 over the
whole window — the same polynomial as `zlib.crc32`, which is what lets a host tool verify a capture
with one line of Python.

Battery telemetry was removed with D-83: the payload went **34 → 32 bytes**.

## The serial console

The node answers on the same USB serial it logs to. Commands include `status`, `stats`, `burst` (dump
the frozen window in the radio's framing), `dump` (the raw window, for
`firmware/tools/dump_node_window.py`), and the trigger controls.

**`Serial.setTxTimeoutMs(0)` is critical** (I-11). Without it, a `Serial.print` with no host attached
blocks for the full USB CDC timeout — and on a node whose capture task must never stall, that is a
dropped-audio bug that only appears when nobody is watching.

## Build

Arduino CLI (bundled), ESP32 core **3.3.12**, FQBN **`esp32:esp32:weact_studio_esp32c3`** — the WeAct
Studio ESP32-C3 board definition, which targets the **chip** rather than one module — it is
the right entry for the **Pro Mini** on the cot and the SuperMini on the wrist alike. The current
build compiles to **983,177 B (75 %) of flash, 166,404 B (50 %) of static RAM**, out of the
1,310,720 B app partition and 327,680 B of RAM.

> **A figure that was wrong in an earlier edition.** The stage-2b entry of 2026-10-30 records the
> node at **977,617 B (74 %) / 165,972 B (50 %)** — the size of the sketch on the day it was first
> compiled. That number was carried forward into the earlier dossier as if it were current. It is
> not: the sketch has been rebuilt many times since (the burst rework, the serial-set id that
> persists in flash, the I²S watchdog, D-83 taking the battery sense and the LEDs out). The figure
> above was measured on 2026-11-23 by compiling the tree as it stands, and it is unchanged by the
> board swap — a comment-only edit to the header compiles to the identical bytes of program storage.

`firmware/tools/flash_node.py` is the one-command flasher; `install_sketches.py` places the sketches
where the Arduino CLI expects them.