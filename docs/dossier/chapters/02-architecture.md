# Chapter 2 — Architecture and the end-to-end path

## Why the system is split the way it is

There are three plausible ways to build a multi-cot cry monitor on ESP32-class hardware, and the
project chose the third. It is worth being able to argue all three, because the choice is the
foundation everything else rests on.

**Option 1 — every node runs the model.** Each cot node captures, computes features, runs the
network, and sends a one-byte verdict. Radio traffic is trivial. It fails for three reasons. The
ESP32-C3 is a single-core RISC-V part at 160 MHz with 400 KB of SRAM and no PSRAM: the 81 × 64 feature
plane, the tensor arena and the audio buffer together do not fit comfortably alongside a Wi-Fi radio
and an I²S driver. Second, one copy of a model per cot is one copy per cot to keep in step: every
retrain means reflashing battery units that are physically attached to cots. Third, arbitration
between cots — *which* cot is crying, which one is louder — needs a place where both verdicts
exist at once, and that place would have to be invented anyway.

**Option 2 — every node streams continuously to the hub.** The hub gets everything and decides
everything. This is the simplest firmware and the worst system. Two nodes × 16,000 samples/s ×
2 bytes = 64 KB/s of sustained radio traffic on a link whose measured practical throughput is roughly
31 KB/s for one node bursting alone. It does not fit by a factor of two, before contention — and one
node streaming alone already uses the whole link. It also destroys battery life: the node's radio
would be transmitting continuously.

**Option 3 — the nodes decide *when*, the hub decides *what*.** Each node runs a cheap energy
detector against its own adaptive noise floor. Only when something crosses the floor does it freeze
two seconds of audio and ship them. The hub — an ESP32-S3 with two cores at 240 MHz and 8 MB of PSRAM —
does the expensive part once, for whichever cot asked. Radio traffic becomes bursty and rare, the
model lives in exactly one place, and arbitration is natural because every verdict is computed in the
same address space.

That is CryNet. The cost of the choice is that the node's trigger is a *gate on recall*: a sound the
node never triggers on can never be classified, no matter how good the model is. This is not a
hypothetical cost — it was measured, and it is the reason the adaptive trigger exists (D-63, Chapter 7).

## The five hardware pieces

| Piece | Part | Why this part |
|---|---|---|
| Cot node ×2 | ESP32-C3 **Pro Mini** | Cheapest ESP32 with Wi-Fi (needed for ESP-NOW) and an I²S peripheral; 4 MB flash; native USB (`303A:1001`) on board. The owner's stock board, swapped in and verified live on 2026-11-02 |
| Microphone ×2 | INMP441 breakout | Digital I²S MEMS: no analogue path, no preamp, no ADC noise, no gain to calibrate. Fixed −26 dBFS sensitivity |
| Hub | ESP32-S3-DevKitC-1 N16R8 | Dual core, vector instructions used by ESP-NN, 8 MB octal PSRAM for the tensor arena and audio, 16 MB flash |
| Panel | 2.8" ILI9341, 320 × 240, SPI | Big enough for two full-width cot cards with a level bar and a signal bar each; a ubiquitous, well-documented controller |
| Wearable | ESP32-C3 **SuperMini** + SSD1306 128 × 64 OLED + coin ERM | The *same chip* as the cots, on the SuperMini board the cots used before the swap — so one toolchain and one FQBN still cover all three C3 units. BLE client, tiny display, a motor a caregiver cannot ignore |

## The path a cry takes, step by step

What follows is the whole system in sequence, with the real constants. Every stage named here has its
own chapter.

### 1. Capture (node, continuous)

The INMP441 is clocked by the node's I²S peripheral at 16 kHz, 32-bit slots, left channel. Samples
arrive in DMA-backed blocks and are pumped into a ring buffer of `int16` holding the last two seconds
— 32,000 samples, 64,000 bytes. The top 16 bits of each 32-bit slot are the sample; the microphone
produces 24-bit data left-justified in the slot, and the firmware keeps the top 16.

`capture_task` runs continuously. Nothing else on the node blocks it: this is the one job that must
never miss a sample, because a gap in the audio is indistinguishable from a sound.

### 2. Level and floor (node, every 100 ms)

Every 100 ms the node computes the RMS of the most recent 100 ms of audio, `g_rms`. It maintains a
noise floor `g_floor` that **falls immediately** when the room gets quieter and **rises slowly**
when it gets louder — an exponential update, `g_floor += (g_rms - g_floor) * 0.002f`, a time
constant of about 50 seconds. The trigger level is `g_level = 3.0 × g_floor`, clamped to
`[0.005, 0.030]`.

The asymmetry is deliberate and is the single most important line in the node: if the floor rose as
fast as it fell, a sustained cry would drag the floor up to its own level within a second or two and
the node would stop triggering *in the middle of the cry*. A slow rise means a long cry keeps
triggering; a fast fall means the system re-sensitises the instant a room goes quiet.

Two consecutive readings at or above `g_level` constitute a trigger. Two, not one, because a single
100 ms transient — a door catch, a chair leg — is not a cry.

### 3. Freeze (node)

A trigger does not freeze immediately. The node marks a **peak pending** and waits, so that the two
seconds it eventually freezes are *centred* on the cry rather than ending at it:

- `PEAK_DELAY_MS` = 2000 ms — the cap for a cry that goes on;
- `PEAK_STOP_DELAY_MS` = 500 ms — if the loud streak breaks first (the cry stopped), freeze after only
  half a second, so the window holds the cry that just ended rather than the room behind it;
- `PEAK_EXPIRE_MS` = 4000 ms — the peak must still be inside the ring when the freeze happens.

`research/simulate_freeze.py` checked this stop-capped rule against the corpus: it catches as many cry
episodes as the old peak-centred rule, and the hub announced no room window under any of the variants
tested.

The freeze copies the ring into `g_frozen`, oldest sample first, and records `g_frozen_rms` (the
window's own RMS with its mean removed — the same computation the hub's front end does), the CRC-32 of
the exact bytes that will be uploaded, and a new burst sequence number.

Three timers then protect that window:

| Timer | Value | Job |
|---|---|---|
| `FROZEN_HOLD_MS` | 3000 ms | pure resend coverage after the upload; cut from 4000 when the burst got faster (D-71) |
| `TRANSFER_HOLD_MS` | 4000 ms | protection while the burst is in the air, **refreshed on every fragment sent** |
| `FROZEN_EXPIRE_MS` | 20000 ms | how long an unserved window may sit before it is dropped |

If `g_frozen_rms >= 0.05` — five times the floor — the node enters **cry mode** (D-69): it will send
one window per cry episode rather than one per trigger, exiting when `g_rms < 0.01` and the loud
streak is zero. This stops a single long cry from producing a dozen redundant bursts.

### 4. Offer (node → hub, telemetry at 10 Hz)

The node broadcasts a 32-byte telemetry frame ten times a second on ESP-NOW channel 6. It carries the
node's id, sequence number, `g_rms`, `g_floor`, `g_level` (as milli-RMS), the frozen window's own RMS
and peak, and counters. Telemetry is the node's *advertisement*: "I have window *n*, and here is how
loud it was."

Telemetry is **broadcast**; the 286-fragment burst is **unicast to the hub**, whose MAC the node
learns from the first request it receives — a broadcast destination is filtered more aggressively by
the receiver's radio than a unicast one. Broadcast telemetry at 10 Hz costs about 3.2 KB/s of airtime
per node and is the heartbeat the hub's liveness display is built on.

### 5. Pull (hub → node)

The hub reads the telemetry. If the advertised window is new, and its RMS crosses the trigger level
the node reported (falling back to `CRYNET_TRIGGER_RMS` = 0.030 for an older node), and the hub is not
already busy, it sends a REQUEST naming that sequence number. This is the *pull* model: the hub, not
the node, decides when the channel is used for a 64 KB transfer. That is what makes two nodes
share one channel without a collision-avoidance protocol.

### 5b. Heartbeat and the two link readings (hub ↔ node, 1 Hz)

The hub broadcasts a **heartbeat once a second** — `node_link_send_heartbeat()`, a twelve-byte frame
of type 4 that asks for nothing. It exists for one reason: a node cannot measure the strength of a
link it never receives on. The node records the RSSI of the last frame *the hub* sent and prints its
own four-bar view of the link on its serial console.

Only the hub's own frame types count towards that reading — a REQUEST (3), a HEARTBEAT (4) or a
RESEND (5). Everything on channel 6 is broadcast, so a cot also hears the *other* cot's telemetry and
window fragments; taking the RSSI of any frame would report the loudest cot in the room and call it
the hub. That distinction is a bug that was caught before it shipped, and a host test now holds it
(`research/test_heartbeat_framing.py`).

In the other direction the hub records the RSSI of each cot's telemetry (`slot->tel_rssi`), carries it
through `link_stage` into the display state, and draws it as a four-bar glyph on that cot's card. Both
ends therefore show a link reading, and they are readings of *different* directions — which is why
they disagree by tens of dB on the bench and why that disagreement is not a fault.

### 6. Burst (node → hub, 286 fragments)

The node splits the 64,000-byte window into 286 fragments of 224 payload bytes each (the ESP-NOW
maximum frame is 250 bytes; the protocol header and CRC-16 take the rest). Each fragment carries:

- the node id and window sequence number,
- the fragment index and total,
- a **CRC-16/CCITT-FALSE** over that fragment's payload,
- the payload bytes.

The last fragment also carries the **CRC-32 (IEEE 802.3)** of the whole 64,000-byte window — the same
polynomial as `zlib.crc32`, which is what lets a host-side Python tool verify a capture without
reimplementing anything.

Fragments are paced at roughly 4 ms. The transmit queue is 10 deep with at most 4 frames in flight;
`on_send` releases a slot. The node's radio runs at **8.5 dBm**, not the 20 dBm default: at 20 dBm the
transmitter, sitting centimetres from the microphone, put its own noise into the audio that was about
to be judged (D-65).

### 7. Reassemble and repair (hub)

The hub allocates a 64,000-byte buffer per burst and a 286-bit received bitmap. Each arriving fragment
is CRC-16 checked; a bad fragment is dropped and its bit left clear. When fragments stop arriving for
`FRAG_STALL_MS` (100 ms, adaptive up to 1500 ms) the hub sends a **RESEND** frame — type 5, a 54-byte
request carrying a 36-byte bitmap of exactly what is missing. It sends it three times, because the
request itself is not acknowledged. The node replays only the missing fragments, and deduplicates a
request only when it names **the same window and the same fragments** and arrives within
`RESEND_DEDUPE_MS` = 250 ms. Up to `RESEND_MAX_ROUNDS` = 10 rounds. (That dedupe rule was once 800 ms
and one-sided, and it silently destroyed every burst that lost a single fragment — see Chapter 7.)

When all 286 bits are set the hub computes the CRC-32 of the reassembled window and compares it with
the value the node sent. `CRC32 MATCH` in the log is the proof that the two seconds of audio in the
hub's memory are bit-for-bit the two seconds the microphone heard. **Measured: 286/286 with CRC-32
MATCH, repeatedly, including with a BLE client connected.**

If the node advertises a *newer* sequence number mid-burst, the hub abandons the old burst rather than
chasing a window the node has already overwritten.

### 8. Refuse if clipped (hub)

Before any DSP: if any sample in the window has magnitude ≥ `CRYNET_CLIP_PEAK` = 31000 (of 32767,
i.e. 0.946 of full scale), the window is **refused outright**. No features, no inference, no verdict.

The reason is physical. The INMP441 is a fixed-gain digital microphone: −26 dBFS ±3 dB, and its L/R
pin selects the channel, not the gain. When the sound pressure exceeds what it can represent it
flat-tops *inside the microphone*, before the 16-bit window ever sees it. A clipped window is not a
loud cry — it is a distorted waveform whose harmonics are an artefact of the clipping, and the model
has never been trained on that artefact. There is no software cure. The correct behaviour is to
refuse the corrupted evidence and let the *other* cot — the bystander that heard the same cry from
further away, unclipped — announce it. That is exactly what happens on the bench.

### 9. Front end (hub, 41.7 ms)

The frozen contract, D-11, executed in C:

1. `int16 pcm[32000]` → float, divided by 32768.
2. Subtract the mean, computed as an exact `int32` sum before division (so the DC removal is identical
   to Python's, not merely close).
3. Zero-pad 256 samples at the front and 512 at the rear — this reproduces librosa's `center=True`
   reflect-padding count for this configuration and gives exactly 81 frames.
4. 81 frames of 512 samples, hop 400, each multiplied by a **symmetric** Hann window.
5. Real FFT → 257 magnitude-squared bins.
6. 64 Mel bands, **slaney** normalisation, 20 Hz–8 kHz, 497 non-zero weights.
7. `10·log10(max(P, 1e-10))`, floored at −80 dB.
8. Per-window CMVN: subtract the mean of the whole 81 x 64 plane and divide by its standard
   deviation (plus 1e-6), so the plane arrives at the network with mean 0 and variance 1.
9. Quantise to INT8 with the model's input scale and zero-point.

Every one of those constants is a `_Static_assert` away from being wrong: `crynet_dsp.c` carries
**eight** compile-time guards (lines 35–42) that fail the build if the deployed model's input or
output scale, either zero-point, the silence gate, the sample count, the frame count or the mel band
count drift from what the C code assumes.

**Measured parity against the Python front end: maximum absolute difference 6.9 × 10⁻⁵ over four
probe windows.** That is float rounding, not a disagreement.

### 10. Inference (hub, 101.8 ms)

The INT8 model — 137,384 bytes, 122,770 parameters — runs on TensorFlow Lite Micro with ESP-NN's
SIMD kernels, in a 262,144-byte tensor arena of which 108,328 bytes are actually used, allocated in
PSRAM. Output: two INT8 values, dequantised and softmaxed to `[P(no_cry), P(cry)]`.

The output saturates at **P(cry) = 0.9961** for a clear cry. That number matters enormously for the
alert policy: it means a threshold of 0.99 is *just* below saturation, and it means a threshold change
cannot separate a confident true cry from a confident false one — they carry the identical value.

### 11. Announce (hub)

A verdict is not an alert. The announcement rule (D-64, D-74) is:

```
audible      = rms >= CRYNET_ANNOUNCE_MIN_RMS          (0.006)
unmistakable = audible && !clipped
               && (rms >= 0.080 ? p_cry >= 0.99 : p_cry >= 0.99)
               && (rms >= 0.020 || crest >= 3.5)
confirmed    = unmistakable || (cry_run >= 2 && rms >= 0.020)
```

In words: one window announces on its own only if the model is essentially saturated *and* the window
carries real energy or a cry-like crest factor. Anything less is a *maybe*, and a maybe must be
confirmed by a second consecutive window. A cry lasts seconds and its windows agree; a noise
fluctuation that happens to look like a cry does not repeat.

This rule exists because the adaptive trigger, by design, asks the model about near-silent windows —
and the model is not a reliable judge of those. The same quiet room produced verdicts of 0.0000 and
0.9766 for windows that differ by nothing a person could hear. The rule, not the model, is what makes
that safe.

### 12. Hold and arbitrate (hub)

A confirmed cry is held for `CRY_HOLD_MS` = 8000 ms. The alert names the loudest crying cot, and it
takes a **1.5× loudness margin sustained for 1500 ms** (`COT_SWITCH_MARGIN`, `COT_SWITCH_DWELL_MS`)
before the panel will switch its primary label to a different cot. Without hysteresis, two cots
hearing the same cry at similar levels make the label flicker between them — which is exactly the
symptom the dwell timer removes. With two cots this is not an edge case: one baby, two microphones,
one cry, and the two RMS readings are within a few dB of each other whenever the cots are a metre
apart.

The alert therefore names **one** cot — the loudest — and that is deliberate: one cry must be one
buzz. The state characteristic still carries the whole crying bitmask, so the information is not lost
— and since **D-86** the wrist's alert face reads that mask and lists every crying cot, unioned with
the cot the alert named. **The packet and the buzz stay one-cot; the screen does not.**

### 13. Publish (hub → wearable, BLE)

Two GATT characteristics on service `19b10000-e8f2-537e-4f6c-d104768a1214`:

- **Alert** `19b10001-…`, 6 bytes: `cot_id`, `alert_type` (1 = cry, 2 = stopped, 3 = deaf),
  `confidence_pct` (u16), `event_id` (u16).
- **State** `19b10002-…`, 8 bytes: `cots`, `crying_mask` (bit 0 = cot 1), `deaf_mask`,
  `confidence_pct`, `started_at_s` (u32).

This contract is **frozen legacy**: the wearable was written against it before the rebuild, and it was
kept byte-for-byte so the two halves could be developed independently. That is a real engineering
decision with a real cost — `alert_type` has one value for "cry", which is why the model is binary
(D-1).

### 14. Announce to the human (wearable)

The wearable's notify callback parses the packet, sets the alert face, and starts a 2.5-second haptic
pulse train on GPIO7 through a BC547 low-side switch, with a 22 Ω stall cap in the motor's positive
lead and a 1N5819 flyback diode across it (D-77, D-85). The alert face holds for 60 seconds and names
the cot the alert carried.

## Timing budget

| Stage | Time | Source |
|---|---|---|
| Trigger decision | up to 200 ms (two 100 ms readings) | node design |
| Telemetry to hub | ≤ 100 ms (10 Hz) | node design |
| Burst, 286 fragments | 2.06–5.19 s, median 3.55 s | measured, D-61/D-62 |
| Front end | 41.7 ms | measured on chip |
| Inference | 101.8 ms | measured on chip |
| Request → verdict, end to end | 2.23–5.35 s, mean 4.03 s | measured, D-62 |
| Panel shows the cry | ≈ 2.5 s after the sound in the good case | measured, D-61 |

The burst dominates. It is not the pacing that sets its length — it is contention on channel 6, which
is shared with every Wi-Fi network in the building. That is why the same firmware gives 2.06 s on a
quiet channel and 5.19 s on a busy one, and why the honest figure is a range and not a number.

## What runs where, in memory

| Allocation | Size | Where | Why |
|---|---|---|---|
| Node audio ring | 64,000 B | internal SRAM | DMA target, must be internal |
| Node frozen window | 64,000 B | internal SRAM | held 4 s for resend |
| Hub burst buffer | 64,000 B per active burst | PSRAM | large, not latency-critical |
| Hub tensor arena | 262,144 B reserved / 108,328 B used | PSRAM | the single largest allocation |
| Hub feature plane | 81 × 64 floats | PSRAM | intermediate |
| Hub framebuffer | 320 × 240 × 2 = 153,600 B | PSRAM | full-frame redraw |
| Hub boot probe buffers | large, temporary | PSRAM, **freed after probes** | D-39/D-40 |

The boot-only buffers are the reason the hub's RAM figure went from **59.9 % (196,140 B) to 12.9 %
(42,236 B)** — the current build reports **13.0 % RAM, 63.6 % flash**, the small difference being the
cot-count and RSSI fields the two-cot link layer added. They exist to prove the DSP and the model agree with the host at startup; once proven
they are dead weight, and freeing them is what leaves room for the radio and Bluetooth to coexist.

Initialisation order is **radio → Bluetooth → display**, and it is not arbitrary: each of those
subsystems takes a large, permanent bite of *internal* heap, and the display's framebuffer must go to
PSRAM. Free internal heap through the sequence: 298,763 B at boot → 290,791 B after probes →
215,155 B with the radio up → 149,271 B with Bluetooth up. Getting the order wrong starves the last
subsystem to start, which is how the BLE stack failed to initialise in an early build.