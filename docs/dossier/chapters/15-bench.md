# Chapter 15 — Bench verification and the demonstration procedure

## The distinction that governs all bench work

**The log is the evidence. The wrist is the output.**

The wrist buzzes once per cry and lists every cot the hub says is crying. "It buzzed" therefore proves
much less than the log line does: it proves an alert was published, not that the *right* cot was
named, not that the model was confident, and not that the window was clean. Every verification
procedure in this project reads the hub's serial log.

## Setting up a bench session

1. **Flash all units** (Chapter 19). One command per unit.
2. **Open the hub's log** — `firmware/tools/listen_hub.py`, or any serial terminal at 115200.
3. **Open the node's log** alongside it — `firmware/tools/listen_node.py`. The node's log carries the
   floor, the level and every frozen window's own RMS; without it you cannot tell a trigger problem
   from a model problem.
4. **Attach a BLE client** — the wearable, or `firmware/tools/ble_alert_test.py` on a laptop.
5. `firmware/tools/capture_multi.py` captures several ports at once with timestamps, which is what
   makes a two-board timing measurement possible.

## The demonstration procedure

From `DEMO_RUNBOOK.md`, in order.

### Once, before starting

**Set the phone's distance, not just its volume, and do not touch either during the demonstration.**
The runbook's stated target is a hub reading of **0.10–0.20 RMS**. **That target is not safe on its
own**, and this is the single most important operational lesson in the project.

> **Measured on 2026-11-20, and it contradicts the runbook.** Three windows were refused for clipping
> at peaks **32767, 32637 and 32736** — and *all three sat inside the 0.10–0.20 RMS band the runbook
> recommends*. The quantity that decides refusal is the **peak** (`peak >= 31000`), not an RMS bound.
> The 2 s window includes the clip's quiet lead-in and tail, which drags RMS down while the peak stays
> at the rail: measured **window crest was 6.1–7.3**, against ~2.9–3.1 for the loudest 100 ms blocks of
> the same clips. At crest 7 the ceiling is window RMS ≈ **0.135**, not 0.20.
>
> **What went wrong on the bench:** cries were sometimes not detected at all, and a cry played at
> **cot 2 was announced as cot 1** — because cot 2's own saturated windows were refused and the
> bystander cot's clean window, hearing the same cry across the table, announced first.
>
> **The fix is distance, not volume.** Peak falls roughly as 1/d, so **1.5–2× the phone-to-mic gap**
> puts these windows near peak 0.5–0.6, clean with margin. Aim to keep the **peak under about 0.75 of
> full scale**; treat the RMS number as a rough sanity check only. With the phone moved back, four
> plays named the right cot four times.

**Leave about 10 s between plays.** `CRY_HOLD_MS` = 8000 keeps a confirmed cot crying for eight
seconds, during which a challenger needs 1.5× the RMS sustained for 1.5 s to take the name — and the
wrist buzzes only on a fresh quiet→cry transition. A second play inside the hold can therefore be
silent and can keep the first cot's name. **That is the one-cry-one-buzz rule working, not a miss.**
Ten seconds makes each play an independent test.

**The clip:** `session9_clip_0005.wav` from `research/out/demo_kit/` — the most forgiving of the kit;
it announces at every volume and never clips. Backups, in order: `session4_clip_0012.wav`,
`session1_clip_0005.wav`.

**Do not play from the laptop's speakers.** They reshape the cry enough that the model refuses it —
**P 0.03–0.15 on a window the model scores 0.9961 from the same recording**. The phone is not a
nicety; it is the only source shown to work (D-61).

**The room:** quiet if you can get it. The system holds **0 false alarms in 20.5 minutes** of a room
with people talking, but the demonstration is easier in a quiet room.

### Per cot — about 15 seconds each

**The phone goes 15 cm from the microphone.** Not 10 cm (that saturates the microphone) and not 1 m
(the cry never crosses the trigger). **15 cm.**

1. Hold the phone 15 cm from the cot's microphone.
2. Press play. **Let the whole 5-second clip run out.** Do not press twice; do not stop it early.
3. **Wait 5 seconds.**
4. **Read the hub's log:**

   ```
   node 1: front end 48.2 ms, inference 103.5 ms, P(no_cry)=0.0039 P(cry)=0.9961
   node 1: ALERT — cry
   ```

   **That second line, on the node you played at, is the pass condition.**
5. **Wait 10 more seconds.** The alert is held 8 s and then clears. You must let it clear before the
   next cot, or the hub keeps naming the previous cot.

Repeat for each cot. Afterwards, wait 10 seconds of quiet and check: **one `ALERT — cry` line per cot,
and nothing after the last one.** A quiet window must never announce.

Total: about 45 seconds of playing, 75 seconds with the waits.

### Why one play, and not several

The node freezes **one** window per cry (cry mode, D-69). Once it has, it will not freeze again until
the room goes quiet. A second play of the same clip therefore lands on the tail of the clip — a pause
between cries — and the model scores that around **0.11**. That "no cry" is the *clip* being wrong,
not the system being wrong.

> Playing once and reading the log tells you what happened. Playing three times and watching the
> wrist tells you almost nothing.

## Reading the log

| The log says | What it means | What to do |
|---|---|---|
| `node N: ALERT — cry` | **pass** — the right cot named | next cot |
| `the window is CLIPPED` | the phone is too close; the microphone saturated | move it **back** to 15 cm; do **not** turn the volume down |
| `no cry` with P(cry) high | the window caught a pause in the clip | play once more, same place |
| `cry (too quiet to announce)` | below the 0.020 RMS floor | phone closer, or volume up |
| `cry (unconfirmed)` | a maybe: P(cry) high but the window was not clean | play once more |
| `ALERT — cry` on the **wrong** cot | another cot heard it cleanly | wait out the 8 s hold, then play again |
| nothing at all | the cry never crossed the trigger | phone closer |

The "clipped → move back, not down" row is counter-intuitive and correct: turning the volume down
changes the *recording's* dynamics as well as its level, and the kit was characterised at a fixed
volume. Distance changes only the level.

## The two-cot checks that are specific to this system

Before any acoustic test, four things are worth confirming, because each has a failure mode that
looks like an acoustic problem and is not one.

**1. The bench map.** Four targets, four ports, and the wrong port means the wrong firmware. Read each
board's own boot banner rather than trusting a remembered port number:

```bash
python firmware/tools/who_is_who.py
```

The map on the last verified session was COM32 hub, COM30 wearable, COM31 cot 1, COM37 cot 2.

**2. The ids.** `id 1` and `id 2` over each cot's console, then confirm they survived the flash. A cot
on any other number is not quiet — it is *invisible*, because the hub drops its frames before they
reach a slot. The symptom of a wrong id is identical to the symptom of a dead radio, which is why this
check comes second and not last.

**3. Both link bars, in both directions.** On the cot's console, `status` prints its view of the hub
(`link   [####] -12 dBm (hub frame 445 ms ago)`). On the hub's console, `status` prints its view of each
cot. If the cot's bar is empty, the hub's heartbeat is not arriving — check that the hub is running the
firmware that sends one, because a hub built before that change answers requests perfectly and still
leaves the cot's bar dark.

**4. The wrist's cot count.** The wearable must read `state: 2 cot(s)`. If it reads `0 cot(s)` while
the hub can hear both, the hub is running firmware that only publishes state on a cry transition —
the bug the 2026-11-05 session found. It is a publishing-side fault, not a wearable fault.

**Then the alert path, without any sound at all:**

```
alert 2      → hub: ble_alert: a cry on cot 2 at 100%
             → wrist: [ble] ALERT cot 2 type 1 conf 100% event #1   (and a buzz)
clear        → wrist: the matching type 2 cancel
```

That exercises the whole downstream half — arbitration, BLE, the wrist's parsing, the haptic — with
none of the acoustic variables in play. If it fails, the problem is not the microphone.

## Troubleshooting, in the order to try

1. **Move the phone back to 15 cm.** Clipping is the commonest failure and the fix is distance.
2. **Play once more**, same place, and read the log.
3. **Check the hub is alive** — the console answers `status`:

   ```
   I (12345) console: << status
   I (12346) console:   cot 1: rms 0.0154  level 0.0092  window 0.0121 (whole)  confidence 0%  link -23 dBm
   I (12347) console:   cot 2: rms 0.0148  level 0.0088  window 0.0119 (whole)  confidence 0%  link -43 dBm
   ```

   No answer means the hub has crashed or lost power.
4. **Check the node is alive** — its console answers `status` and `stats`.
5. **The link**, if a window never arrives: the hub logs `the burst stalled with N of 286 fragments`
   and asks for the missing ones. The resend rounds recover nearly all of it; if a burst dies
   outright, move the cot away from whatever is on the same channel.

## The demo kit and how it was built

`research/build_demo_kit.py` cut the recorded sessions into 5-second clips;
`research/screen_clips.py` and `research/score_demo_clips.py` scored every clip against the deployed
model and the announcement rule.

| Fact | Number | Source |
|---|---|---|
| Clips that announce under the rule on the boards | **27 of 37** | `research/out/demo_rehearsal.md` |
| Clips that clip if turned up | **17** | same |
| Freeze lands after the clip starts | 2.0–5.4 s, **median 2.9 s** | `research/out/demo_rehearsal.csv` |
| Continuous cry the model needs in the window | **~1.5–1.75 s** | `research/out/DEMO_KIT.md` |
| Ambient room with people talking | **20.5 min, 0 false alarms** | `research/out/ambient_25min/summary.md` |
| Both cots on one hub, continuous | **25 min, no brownout or reset** | `SYSTEM_UPDATE.md` |

The kit is not a lucky selection: it is every clip from the recorded sessions, scored, with the
failures listed alongside the successes. That is what makes "27 of 37" a defensible number rather
than a demonstration chosen to work.

## Other verification procedures

### The confusion session (O-9)

`research/CONFUSION_SESSION.md` gives the full procedure: nine one-minute takes with `node_capture` on
the real INMP441, cut into 5 s clips with a 2.5 s stride, labelled with the session's ground truth via
`label_session.py --truth` — **not** by loudness. Labelling by loudness would have made the evaluation
circular. Results in Chapter 14.

### Burst integrity

`firmware/tools/measure_burst.py` and `verify_burst.py` capture a burst and check every fragment's
CRC-16 and the whole window's CRC-32 against the node's advertised value, using `zlib.crc32` on the
host. `dump_node_window.py` writes the node's frozen window out over its USB console so the exact bytes
the node holds can be compared with what the hub reassembled.

### Latency

`firmware/tools/measure_latency.py` timestamps request → verdict across the two logs.

### Artefact drift

`firmware/tools/check_artifact_drift.py` verifies `research/out/`, `deploy_config.json` and the staged
firmware copies all describe the same model bytes. Currently **PASS**.

### The wearable, without a noise

`alert <cot>` on the hub console injects a real alert through the real publish path. This is how the
BLE server, the notification and the wearable's callback are tested independently of the model — and
how the haptic fault was localised to hardware.