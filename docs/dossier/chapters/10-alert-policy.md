# Chapter 10 — The announcement policy: turning a probability into an alarm

## Why this layer exists at all

A classifier returns a number. An alarm wakes a person. Those are not the same thing, and the gap
between them is where most of this project's engineering judgement lives.

Three measured facts forced the policy into existence:

1. **The model's output saturates at P(cry) = 0.9961.** A clear cry, a saxophone solo and a loud
   conversation can all land on the same value. No threshold separates them.
2. **The model is not a reliable judge of near-silence.** The same quiet room produced verdicts of
   **0.0000 and 0.9766** for windows that differ by nothing a person could hear. The adaptive trigger
   (D-63) deliberately asks about such windows, so this is a consequence of a good decision, not a
   defect.
3. **A conversation in the next room reaches 0.9727.** One step louder and an earlier, more
   permissive rule would have announced it as a cry at three in the morning.

So the hub does not announce on the model's calibrated threshold (0.95). It announces on
**saturation plus physical plausibility**, and it keeps the weaker evidence as a counter rather than
as a licence.

## The constants, with their measured justification

All in `firmware/hub_infer/src/link_stage.h`.

| Constant | Value | What it means |
|---|---|---|
| `CRYNET_TRIGGER_RMS` | 0.030 | fallback pull level for a node that does not report its own |
| `CRYNET_CLEAR_CRY` | **0.9900** | the saturation bar a quiet window must reach |
| `CRYNET_ANNOUNCE_MIN_RMS` | 0.006 | below this a window is not audible at all |
| `CRYNET_CRY_RUN` | 2 | consecutive cry verdicts before a run may confirm |
| `CRYNET_MAYBE_MIN_RMS` | **0.020** | the level a window needs to be counted or confirmed |
| `CRYNET_PULL_CRY_RMS` | 0.050 | a frozen window this loud is pulled immediately |
| `CRYNET_LOUD_ANNOUNCE_RMS` | 0.080 | above this the window is "loud" |
| `CRYNET_LOUD_ANNOUNCE_P` | **0.9900** | the confidence a loud window needs |
| `CRYNET_CONFIRM_P` | **0.9900** | the confidence the second window of a run needs |
| `CRYNET_CLIP_PEAK` | **31000** | of 32767 — 0.946 of full scale; refuse outright |
| `CRYNET_QUIET_CREST` | **3.5** | peak/RMS a quiet window needs to look like a cry |

### Where 0.050 came from

Measured on the bench, 2026-11-04: the loudest window the nodes froze out of **ordinary room sound**
was **0.036 RMS** (node 2); every window a **phone cry at 15 cm** froze was **0.177 and 0.184**. 0.050
sits cleanly between them. Quieter frozen windows are still pulled the moment the *live* reading is
loud, so a cry at one metre is not lost by this — it is pulled while it is happening.

### Where 3.5 came from

The crest factor (peak ÷ RMS) separates an impulsive sound from a steady one:

| Sound | Crest |
|---|---|
| Room hiss that scored P(cry) = 0.9961 but was not a cry | **2.2 – 2.9** |
| A real quiet cry, P(cry) = 0.9961 at 0.0103 RMS | **5.6** |
| Phone cries at 15 cm | **6.6 – 6.9** |

Room hiss is Gaussian: no impulses, so peak and RMS stay close. A cry is a sequence of voiced bursts,
so its peak runs well above its RMS. 3.5 sits in the empty gap between 2.9 and 5.6.

A loud bump has a high crest too — but the model rejects it, which is the model's job. The crest test
is only applied to *quiet* windows, where the model's word alone is not trustworthy.

## The rule as implemented

```c
const bool saturated = (p_cry >= CRYNET_CLEAR_CRY);

const bool unmistakable = audible && !clipped &&
    ((rms >= CRYNET_LOUD_ANNOUNCE_RMS)
         ? (p_cry >= CRYNET_LOUD_ANNOUNCE_P)   /* loud: the model's word */
         : (p_cry >= CRYNET_CLEAR_CRY)) &&     /* quiet: it must saturate */
    ((rms >= CRYNET_MAYBE_MIN_RMS) || (crest >= CRYNET_QUIET_CREST));

if (says_cry) {
    if (rms >= CRYNET_MAYBE_MIN_RMS && st->cry_seq != st->request_seq) {
        st->cry_seq = st->request_seq;
        st->cry_run++;
    }
    confirmed = unmistakable ||
        (st->cry_run >= CRYNET_CRY_RUN && rms >= CRYNET_MAYBE_MIN_RMS &&
         p_cry >= CRYNET_CONFIRM_P);
} else {
    st->cry_run = 0;
}
```

Read it in words:

- **Audible** — RMS ≥ 0.006. A window with no sound in it cannot be a cry.
- **Not clipped** — peak < 31000. Corrupted evidence is refused, not interpreted.
- **Saturated** — P(cry) ≥ 0.99, on both the loud and the quiet path today.
- **Plausible** — either the window carries real energy (RMS ≥ 0.020) or, if quiet, it has a cry's
  impulsive shape (crest ≥ 3.5).

`cry_seq != request_seq` ensures one window is counted **once**, even if it is scored twice.

### Why the run no longer announces anything

Both `CRYNET_LOUD_ANNOUNCE_P` and `CRYNET_CONFIRM_P` are **0.9900** — the same saturation the
unmistakable path already requires. So a window that satisfies the run clause already satisfies the
unmistakable clause. **In practice the run announces nothing.**

That is deliberate, and the header says so:

> The run is kept because it says how close the model came, and because setting this to 0.9500
> together with `CRYNET_LOUD_ANNOUNCE_P` brings back the whole old rule — the loud window's own
> threshold and the two-window confirmation.

The earlier rule let a *loud* window announce at 0.95 without waiting for saturation. That was a
band-aid for a clipped recording, and it opened the way for a conversation to be announced as a cry.
It was removed, and the two constants were left in place at the saturation value so the whole old
behaviour is **one edit away** if a future model earns it.

This is good engineering practice worth defending: *keep the knob, set it to the safe value, and
write down exactly what turning it costs.*

## The trade, measured in both directions

The header records both sides, which is what makes the choice defensible rather than arbitrary.

**The cost of requiring saturation:** on the corpus, **7 of the 53 cry episodes** the old rule caught
peaked between **0.9688 and 0.9883** and are now missed. All seven are *strong* cries — RMS 0.09–0.22,
crest 4.3–7.9. (An earlier count in `link_stage.c` records the same trade as 8 of 57 over a slightly
different episode set.) On the bench, **three genuine cries out of three scored 0.9961 and all three
still announce.**

**The cost of the old rule:** in twenty minutes of a room with people talking, the model scored
**four windows between 0.9688 and 0.9805 that were not cries**, and the hub's own boot probe scores
**0.9805 on synthetic noise**. None of the four was loud enough (0.080 RMS) for the old rule to let it
through — *but that is the one thing about them that was not measured*: **how the model scores a loud
conversation is unknown**, and the old rule would have announced it.

So the decision was made under a known unknown, and the unknown is written down:

> This number is the saturation, and it is the only thing between a loud conversation and a false
> alarm at three in the morning. Set it to 0.9500 to get the old rule back — 7 more episodes on the
> corpus, and the way open again.

That is the honest form of a safety trade-off: state what you gain, state what you lose, and state
what you have not measured.

## Clipping refusal

`CRYNET_CLIP_PEAK = 31000` of 32767 — **0.946 of full scale**. A window that reaches it is refused
before any DSP runs.

The physics: the INMP441 is a **fixed-gain** digital microphone, −26 dBFS ±3 dB. Its L/R pin selects
the channel, not the gain. When the sound pressure exceeds what it can represent, it flat-tops
*inside the microphone*, before the 16-bit window ever sees it. The resulting harmonics are an
artefact of the clipping, not of the sound, and the model has never been trained on that artefact.

**There is no software cure.** Turning down a digital gain after the fact does not restore
information that was destroyed in the transducer. The correct behaviour is to refuse the corrupted
evidence — and the system's redundancy handles the rest: the **bystander cot**, further from the
baby and therefore unclipped, announces the cry instead. That is exactly what was observed on the
bench.

## Hold, arbitration and hysteresis

| Mechanism | Constant | Behaviour |
|---|---|---|
| Cry hold | `CRY_HOLD_MS` 8000 | the announcement outlives the window that confirmed it, so the display does not flicker while the cry goes on |
| Re-cooldown | `RECOOLDOWN_MS` 1500 | minimum gap between verdicts on one node |
| Primary label | loudest crying cot | the panel names one cot as primary |
| Switch margin | `COT_SWITCH_MARGIN` **1.5×** | another cot must be half again as loud |
| Switch dwell | `COT_SWITCH_DWELL_MS` **1500 ms** | …and stay that loud for a second and a half |

The hysteresis is not decoration, and with **two** cots it is not an edge case either. One baby, two
microphones a metre apart, one cry: the two RMS readings land within a few dB of each other, so
without the margin and the dwell the primary label oscillates — "first cot 1, then cot 1 and 2, then
cot 2" — while nothing about the room has changed.

The alert names **one** cot for the same reason it holds for eight seconds: one cry must be one buzz.
The `crying_mask` still carries every crying cot, so nothing is thrown away — and since **D-86** the
wrist's alert face reads that mask and names **every** crying cot, while the packet and the buzz stay
one-cot. The screen and the buzz are deliberately different: the caregiver needs the whole list to
look at, and one pulse to act on. Two cots crying at once was staged on 2026-11-20 and the mask sat at
`0x03` for fifteen seconds; [Chapter 8](#chapter-08) has the capture.

## Deafness is an alert, not a silence

`alert_type = 3` is raised when a cot's audio cannot be obtained or every window it sends is refused.
The wearable **buzzes** for it, with the same edge-test as a cry so it buzzes once.

The reasoning, from the wearable's own source: *"It is not being watched, and the caregiver has to
hear that from the wrist, not only see it on the hub's panel."* A monitor that fails silently is worse
than no monitor, because it produces false confidence.

## The policy in one sentence

**Announce only when the model is saturated and the window is physically plausible; refuse corrupted
evidence outright; hold the announcement so it does not flicker; require sustained dominance before
naming a different cot; and buzz the caregiver when the system cannot hear.**