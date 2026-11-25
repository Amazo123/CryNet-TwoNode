# Chapter 15 — Every measured result, and how it was obtained

## How to read this chapter

Every number here was produced by a run that is still reproducible, or is quoted from a log still in
the repository. Where a figure is a **projection** rather than a measurement, it says so. Where a
figure changed after a retrain, **both** values are given — the older number is not erased, because
the difference between them is itself a result.

The single most important caveat, stated once here and applicable to every positive-case number
below: **the model has never heard a real infant cry.** Every cry it has been tested against is a
recording played through a phone speaker — compressed, band-limited and EQ'd by a small loudspeaker
in a plastic case. The negatives are authentic (this room, this microphone); the positives are a
proxy. This is O-2 and it is the largest accuracy risk in the project.

## Model quality — offline, on the corpora

| Claim | Number | How it was measured |
|---|---|---|
| ICD validation AUC | **0.9994** | full Kaggle run, fold 4 |
| ICD test AUC | **0.9993** | full Kaggle run, fold 5 |
| **Cross-corpus AUC** | **0.9984** | cry4 hold-out + ESC-50 + snoring + music + speech, unseen corpora and unseen babies |
| INT8 vs float32 | **ΔAUC −0.00137**, decision agreement **99.956 %** | 11,386 windows, host |
| Deployed artefact | **137,384 bytes** INT8 | SHA-256 **`bd592d54…dce43b9`** |
| INT8 vs float32, inside the export | val AUC **0.9978 vs 0.9991** | `deploy_config.json` |
| Parameters | 122,770 | `model.count_params()` |

The cross-corpus figure is the one to quote in a defence: it is the honest estimate of what happens in
a room the model has never seen.

## The front end — parity and speed

| Claim | Number | Method |
|---|---|---|
| C front end vs Python | max **6.9 × 10⁻⁵** | 4 probes, real run on the board |
| On-chip feature parity | worst **≤ 1 LSB**, **≤ 1 %** of 5,184 features differing | boot probes, both conditions required |
| On-chip front end | **41.7 ms** per 2 s window | ESP32-S3, 240 MHz, `-O2` |
| On-chip inference | **101.8 ms** per window | ESP-NN SIMD kernels |
| Front end before the SRAM move | 135 ms | scratch buffers in PSRAM — the measurement that justified moving them |
| Tensor arena | 262,144 B reserved, **108,328 B used** | `ArenaUsedBytes()` |

## Against the deployed INT8 model, on real audio

| Test | Before the music retrain | **After (deployed)** | Tool |
|---|---|---|---|
| ESC-50 `crying_baby` recall | 36 / 40 | **36 / 40** | `research/eval_esc50.py` |
| ESC-50 non-cry false alarms | 2.64 % (38 / 1,439) | **1.18 %** | `research/eval_esc50.py` |
| **GTZAN music false alarms** | **8.19 %** (79 / 965) | **0.21 %** (2 / 965) | `research/eval_music.py` |
| Quiet room, this INMP441 | 0 / 236 windows | **0 / 236** | `research/eval_indomain.py` |
| Phone-cry per-window recall, session 1 | 0.867 | 0.800 | `research/score_demo_clips.py` |
| Phone-cry per-window recall, session 4 | 0.724 | 0.592 | `research/score_demo_clips.py` |

The last two rows are the **cost** of the retrain. Per-window recall fell; episode recall did not,
because a sustained cry trips many consecutive windows.

### The music breakdown that caused the retrain

Before: jazz **14.3 %**, blues **13.0 %**, pop **12.0 %**, disco **10.0 %**, rock **10.0 %**; reggae
2.0 %, classical 2.9 %, country 3.0 %, metal 4.0 %.

And the number that ruled out a threshold fix: **45 of the 81 music alarms and 34 of the 36 true cry
detections carried exactly the same value, P(cry) = 0.9961.**

## The in-room confusion session — O-9, closed

Nine one-minute takes recorded with `node_capture` on the real INMP441, cut into 5 s clips with a
2.5 s stride (22 clips, 44 windows each), labelled with the **ground truth of the session** rather
than by loudness (`label_session.py --truth`). Procedure: `research/CONFUSION_SESSION.md`. Result:
`research/in_domain/SESSION_REPORT.md`.

| # | Take | Class | Median RMS | Peak RMS | Records ≥ 0.030 | Clips reaching the model | **False alarms** | Recall |
|---|---|---|---|---|---|---|---|---|
| 1 | session5 | quiet room | 0.0020 | 0.0100 | 0 / 590 | 0 / 22 | **0** | — |
| 2 | session6 | speech, desk distance | 0.0040 | 0.0530 | 3 / 590 | 0 / 22 | **0** | — |
| 2b | session6b | speech, 30 cm | 0.0080 | 0.6670 | 62 / 590 | 6 / 22 | **0** | — |
| 3 | session7 | music, 1 m | 0.0100 | 0.0380 | 1 / 590 | 0 / 22 | **0** | — |
| 4 | session8 | movie, 1 m | 0.0070 | 0.0190 | 0 / 590 | 0 / 22 | **0** | — |
| 4b | session8b | movie, 30 cm | 0.0260 | 0.2180 | 269 / 590 | 12 / 22 | **0** | — |
| 4c | session7b | music, 30 cm | 0.0470 | 0.1410 | 493 / 590 | 20 / 22 | **0** | — |
| 5 | session9 | **the cry, 15 cm** | 0.0370 | 0.3870 | 329 / 590 | 20 / 22 | 0 | **38/44 = 86.4 %** |
| 6 | session10 | **the cry, 1 m** | 0.0070 | 0.0160 | **0 / 590** | 0 / 22 | 0 | *18/44 = 40.9 % if asked* |

**Zero false alarms in 308 windows of non-cry audio.**

The two loud takes are the ones that count. The trigger fired on **46 %** of the loud movie's records
and **84 %** of the loud music's — the model was asked 44 times in each and **refused every one**. On
GTZAN the music false-alarm rate had been 8.19 %; on the loudest music this room can produce it is
**0/44**. That is the retrain working in the room it was supposed to work in.

### The finding that changed the design

**The cry at one metre never crosses the trigger.** Median RMS 0.0070, peak 0.0160, **0 of 590
records** reach 0.030. The system is blind at one metre *by trigger*, not by discrimination — if the
model were asked anyway it would still catch 18 of 44 windows.

That single row is why the adaptive trigger (D-63) exists. It is the clearest example in the project
of a measurement redirecting the engineering: the temptation was to retrain the model, and the data
said the model was never being asked.

## The live chain — hub + node + a real BLE client

| Claim | Number |
|---|---|
| Radio integrity | **0 bad frames, 0 bad payloads** over thousands of frames (the hub's own counters) |
| Burst completion | **286/286 with CRC-32 MATCH**, with a BLE client connected |
| Burst duration | 2.06–5.19 s, **median 3.55 s** |
| Request → verdict | 2.23–5.35 s, **mean 4.03 s** |
| Before the airtime fixes | 5.54–6.93 s per burst |
| After the first airtime fix | **2.06–2.11 s**, no resend rounds |
| Demo session | **45 bursts, 45/45 complete**, no stall, timeout, CRC error or resend round |
| Verdicts in that session | **42**: 26 "ALERT — cry" at P(cry) **0.9922–0.9961**, 16 "no cry" at **0.0078–0.2148** |
| Quiet room + a loud non-cry sound | **P(cry) = 0.0000** on every window; the trigger fired (RMS 0.035–0.085) and the model rejected it |
| End-to-end alert delivered | `ALERT {'cot': 1, 'alert': 'cry', 'confidence_pct': 100}` |

Note the gap in that verdict distribution: nothing between 0.2148 and 0.9922. On real audio in this
room the model is not ambivalent — it is either near-zero or saturated. That is exactly the property
the announcement rule is built on.

## The two-cot bench session — 2026-11-05/06

This is the session that says the *two-cot* system works, as opposed to the components working. The
bench map was read from each board's own boot banner with `who_is_who.py` before anything was flashed,
because four different targets on four ports is four chances to flash the wrong firmware.

| Unit | Port | Identity |
|---|---|---|
| Hub | **COM32** | CH343 USB-serial |
| Wearable | **COM30** | the C3's own USB, `303a:1001` |
| Cot 1 | **COM31** | derived id 1 |
| Cot 2 | **COM37** | saved id 2, from NVS |

**Both ids survived the flash**, which is the check that matters — the id lives in NVS and a flash
could have cleared it.

| Claim | Evidence |
|---|---|
| Both cots heard | `node 1 heard for the first time`, `node 2 heard for the first time`, both `is online` |
| Frame integrity | **993 frames off the air, 993 parsed, 0 bad, 0 bad payload** |
| Panel driver | `the panel is up: 320 x 240, rotation 2` |
| A full burst crossed and was judged | node 2: **286/286 fragments in 0.99 s** |
| The audio arrived unchanged | `window crc32 0xA8FCEBD5, the node advertised 0xA8FCEBD5 -> MATCH` |
| The model ran on it | `P(no_cry)=0.0508 P(cry)=0.9492` — no cry, room noise, **correctly refused** |
| Cot 1's own link bar | `link   [####] -12 dBm (hub frame 445 ms ago)` |
| Cot 2's own link bar | `link   [####] -31 dBm` |
| The hub's view of cot 1 | `cot 1: … link -23 dBm` |
| The hub's view of cot 2 | `cot 2: rms 0.0230 … link -43 dBm` |
| Alert path, exercised without a sound | `alert 2` → `ble_alert: a cry on cot 2 at 100%` → wrist `[ble] ALERT cot 2 type 1 conf 100% event #1` |
| Cancel path | `clear` → the matching `type 2` on the wrist |
| Wearable reattachment | `hub found`, `hub connected`, `subscribed to alerts` — unaided |

Note the fourth row from the bottom and the two above it: **−12 dBm at the cot and −23 dBm at the hub
for the same link.** Those are two different directions measured by two different receivers, and the
node transmits at 8.5 dBm by design (D-65). A defence should not be caught calling that a discrepancy.

### The bug this session found

The hub could plainly hear two cots, and the wrist read **`0 cot(s), mask 0x00`**. The state
characteristic was published only when a cry started or stopped, so a cot *joining* the system never
reached the caregiver, and the wearable read the packet it was given at boot for ever.

The fix was on the publishing side, not the wearable: the eight-byte packet is rebuilt every cycle and
published whenever anything in it has moved — the cry mask, the deaf mask, or **the number of cots the
hub can hear** — and on a slow beat besides. The sentinels were changed so the first cycle always
publishes (`0xFF` for a cot count that cannot happen, `-1000` for the timestamp).

**Verified on the hardware:** the wrist reads `state: 2 cot(s)`, a console test alert moved the mask
`0x00 → 0x02` and back `0x02 → 0x00` on `clear`, with the wearable printing the matching cancel.

## Memory and build

| Claim | Number |
|---|---|
| Hub RAM before the PSRAM move | 59.9 % (196,140 B) |
| **Hub RAM after** | **12.9 % (42,236 B)** |
| **Hub RAM, current build (log + clock + Wi-Fi in)** | **14.3 % (46,788 B)** |
| Hub flash, before the two-cot fields | 61.9 % (1,297,303 B of 2 MB) |
| Hub flash, two-cot build | 63.6 % (1,335,248 B) |
| **Hub flash, current build** | **77.2 % (1,619,615 B)** — the growth is the network stack, the certificate bundle and the cry log |
| Free internal heap at boot | 298,763 B |
| …after the probes | 290,791 B |
| …with the radio up | 215,155 B |
| …with Bluetooth up | **149,271 B** |
| Node flash / RAM (compiled 2026-11-23) | **983,177 B (75 %) / 166,404 B (50 %)** — the stage-2b figure of 977,617 B / 165,972 B is the day-one build, not this one |
| Wearable flash / RAM, before D-86 | 685,143 B (51 %) / 18,684 B (5 %) |
| **Wearable flash / RAM, with D-86** | **685,589 B (52 %) / 18,684 B (5 %)** — +446 B of flash, **no extra RAM** |
| Continuous watch on USB power | **25 minutes, no brownout or reset**; 153 windows scored, 0 alerts |
| Ambient room with people talking | **20.5 minutes, 0 false alarms** (`research/out/ambient_25min/summary.md`) |

## The adaptive trigger, measured

| Condition | Fixed 0.030 | 3× floor |
|---|---|---|
| Cry at one metre | **0 trigger events/min** | **39** |
| Quiet room | ~0 | 5 |
| Loud sessions | capped at 0.030 | capped at 0.030 |

On the boards afterwards: level tracks the room (0.006–0.016 in a noisy room), the node's log shows it
settling (`rms 0.0063 floor 0.0028 level 0.0083`), and the hub asks **5–11 times a minute** instead of
1–2.

And the cost, measured: the same quiet room produced verdicts of **0.0000 and 0.9766** for
indistinguishable windows. Five minutes of a noisy room after the announce-rule change and the TX
power reduction: **32 verdicts, 0 false alerts**.

## Clipping, measured — and the session that made it a first-class finding

| Observation | Number |
|---|---|
| Node 2, ordinary room sound | peak **31,801** of 32,767 — clipped |
| Phone at 10 cm | clipped the cry; that window scored **0.9805 instead of 0.9961** |
| Consequence | **the alert named the wrong cot for 42 seconds** |
| Refusal threshold | `CRYNET_CLIP_PEAK` **31000** (0.946 of full scale) |

### 2026-11-20 — "the cries aren't being detected", and it was the microphone

The owner reported two symptoms in one session: cries sometimes not detected at all, and a cry played
at **cot 2** announced as **cot 1**. Both turned out to be one fault, and the fault is not in the
firmware. Two node-side peak probes ran alongside a wrist capture for 300 s while a cry was played once
at each cot.

| Cot | Window RMS | Peak (of 32767) | Samples at rail | Crest | Verdict |
|---|---|---|---|---|---|
| 1 | 0.1362 | **32767** | 29 | 7.3 | refused |
| 2 | 0.1421 | **32637** | 16 | 7.0 | refused |
| 2 | 0.1627 | **32736** | 58 | 6.1 | refused |
| 1 (bystander) | 0.0703 | 24697 | 0 | — | clean |
| 1 (bystander) | 0.0681 | 18090 | 0 | — | clean |

All three loud windows are ≥ `CRYNET_CLIP_PEAK`, so all three were refused at `link_stage.c:471`
**before the model's score could matter**. Cot 1 also produced two *clean* windows because it heard the
same cry from across the table at a lower level — and that is why the alert named cot 1: the true
source's own evidence was discarded and the bystander's clean window announced first. The wrist log
confirms it: exactly two alerts, both `cot 1`, and a mask histogram of **283 × `0x00` and 16 × `0x01` —
never `0x02`, never `0x03`**. The delay the owner noticed is the same mechanism: the hub waits several
2 s windows until a quieter portion of the clip yields a clean one.

**The correction to our own operator guidance.** All three refused windows sat *inside* the
0.10–0.20 RMS band the runbook calls the target. **Window RMS is not a safe proxy for clipping.** The
2 s window includes the clip's quiet lead-in and tail, which drags RMS down while the peak stays at the
rail — measured *window* crest here was 6.1–7.3, against ~2.9–3.1 for the loudest 100 ms blocks of the
same clips. At crest 7 this clip's ceiling is window RMS ≈ **0.135**, not 0.20. **The instrument that
matters is peak.** The fix is distance, not volume: peak falls roughly as 1/d, so 1.5–2× the
phone-to-mic gap puts these windows near 0.5–0.6, clean with margin.

**The fix was verified the same day.** With the phone moved back, four plays across two rounds named
the right cot every time — `cot 1 #10`, `cot 2 #12`, `cot 1 #14`, `cot 2 #16` — all `type 1 conf 100%`,
each with its 2500 ms pulse and each followed exactly 8 s later by `type 2`. The mask histogram became
symmetric: **388 × `0x00`, 16 × `0x01`, 16 × `0x02`**. Cot 2 naming itself is the case that had failed.
Its peaks were 0.4253/0.6859 and 0.7309/0.7614, zero samples at the rail. **Cot 1 remains the marginal
microphone** — it clipped once at peak 32764 (79 samples at rail), and its clean window peaked 0.8604,
only 10 % under the refusal threshold.

**A design limitation this exposes, recorded and not fixed (O-1g).** The clip gate is a bare peak test,
so **one sample out of 32,000 discards a whole 2 s window** — in a later round seq 82 was refused on a
single sample at 32042 while its RMS 0.1901 and crest 5.1 looked otherwise usable. A count- or
fraction-based gate would tolerate an isolated transient. And **a real infant crying directly at the
microphone lands in the same dead zone**. The refusal is correct — the INMP441 is fixed-gain and
flat-tops before the node's 16-bit window does, so the harmonics the model reads are already gone — but
it is a genuine close-range blind spot that only placement or a gain change can address.

### 2026-11-20 — two cots at once, and the one-buzz rule (D-86)

The supervisor's question — *what does the alert look like when both cots detect a cry at the same
time?* — was answered on the bench. With one clip heard by both microphones, the hub's crying mask sat
at **`0x03` for fifteen consecutive seconds** (12:36:41–12:36:55), and the owner watched the wrist's
alert face read the two-cot label where before it named only one cot. **Three separate two-cot events
were captured** (15 s, 3 s and 7 s).

| Measurement | Result |
|---|---|
| Simultaneous-cry mask | `0x03`, 15 s continuous — plus two more events |
| Cry announcements, whole session | **9**, across **5** episodes |
| Haptic pulses | **5** — one per episode |
| Silent announcements | **4**, all handovers between cots |
| Attach time | **0.4 s** (`hub found` → `subscribed to alerts + state`) |
| Single-cot path | unchanged: `0x01` → `COT 1`, `0x02` → `COT 2`, one buzz each |

The two handovers inside the two-cot episode (`ALERT cot 2` then `ALERT cot 1`, as their levels
crossed) produced **no buzz at all** — exactly as `g_type == 1 && prev_type != 1` says they should.
This is the one-cry-one-buzz rule surviving the case it was written for.

**A later round showed the mask self-correcting.** Cot 2 clipped 3 of 6 windows while bystander cot 1
stayed clean, and the glass went **cot 1 alone → `COTS 1 2` → cot 2 alone**. No forced handover was
involved: cot 1 RMS 0.1317 against cot 2's 0.1508 is 1.145×, under `COT_SWITCH_MARGIN` 1.5 — so the
*mask* did the work, not the loudest-first switch. The system ended on the correct cot by itself.

**And one cosmetic flicker, traced rather than guessed.** The owner saw cot 1 go offline for a split
second. `node_live()` is consulted **only** for whether to keep probing, which cot the panel names, and
the card's online/offline text. It appears **nowhere** in the announce path: the crying mask uses
`published_cry`, the wrist's cot count uses the latched `heard`, and the deaf mask uses the node's own
microphone self-report. **A liveness flicker cannot drop a cry, misattribute one, change the wrist's
cot count, or raise a spurious buzz.** Its one real consequence is cosmetic — the panel can momentarily
name a different cot than the wrist. The duration was *not* measured (the hub's UART was absent), so
the cause is reasoned from the code, not observed in a log.

## The dashboard phase, measured — 2026-11-24/25

| Claim | Number | Source |
|---|---|---|
| Presence cadence, clean-power soak | **15 posts at the exact 30 s cadence, zero cot flap, zero restarts in 10 min** | D-106 |
| The restarts' real cause | **stack overflow in task `main`** — a 3,584-byte stack sized for an `app_main` that returns, running a system whose `app_main` never returns; now 16,384 B | D-107 |
| The same soak, after the stack fix | **zero restarts, telemetry live on both cots** | D-107 |
| D-108's live proof | production D1 rows with `at` **2,251 s old** reading "online" against a 90 s window; after the fix the same rows read offline | deploy `d6deaeda` |
| The owner's end-to-end cry test | **5 cries, seq 111–115, both cots, two episodes one second apart** — all present on the hosted dashboard with presence fresh | live API |
| The contract test | full pass, including the D-108 section, which **fails on the pre-fix server** | `test_dashboard_contract.py` |
| Upload idempotence | a repeated batch adds **0** records | contract test |

Two of these deserve their sentences. The stack overflow is the phase's honest headline: the
"restarts were power" diagnosis of D-106 was made in good faith from a real soak and was still
wrong, and only the next capture caught it — the decision record keeps both, in order. And the
D-108 fix is proved the strongest way a dashboard fix can be: the regression test was made to fail
against the old server first, then the fix was deployed and the same live rows that lied now tell
the truth.

## What has *not* been measured

Listed here so the boundary of the evidence is explicit:

- **Runtime on any battery-powered unit.** The ~6 h pouch / <1 day 18650 figures are *projections*
  from the regulator's behaviour (D-82), not measurements.
- **A real infant cry.** Every positive is a phone-speaker proxy (O-2).
- **How the model scores a *loud* conversation.** Four non-cry windows scored 0.9688–0.9805 in twenty
  minutes of talking, but none was loud enough (0.080 RMS) to test the loud path. This unknown is the
  stated reason the loud path requires saturation.
- **The haptic's rail on a cell.** The motor was proved three ways on USB — the standalone bench sketch,
  three complete alert cycles on 2026-11-06, and the fitted 22 Ω cap on 2026-11-11. The wearable **has
  since run on its Li-Po pouch** (2026-11-20) and kept working, but **the buzz went missing in that
  round** and the rail's behaviour during a buzz is still unmeasured. The 56 mA stall figure is
  arithmetic from an assumed 37 Ω coil, not a measurement of the fitted motor. One meter across the
  motor during a live alert settles it (O-1d).
- **This repository's own D-86 image on hardware.** The two-cot behaviour above was verified from the
  sibling repository's build. The port here compiles to the identical figures — 685,589 B / 18,684 B —
  but no board was attached when it was ported, so `firmware/prebuilt/wearable/app.bin` in this repo
  has never been written to a device (O-1f).
- **The 89 % radio-busy figure with exactly two cots.** That number comes from the busiest session
  recorded (230 s of burst airtime in 260 s), which had more transmitters on the channel than the
  two-cot system does. It is an upper bound on airtime and has not been re-measured at two.
- **The I²S zero watchdog recovering a real fault.** The code is committed and fault-injection proved
  it executes and refills a window; it is not flashed on either cot (D-79, O-1c), and it detects exact
  zeros only.