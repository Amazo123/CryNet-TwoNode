# Chapter 19 — Limitations, open items, and what to do next

## Why this chapter exists

A dossier that lists only what works is a brochure. The value of this document is that it can be
defended, and a defence is only credible if it knows where the ground stops. This chapter is the
boundary of the evidence: what has **not** been measured, what is **open**, what the project
**knowingly gave up**, and what the next person should do about each.

Three kinds of thing appear here, and they are different:

1. **Open items (O-n).** Work that was identified and deferred. Each has a reason it is still open.
2. **Unmeasured things.** Work that was never attempted, or attempted and abandoned without a
   result. These are the honest holes.
3. **Knowingly-given-up things.** Things the project decided *not* to do, and accepted the cost of.
   These are not open — they are closed decisions with a price attached.

The record's O-list was written before the system existed in its present form, so it is out of date
in places. Where that has happened, both the original wording and the current status are given. The
two-cot work also added five sub-items of its own - **O-1a … O-1e** - which are part of the
repository's record and are covered here alongside the original nine.

---

## 1. The open items, and where each one stands today

### O-1 — "the wearable does not exist yet" — **CLOSED**

*Original wording:* "The wearable (Stage 2d) does not exist yet."

**Status: closed, and recorded as O-1a.** `firmware/wearable/wearable_crynet/` was written, flashed
and verified. It is a BLE client against the hub's GATT server with an SSD1306 OLED (SDA 5, SCL 6) and
a BC547 low-side haptic drive on GPIO7 (D-77). On **2026-11-06** three alert cycles in a row came
through complete, the haptic fired, and the unit recovered from a hub reset mid-link. Chapter 8 is the
full description.

What O-1 gated was the wearable as a bench artefact, and that is done. What it did **not** gate is
battery *runtime*: the unit has run on its pouch, but nobody has timed it (O-1d). The alert face now
names **every** crying cot (D-86, which closed O-1b); the alert packet and the buzz still name one.

### O-2 — the model has never heard a real infant cry — **STILL OPEN, and it is the largest one**

*Original wording:* "The only cry source available in this room is a *recording played through a
phone speaker* — compressed, band-limited and EQ'd by the speaker."

**Status: still open. This is the single most important caveat in the project.**

Everything the model has been measured against is one of:

| Positive class | What it physically is |
|---|---|
| ICD (13,330 clips) | 16 kHz recordings of infants, from three source corpora, at their original levels |
| cry4 (4,871 clips) | 16 kHz, LUFS-normalised, VAD-trimmed real infant cries |
| ESC-50 `crying_baby` (40 clips) | 16 kHz, held out entirely as a cross-domain test |
| The room sessions (session 9, 10) | **a phone loudspeaker playing one of the above**, at 15 cm and at 1 m |

The **negatives** are authentic: this room, this INMP441, this microphone, this gain, this noise
floor. The **positives** in the *room* are a proxy. A phone speaker in a plastic case applies a
band-limited, compressed, EQ'd response, and it removes exactly the low-frequency detail that
distinguishes a cry from other vocal sounds. A model trained on clean 16 kHz corpus audio and
tested on speaker-played audio is being tested on a corrupted version of its training
distribution; the fact that it still scores 0.9961 on that corruption says the signal it keys on
survives the corruption, but it does not say what happens on a real infant in a real cot.

**What would close it.** Fifty to a hundred real clips: ten infants × several cries, recorded with
`node_capture` on the actual INMP441 in the actual room, plus room negatives in the same takes.
The tooling already exists — `firmware/tools/collect_clips.py` records, `firmware/tools/label_session.py
--truth` labels by ground truth rather than by loudness, and `research/CONFUSION_SESSION.md`
documents the procedure. Those clips then go into the notebook as a custom corpus, and the whole
notebook is re-run.

**Why it has not been done.** It needs a baby and a quiet room, and it needs consent. It is not a
software problem.

### O-3 — one photograph of the panel with the room lit — **STILL OPEN, and it is now cosmetic**

*Original wording:* "What is still wanted is one photograph **with the room lit**, so the ramp
yields the panel's own tone curve instead of a colour choice."

**Status: still open, but the consequence has shrunk.** The panel's palette was set from the
colour-check page judged by eye (D-55) and then from a dark-ramp photograph the user read (D-57,
D-59). The measurement shows this panel *lifts the dark end and lifts the blue channel hardest*,
and the palette compensates for that deliberately (Chapter 14, Round 5).

What a lit-room photograph would add is the panel's tone curve — whether the shipped palette is
correct in a lit room, not only on a dark one. It is a one-minute job with a camera and it is the
last thing that would settle the display's colours. It does not affect detection, alerting or any
number in this dossier.

### O-4 — the tensor arena is still in PSRAM — **STILL OPEN, and deliberately so**

*Original wording:* "Moving it into internal SRAM is the obvious next optimisation. At 101.8 ms of
inference per two-second window it is not urgent for a triggered monitor."

**Status: still open.** The arena is 262,144 bytes reserved, 108,328 used, and it lives in PSRAM.
The front end's scratch buffers were moved *out* of PSRAM into internal SRAM for exactly this
reason — it took the front end from 135 ms to 41.7 ms — so the same treatment has not yet been
applied to the arena.

The reason it was left alone is the memory arithmetic. Hub RAM after the PSRAM move is **12.9 %
(42,236 B)** of 512 KB, and the free internal heap with Bluetooth up is **149,271 B**. A 262 KB
arena does not fit in 149 KB. Options are (a) shrink the arena to what is actually used — 108 KB
fits, but the allocator's peak is not the reserved size and the difference is not free), (b) use
`AllocateTensors()` failure as a fallback to PSRAM, or (c) leave it. At 101.8 ms for a window that
is only analysed after an event has already been triggered, (c) is defensible. It is listed here
so that nobody later mistakes it for an oversight.

### O-5 — the in-domain audio is speaker-played, not real — **STILL OPEN, and it is O-2 from the other side**

*Original wording:* "A real cry in this room, recorded with `node_capture`, is the honest test of
whether the system works in the real room."

**Status: still open.** This is the same hole as O-2 seen from the measurement side rather than
the training side. O-2 is "the model has never trained on a real cry"; O-5 is "the system has never
been evaluated on a real cry". They close together and with the same 50–100 clips.

### O-6 — the distance curve — **STILL OPEN**

*Original wording:* "The phase cues did not line up in the earlier attempt, so the far-side
measurement has to be repeated."

**Status: still open.** The system has two known points on the distance curve and one hard limit
between them:

| Distance | What happens | Evidence |
|---|---|---|
| **15 cm** (the realistic case — the mic is *in* the cot) | trigger fires, model scores 0.9961, alert raised | D-60, D-61, live sessions |
| **1 m** | **0 of 590 records cross the trigger** — the model is never asked | D-60, session 10 |

The 1 m result is not a model failure: asked anyway, the model would have caught 18 of 44 windows.
It is a *reach* limit set by `CRYNET_TRIGGER_RMS` (0.030) and the INMP441's fixed −26 dBFS ±3 dB
sensitivity with no gain strap. The node's adaptive trigger (D-63, 3× the running floor) partly
addresses it, and on the boards afterwards the hub asked 5–11 times a minute instead of 1–2 — but
a *continuous* distance curve has never been measured. The earlier attempt failed because the
phase cues did not line up between the phone and the node, so the two clocks could not be
aligned; the fix is to trigger on an acoustic event visible in both streams (the phone's own
playback start) rather than on a phase relationship.

### O-7 — the resend mechanism has not been exercised under a genuinely hostile channel — **STILL OPEN**

*Original wording:* "It is verified against the hub's own Bluetooth advertising, which is the real
interference in this design, but not against a busy Wi-Fi environment with a second router on the
same channel."

**Status: still open.** The resend path is real and exercised: the hub logs "the burst stalled with
N of 286 fragments", asks for the missing ones, and the resend rounds recover nearly all of it
(D-26, D-27). The hub's own Bluetooth advertising is a genuine and *severe* interferer — it is the
reason the advertising interval is throttled to 320 ms during a burst (Chapter 11) and the reason
the burst duration dropped from 5.54–6.93 s to 2.06–2.11 s (Chapter 9).

What is untested is a **second Wi-Fi router on channel 6** — a hospital or a school where the
nursery's AP is on the same channel as the ESP-NOW network. ESP-NOW and Wi-Fi share the radio, so a
busy channel does not merely drop frames, it prevents the node from transmitting at all, and the
resend rounds then fight a channel that never opens. The prediction to test: the resend rounds
recover most of it (they recovered against the BLE interferer), but the *burst* can exceed
`BURST_TIMEOUT_MS` (15 s) and be abandoned, with `BURST_FAIL_LIMIT` (3) consecutive failures putting
the node into a 60-second backoff.

### O-8 — the music false-alarm rate — **CLOSED**

*Original wording:* "The deployed model false-alarms on 8.19 % of loud music, and the fix is a
training round that has not been run yet."

**Status: closed by D-58.** GTZAN was added to the training corpus, the notebook was patched and
regenerated, the second full Kaggle run happened, and the retrained model is deployed and verified
on the board.

| | Before | After |
|---|---|---|
| GTZAN music false alarms | 79 / 965 = **8.19 %** | 2 / 965 = **0.21 %** |
| ESC-50 non-cry false alarms | 38 / 1,439 = **2.64 %** | 17 / 1,439 = **1.18 %** |
| ESC-50 `crying_baby` recall | 36 / 40 | **36 / 40** (unchanged) |
| Quiet room | 0 / 236 | **0 / 236** (unchanged) |

The cost is real and was accepted: per-window INT8 recall on the phone-speaker sessions fell
(session 1: 0.867 → 0.800; session 4: 0.724 → 0.592). Episode recall did not fall, because a cry
is sustained and trips many consecutive windows.

### O-9 — the confusion session — **CLOSED**

*Original wording:* "The confusion session — the in-room measurement of speech, music, television
and the phone-played cry — has not been recorded."

**Status: closed by D-60.** Nine one-minute takes on the real INMP441, labelled by the session's
ground truth rather than by loudness, cut into 5 s clips with a 2.5 s stride. Full table in
Chapter 15.

| Result | Number |
|---|---|
| False alarms on speech, music and film | **0 in 308 windows** |
| Loudest music the room can produce | trigger fired on 84 % of records, **0 of 44** windows alarmed |
| Loudest film | trigger fired on 46 % of records, **0 of 44** windows alarmed |
| Per-window recall, cry at 15 cm | **86.4 %** (38/44) |

The session also produced the finding that redirected the engineering: **the cry at one metre never
crosses the trigger**, so the system's reach is set by software, not by the microphone.

---

## 2. The two-cot sub-items, and the items with no O-number at all

### O-1a — the wearable exists and has run on its cell; the runtime does not — **PARTLY CLOSED**

The wearable is on the bench, proven end to end, and **has run from its Li-Po pouch** (2026-11-20).
What remains under this item is *how long* it lasts, and the buzz that went missing while it was on the
cell — both O-1d below. The battery/SOC readout that used to be listed here is **cancelled**, not deferred: there
is no divider and no SOC text on the OLED (D-83).

### O-1b — two cots crying at the same instant — **CLOSED BY D-86**

This was open when the dossier was first written, and it is now measured. On **2026-11-20** one clip
was heard by both node microphones and the hub's crying mask sat at **`0x03` for fifteen consecutive
seconds**; the owner watched the wrist's alert face read the two-cot label. **Three separate two-cot
events** were captured (15 s, 3 s, 7 s).

**The one-buzz rule held across all of them.** Over the whole session, nine cry announcements across
five episodes produced **exactly five buzzes**; the four silent ones were handovers between cots. The
single-cot path is unchanged.

**What the test did not show, and this matters for the defence:** there is **no second buzz when a
second cot joins**. That was never implemented, and D-86 deliberately does not add it — one cry is one
buzz. The earlier note on this item described a branch that would buzz on a second cot; that branch
(`feature/wearable-multi-cot`) turned out to be an **earlier and different** attempt with no `COTS`
label at all, and it is superseded, not merged.

**What remains genuinely untested:** two *independent* cries — two sources, two babies — rather than
one clip heard by two microphones. The mask, the arbitration and the buzz rule were exercised by the
shared-source case; genuinely colliding bursts from two separate cries have still not been staged.

### O-1f — this repository's D-86 image is compile-verified, not flashed — **OPEN**

The behaviour above was proved from the **sibling repository's** build. The change has been ported here
and compiles to the identical figures — **685,589 B (52 % of flash) / 18,684 B (5 % of RAM)** — and
`check_prebuilt.py` passes. But **no board was attached when it was ported**, so this repo's
`firmware/prebuilt/wearable/app.bin` has never been written to a device.

**How it closes:** `python firmware/tools/flash_unit.py --role wearable --port COM30`, then re-run the
two-cot play and watch the glass. Until then, treat the port as verified-by-equivalence, not
verified-on-hardware.

### O-1c — the I²S zero watchdog is committed but not flashed — **OPEN**

The watchdog exists because a microphone that stops producing data produces **zeros**, and zeros look
exactly like a very quiet room: no trigger, no burst, no alert. The system fails silent, which for a
monitor is the worst way to fail. Chapter 7 has the code.

Two honest limits: it detects **exact** zeros only, so a microphone stuck at a DC value or at low-level
noise is not caught; and the fault-injection test proved the code executes and refills a window, not
that it recovers the original physical fault, which has never been reproduced on demand.

It is not flashed because the owner is soldering the final wiring and a node should not be reflashed
mid-solder (D-79). **After it goes on it needs a played-cry end-to-end run** to confirm the node still
streams and the hub still hears it.

### O-1d — no *runtime* has ever been measured; one unit has run on a cell — **OPEN, and it is the largest hardware gap**

**A correction to this dossier's own first edition.** It said *"nothing has ever run from a cell."*
That was too strong, and the bench record disproves it: during the third round of the **2026-11-20**
session the wearable was on its **Li-Po pouch**, not USB — which is exactly why COM30 was absent and no
wrist log could be captured that round. **A unit has run from a cell and kept working.** The nodes and
the hub have still never been battery-powered.

**What is still open is how long anything lasts**, and one live fault came out of that round: **the
haptic buzz went missing while the wrist was on the pouch.** The firmware is exonerated — D-86 touches
no motor line, and the drive is byte-identical to the build proved on 2026-11-11 — so a sagging 3.3 V
rail is a real candidate, since the OLED, the C3's radio peaks and the motor share one linear
regulator. The decisive test is a meter across the motor during a live alert: ≈3.3 V means no current
(open coil or dry joint), ≈2.1 V means current flowing but a weak motor or a sagging rail, ≈0 V means
the BC547 is not switching.

Every power *number* the project has is still **arithmetic from the regulator's behaviour**, not a bench
reading. The ~6-hour pouch figure and the <1-day 18650 figure are **projections** (D-82, D-84), and
this document labels them as such everywhere it quotes them.

Unknowns only a cell can answer: the boost module's quiescent current, its switch-off drain, the cell's
voltage curve under a radio-burst load, the actual charge current, and the thermal behaviour of the
board's own linear regulator - which dissipates (5.1 − 3.3) V × I ≈ **0.5–0.7 W** at the radio peaks.
**The regulator is the weak point in the chain, not the radio.** A module that draws a milliamp in
standby would dominate a wearable's budget, and nobody has measured it.

The procedure is in `SYSTEM_WIRING.md` §6: build **one** power assembly, validate it, then buy
the rest. The three rules of D-84 are not optional - set the trimpot to 5.1 V before any board is
attached, never run the boost and USB into the same board, and use a VBUS-cut cable to log on battery.

### O-1e — the divider's source impedance — **CLOSED BY D-83**

This item was opened because the proposed 220 k / 100 k divider has a source impedance of
**68.75 kΩ** (220 kΩ ∥ 100 kΩ), well above the ~10 k an ESP32 ADC wants, and the 100 nF on
the sense node was what made the reading accurate - load-bearing, not a nicety. A fallback was worked
out (22 kΩ / 10 kΩ keeps the ×3.2 ratio exactly and drops the source impedance to 6.9 kΩ for about 118 µA
more drain).

**None of it is needed.** The whole feature was withdrawn before it was fitted: no divider, no
capacitor, no ADC channel. The item is closed by deletion, which is a legitimate way to close an item
and worth naming as such.

### O-10 — how the model scores a *loud* conversation — **OPEN, no O-number in the record**

In twenty minutes of people talking, four non-cry windows scored **0.9688-0.9805**. None was loud
enough (0.080 RMS) to exercise the loud path. This unknown is the stated reason the loud path requires
saturation: `CRYNET_LOUD_ANNOUNCE_RMS` 0.080 **and** `CRYNET_LOUD_ANNOUNCE_P` 0.9900. If a loud
conversation can reach 0.99, the loud path announces it.

**How it closes:** play speech at a level that reaches 0.080 RMS at the microphone without clipping,
and read P(cry). One session.

### O-11 — the runbook's RMS target is *unsafe* advice, not merely imprecise — **OPEN, and now measured**

`DEMO_RUNBOOK.md` says to aim the phone at a hub reading of **0.10-0.20 rms**. The quantity that
actually decides refusal is the **peak**: the clip gate is `peak >= 31000` (0.946 of full scale), not
an RMS bound.

**This was upgraded from "imprecise" to "unsafe" by measurement on 2026-11-20.** All three windows
refused in that session — peaks 32767, 32637 and 32736 — sat **inside** the 0.10–0.20 band the runbook
recommends. The 2 s window includes the clip's quiet lead-in and tail, which drags RMS down while the
peak stays at the rail: measured *window* crest was **6.1–7.3**, against ~2.9–3.1 for the loudest
100 ms blocks of the same clips. At crest 7 the clip's ceiling is window RMS ≈ **0.135**, not 0.20. An
operator following the runbook exactly can therefore saturate the microphone and see cries missed, or
named to the wrong cot, with the hub's own number telling them they are in range.

**The correct instruction is a peak target** (keep the peak under about 0.75 of full scale) **and
distance rather than volume** — peak falls roughly as 1/d, so 1.5–2× the phone-to-mic gap puts these
windows near 0.5–0.6 with margin. The same file's example `status` output still shows a third cot.
Both are documentation defects rather than system defects, and both are offered rather than applied —
but this one now has a measured failure behind it, and it is the first documentary item worth fixing.

### O-1g — the microphone's close-range blind spot, and a clip gate that discards on one sample — **OPEN, design**

This is the system limitation the 2026-11-20 session exposed, and it is separate from the runbook
wording above.

**The blind spot.** A source close enough to drive the INMP441 to the rail produces a window the hub
refuses outright — correctly, because the microphone is fixed-gain and flat-tops *before* the node's
16-bit window does, so the harmonics the model reads are already gone. **A real infant crying directly
at the microphone lands in the same dead zone.** No firmware change fixes this; only placement or a
gain change does. It is a genuine boundary of the system and should be stated as one in a defence.

**The gate's granularity.** `CRYNET_CLIP_PEAK` is a bare peak test over all 32,000 samples, so **one
saturated sample discards a whole 2 s window**. In the measured round, seq 82 was refused on a *single*
sample at 32042 while its RMS 0.1901 and crest 5.1 looked otherwise usable. A count- or fraction-based
gate — refuse on sustained saturation, tolerate an isolated transient — would have passed it and named
the correct cot sooner.

**Why it is recorded and not implemented:** the model's score on lightly-clipped windows has not been
measured, so relaxing the gate would be a guess about accuracy. The order is measure first, then
branch, bench-verify and reflash the hub.

### O-12 — the record's own numbering and identity blocks are inconsistent — **OPEN, documentary**

Seven separate things, all in the documents rather than the code:

| What | Where | The fact |
|---|---|---|
| **D-51 and D-52 are each used twice** | `DECISIONS.md` §1.2 and §1.5 | D-51 is both "music joins the corpus" and "the font table is indexed by raw ASCII"; D-52 is both the zip-index fallback and the `PHONE` pill. 87 rows, 85 distinct numbers |
| **D-70 was skipped** | `DECISIONS.md` | The cry-mode entry threshold's reasoning is in the code and in D-69's neighbourhood, but no D-70 row exists |
| **D-95 was skipped** | `DECISIONS.md` | The hosted Cloudflare copy's decision is described in D-97 (the URL) and in the D-91..D-94, D-96..D-99 rows around it, but no row carries the number 95 — the commit that introduced the copy used it, the record never did. 108 rows now carry 106 distinct numbers |
| **D-3 still says "3-node → hub → wearable"** | `DECISIONS.md` §1.1 | The topology it describes is this system's, with two nodes. D-75…D-81 and §0 correct it, but the row itself was not edited |
| **O-1's struck-through text still names a DRV2605L** | `DECISIONS.md` §4 | The fitted drive is a BC547 (D-77). The resolution note beside it is correct; the original wording is not |
| **D-16 and `SYSTEM_UPDATE.md` quote the *previous* model's SHA-256** | `DECISIONS.md` §1.2, `SYSTEM_UPDATE.md` | `4aef55d8…126bc11` is the pre-retrain artefact of 2026-10-29. The **deployed** model is `bd592d54…dce43b9`, and `deploy_config.json` and `check_artifact_drift.py` both carry the live one. D-16's quoted test AUC (0.9995) and cross-corpus AUC (0.9973) belong to the same superseded run; the deployed model's are 0.9993 and 0.9984. **Chapter 5 has the full comparison** |
| **The headline board tables said SuperMini for the cots** | `PROJECT_HANDOFF.md`, `TWO_COT_README.md`, `firmware/node/README.md`, `HARDWARE_COMPONENTS.md`, `SYSTEM_WIRING.md`, and the header comment of `node_crynet.ino` itself | The swap to **Pro Mini** nodes was made and verified live on **2026-11-02**, but those five documents still described it as planned or named the old board, and the sketch's own header named the SuperMini in two lines. **Corrected in this edition** — and the first edition of this dossier copied them, which is how the error reached page 8 |
| **The node's build figures were the day-one build** | this dossier, chapters 7, 14 and 19 | The earlier edition printed **977,617 B (74 %) / 165,972 B (50 %)**, which is the stage-2b compile of **2026-10-30**. The tree as it stands compiles to **983,177 B (75 %) / 166,404 B (50 %)**, measured 2026-11-23; the D-83 entry of 2026-11-07 already said "75 % flash, 50 % RAM". **Corrected in this edition** |

None of these changes what the system does. All of them are the kind of thing a supervisor finds in
two minutes, so they are listed here rather than left to be discovered.

**The lesson worth keeping.** This dossier was faithful to the repository, and the repository was
behind the bench: three sessions were run on this two-cot hardware but logged in the sibling repo. A
document built from prose inherits the prose's staleness. Only the source, the artefacts and the dated
bench entries are authoritative — which is why this edition was checked against all three.

### O-13 — one stale comment in the node sketch — **CLOSED in this edition**

`node_crynet.ino` described the hub's heartbeat as arriving "every 100 ms", in **two** places (the
`g_hub_rssi` block and the peer-learning block). The hub sends it **every 1000 ms**
(`link_stage.c:1495`, `(probe_now - last_heartbeat_us) > 1000000`). The code was always right and the
comments were wrong; the node's link-bar freshness print is computed from the actual timestamp, so
nothing misbehaved. It mattered because a reader sizing a timeout from that comment would size it ten
times too tight — and the second comment also claimed the hub's address is learned "within a tenth of
a second of boot", which is really about a second.

**Both comments now say 1000 ms**, and the peer-learning comment says "within about a second of boot".
Comment-only: the sketch compiles to the identical **983,177 B (75 %) / 166,404 B (50 %)**, and
`make_prebuilt.py --role node` was re-run so `BUILD_INFO.json`'s source fingerprint matches the edited
file. `check_prebuilt.py` passes — 11 images match, all three roles up to date.

---

## 3. What was knowingly given up

These are not open items. They are closed decisions with a price, and the price is stated so that
nobody later discovers it as a surprise.

| # | What was given up | Why | The price |
|---|---|---|---|
| 1 | **Battery state of charge** | The panel already says which cots are answering; a second copy of that answer on a cot is redundant, and the figure was always an estimate from a resting-voltage curve (D-83) | **Nothing in the system warns a caregiver that a cell is nearly flat.** The cells are watched by eye. The telemetry payload shrank 34 → 32 bytes |
| 2 | **Every status LED** | Same decision (D-83) | A unit that is off looks identical to a unit that is asleep. The panel is the only status surface |
| 3 | **Cause classification** (hunger / pain / tired) | The BLE alert packet has one bit for it (D-1) | The caregiver gets "a cot is crying", not "why" |
| 4 | **A certified infant monitor** | Out of scope for an academic prototype | Detection accuracy, radio delivery guarantees, battery life and alarm behaviour are not established to any safety-critical standard, and the system does not replace supervision |
| 5 | **A soft trigger** — the hub never hears a cry below 0.030 RMS | The old system's 0.18 trigger was a real bug, but 0.030 is the floor that keeps a quiet room quiet | The system is blind at 1 m. The node's adaptive trigger partly recovers this; the hub's fixed gate does not |
| 6 | **Announcing on a two-window run without energy** | Fourteen false alarms in a quiet evening (D-72, D-73) | The run clause currently announces **nothing** — see Chapter 10 — and a real cry that only reaches two windows is not announced |
| 7 | **Per-window alerting** | A recording of cries has gaps; per-window alerting flaps (D-24) | A cry shorter than the 8-second hold is announced late |
| 8 | **A 3.3 V buck-boost feeding the board's 3V3 pin** | The LX-LCBST cannot be set below 4.2 V, so it needs a separate module (D-84) | The board's linear regulator burns (5.1 − 3.3) V × I ≈ 0.5–0.7 W as heat. Runtime is roughly half what a direct 3.3 V supply would give |
| 9 | **The DRV2605L haptic breakout** | Not needed; the BC547 low-side switch with a 22 Ω stall cap is simpler and cheaper (D-85) | The stall cap drops ~1.2 V of the rail, so the motor runs slower and quieter than on the originally-specified 10 Ω |
| 10 | **LiFePO4 cells** | Charge-current and thermal behaviour under the project's charging scheme is not established | 18650 for the nodes and hub, a Li-Po pouch for the wearable |
| 11 | **Per-cot confidence in the BLE alert** | The packet is a frozen six-byte legacy format (D-42) | The confidence bar on the wrist is the loudest cry's figure, not a per-cot figure |
| 12 | **A second buzz on a cot handover** | The hub always sends `alert_type` 1 for a cry and the wrist buzzes only on the transition into 1 | When the loudest cot changes hands, the wrist stays silent — by design, because the caregiver has already been alerted |
| 13 | **One radio doing two jobs** | ESP-NOW and Wi-Fi share the hub's radio, and ESP-NOW's channel is fixed at 6 (D-98, Chapter 12) | **The router's 2.4 GHz channel must be set to 6.** On any other channel the hub refuses the network and the dashboard goes dark — and the cots never notice, which is the point of the rule |
| 14 | **Audio never leaves the room** | The dashboard's records are metadata — numbers, durations, confidences; there is no microphone feed on any network | No remote listening-in, ever, at any price; the record cannot leak what it does not hold |

---

## 4. What has *not* been measured

The full list is in [Chapter 15](#chapter-15); this is the same list arranged by what it
blocks.

| Unmeasured | What it blocks | How it would be closed |
|---|---|---|
| **A real infant cry, end to end** | Any claim about real-world recall | 50–100 recorded clips on the real INMP441, then a notebook re-run and a bench session |
| **Battery runtime on any unit** | Any runtime claim | One unit, one cell, a log, and a stopwatch. The current figures are projections |
| **The loud-conversation score** | The loud path's safety | Play speech at a level that reaches 0.080 RMS and read the P(cry) |
| **Two *independent* cries at once** | The arbitration rule under genuinely colliding bursts | Two phones, two cots, one hub, at once. One clip heard by both mics is already verified (D-86) |
| **This repo's D-86 image on hardware** | Treating the port as bench-verified here | Flash the wearable from this repo and re-run the two-cot play (O-1f) |
| **The haptic's rail on a cell, and the motor's real stall current** | The alert's last mile under battery power — the buzz went missing on the pouch | One multimeter across the motor during a buzz, and a series ammeter on a bench supply (O-1d) |
| **The I2S watchdog recovering a real fault** | The silent-failure path | Flash it, then a played-cry end-to-end run (O-1c) |
| **The 89 % airtime figure at two cots** | The advertising policy's justification | Re-measure the duty cycle with exactly two cots transmitting |
| **The distance curve beyond 15 cm and 1 m** | The reach of the system | An acoustic alignment on a playback-start event, not on phase |
| **A busy Wi-Fi channel** (O-7) | The resend guarantee | A second router on channel 6 |
| **The tensor arena in internal SRAM** | Nothing — it is an optimisation | Try it, measure, keep it if it fits |
| **A lit-room panel photograph** | The panel's tone curve | One photograph |
| **The charge current and quiescent drain** | The power budget | A meter and a cell |

---

## 5. What to do next, in order

The ordering is by **value per unit of effort**, and it is deliberately not by what is most
interesting.

### First: meter the motor during an alert on the pouch (O-1d)

**The wearable already runs on its pouch, so start there — with a meter, not a stopwatch.** Put it on
the cell, trigger an alert, and read the voltage across the motor while it should be buzzing: ≈3.3 V
means no current (open coil or dry joint), ≈2.1 V means current flowing but a weak motor or a sagging
rail, ≈0 V means the BC547 is not switching. That single reading resolves the one fault the pouch run
exposed, and it costs five minutes.

**Then the stopwatch.** Runtime is still the largest gap between what the documents claim and what has
been observed, and it is the item every other power question waits on: the charge current, the boost's
quiescent drain, the regulator's heat. Build **one** node power assembly, validate it against the three
rules of D-84, log it against the USB baseline, and only then buy the rest.

### Second: record the real in-domain corpus (O-2, O-5)

Fifty to a hundred clips: ten infants × several cries, on the real INMP441, in the real room, with
room negatives in the same takes. The tooling is written and proven — `collect_clips.py`,
`label_session.py --truth`, `CONFUSION_SESSION.md`. This single action closes the project's
largest accuracy risk, and it is the only thing that changes the headline number from "strong on a
proxy" to "strong on the real thing".

Then, and only then, re-run the notebook with the new corpus included and re-deploy. The rule
about the model being deployed only after its own evals have been run on the repo's own scripts
(D-58) applies to this round exactly as it applied to the last one.

### Third: measure the distance curve (O-6)

Because the system's reach is set by a software threshold and the microphone has no gain control,
the distance curve is the honest statement of what the product can do. It is also a measurement
that a sceptic will ask for.

### Fourth: run the hub on a cell for one shift (O-1d)

One unit, one 18650, one log. It converts every runtime figure in the document from *projected* to
*measured*, which is a categorical change in how defensible the power section is.

### Fifth: close the documentary items (O-11, O-12, O-13)

Update `DEMO_RUNBOOK.md` to the peak-based target and to a two-cot `status` example; fix the stale
heartbeat comment in the node sketch; and bring `DECISIONS.md`'s numbering and identity blocks into
line. Cheap, and it removes three places where a reader could catch the project out.

### Not on the list, and deliberately so

- **Re-tuning the model on the phone-speaker sessions.** The music problem was structural and the
  fix was a training round; the phone-speaker sessions are a *proxy for a proxy* and tuning on them
  would fit the artefact rather than the problem.
- **Lowering `CRYNET_TRIGGER_RMS` on the strength of 308 windows from one afternoon.** The
  adaptive trigger was the evidence-driven change; a second threshold change needs a second
  afternoon of evidence.
- **Moving the arena to internal SRAM.** At 101.8 ms per analysed window, for an event-driven
  system, this buys nothing a user can feel.
- **Adding a cause classifier.** The wire format has one bit. It is D-1, and it was deliberate.

---

## 6. How to defend this

If the question is *"what is the weakest part of this?"*, the answer is three sentences long and it
does not require hedging:

> The model has never heard a real infant cry — every positive is either a clean corpus recording
> or a recording played through a phone speaker, while every negative is the authentic sound of
> this room through this microphone. The system's reach at one metre is set by a software
> threshold rather than by the microphone, which has no gain control — and a source close enough
> to drive that microphone to the rail is refused outright, so there is a close-range blind spot.
> And although the wearable has run on its pouch, **no unit's runtime has ever been measured**, which
> makes every runtime figure in the document a projection — one power assembly and a stopwatch would
> settle it.

Each of the three is (a) recorded in the project's own decision log, (b) stated in the same terms in
the overview, the results chapter and this one, and (c) accompanied by the procedure that would
close it and an estimate of what it would cost. Nothing about the system's accuracy is claimed
beyond what was measured, and nothing about its limits is hidden.

That is what it means for a project to be defensible: not that there are no weaknesses, but that
every weakness is known, named, measured as far as it can be, and priced.
