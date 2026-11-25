# Part I — The system

## What CryNet is

CryNet is a monitor for an environment with more than one cot: a NICU bay, a maternity ward, a
daycare, a twin nursery. Two microphone nodes sit with the cots, one at each. Each samples its own microphone
continuously and decides for itself when something interesting has happened. When it does, it hands
its two seconds of audio to a central hub over a short-range radio link. The hub reassembles the
audio, runs a small neural network over it, and decides whether that sound is an infant cry. If it
is, the hub names the cot on its display, raises an alert over Bluetooth — which a caregiver's
wristband turns into a vibration — and writes the event to a record in its own flash, which a web
dashboard reads so that a cry at three in the morning is still visible at nine.

The three design choices that everything else follows from:

1. **The nodes decide when to speak; the hub decides what it means.** A node that hears nothing
   interesting sends almost nothing. This is what makes the radio work at all with two of them
   sharing one channel, and what keeps a battery node alive for a whole shift.
2. **Only the hub runs the model.** One ESP32-S3 with 8 MB of PSRAM is a far better place for a
   neural network than two small battery-powered nodes, and it means the model can be retrained
   and re-flashed in one place instead of at every cot.
3. **The wearable is a dumb, reliable terminal.** It runs no model. It receives an alert and
   vibrates. Everything about it is about being trusted to say something the caregiver must not
   miss.

## The three kinds of unit

| Unit | Board | Role | Key numbers |
|---|---|---|---|
| **Cot node** &times;2 | ESP32-C3 **Pro Mini** + INMP441 I&sup2;S MEMS microphone | Samples audio at 16 kHz, tracks its own noise floor, freezes a two-second window when a cry crosses the trigger, sends it to the hub | GPIO4/5/6 for I&sup2;S; ESP-NOW channel 6; 286-fragment burst; 75 % flash, 50 % RAM of the C3's budget |
| **Hub** | ESP32-S3-DevKitC-1 (dual-core Xtensa LX7 @ 240 MHz, 512 KB SRAM, 8 MB PSRAM) + 2.8" ILI9341 TFT | Reassembles windows, runs the DSP front end and an INT8 CNN, arbitrates between cots, drives the panel, serves the BLE alert service, keeps the cry log, uploads it over Wi-Fi and posts presence | 135 KB INT8 model; front end 41.7 ms, inference 101.8 ms per window; 14.3 % RAM, 77.2 % flash; 286/286 fragments, CRC-32 MATCH |
| **Wearable** | ESP32-C3 SuperMini + 0.96" SSD1306 OLED + coin ERM on a BC547 low-side switch | BLE client; shows the alert and which cot is crying; buzzes | GPIO7 &rarr; 2.2 k&Omega; &rarr; BC547 base; 22 &Omega; stall cap; 2.5 s haptic pulse train |

## Two cots, enforced in the link layer

The cot count is not a display setting. `NODE_LINK_MAX_NODES` is **2** and `HUB_DISPLAY_MAX_NODES`
is **2**, and the hub's receive path drops any frame whose node id falls outside 1..2 *before* it
can claim a slot:

```c
/* This dedicated hub monitors only cot IDs 1 and 2.  Reject other
 * IDs before they can occupy a slot or influence alerts. */
if (node_id < 1 || node_id > NODE_LINK_MAX_NODES) {
    return;
}
```

That is `node_link.c`, at the top of the frame handler, ahead of the counter that says a frame was
good. A third board powered up in the same room is not hidden from the panel &mdash; it is never
heard, cannot occupy a slot, and cannot influence an alert. The nodes know the rule too:
`CRYNET_COT_COUNT = 2` in the sketch, and a node whose id is outside 1..2 prints a warning at boot,
because the hub will ignore every other number. Ids are set over the node's serial console with
`id 1` and `id 2` and live in NVS, so they survive a reflash &mdash; which was checked on the bench,
not assumed.

The reason to enforce it in the link layer rather than the panel is that a slot is a resource. Each
one carries a 64 KB window buffer and a burst state machine. A hub that accepted a third id and
then declined to draw it would still spend the memory, still arbitrate against it, and still let it
hold the alert. Refusing the frame is the only version of "two cots" that is true everywhere.

## The honest status

Three things must be said plainly before anything else, because they shape how every later
number should be read.

**The model has never heard a real infant cry.** Every cry it has been tested against is a
*recording played through a phone speaker* &mdash; compressed, band-limited and EQ'd by a small
loudspeaker in a plastic case. The negatives are authentic (this room, this microphone), but the
positives are a proxy. On that proxy the model is strong; on a real infant it is unproven. This is
recorded as O-2 and it is the single largest accuracy risk in the project.

**One unit has run from a cell; no runtime has ever been measured.** The wearable ran on its
**Li-Po pouch** during part of the 2026-11-20 bench session and kept working — so the battery path is
not wholly untried. But the nodes and the hub have only ever been USB-powered, **no unit's battery
life has been measured**, the boost module's own quiescent draw is unquantified, and the haptic buzz
went missing while the wrist was on the pouch (a sagging 3.3 V rail is the live candidate). The
runtime figures in the documents are *projections* from the regulator's behaviour and are labelled as
such. This is O-1d, and [Chapter 13](#chapter-13) carries the arithmetic and the three rules the 5 V
chain must obey (D-84).

Two smaller things belong in the same breath, because a defence should not be caught by them:
the node's I&sup2;S zero watchdog is **committed but not flashed** (D-79 / O-1c &mdash; the boards are
mid-solder), and the microphone has a **close-range blind spot** &mdash; a source loud enough to drive
it to the rail produces a window the hub refuses outright, which was measured on 2026-11-20 and is
recorded as O-1g.

The wrist, meanwhile, **names every crying cot** (D-86). The alert *packet* still names one &mdash; the
loudest &mdash; because one cry must be one buzz; the *screen* reads the crying mask and lists them all.
Two cots at once was staged on 2026-11-20 and the mask held at `0x03` for fifteen seconds.

Everything else described in this document was measured on real hardware.

## What the system is *not*

- It is **not a certified infant monitor**. It is an academic prototype. Detection accuracy, radio
  delivery guarantees, battery life and alarm behaviour have not been established to any
  safety-critical standard, and it does not replace supervision.
- It is **not a cause classifier**. The model is binary: cry or no cry. It does not distinguish
  hunger from pain from tiredness. That is deliberate (D-1): the Bluetooth alert packet that the
  wearable was written against has one bit for it.
- It is **not a baby monitor that replaces a parent**. It is a second pair of eyes that wakes
  someone up.
- It has **no battery monitoring at all** (D-83). The battery sense and every status LED were
  designed, costed, and then withdrawn on purpose. Nothing in the system will tell a caregiver
  that a cell is nearly flat; the cells are watched by eye.

## The system in one paragraph

Two ESP32-C3 cot nodes with INMP441 microphones sample a room at 16 kHz, each tracking its own
running noise floor; when a sound crosses three times that floor the node freezes the two seconds
centred on the crossing and streams them to an ESP32-S3 hub as a 286-fragment ESP-NOW burst with a
per-fragment CRC-16 and a whole-window CRC-32. The hub reassembles the burst, refuses it outright
if any sample saturated the microphone, computes a 64-band log-Mel spectrogram of the two seconds,
standardises it, quantises it to INT8 and runs a 122,770-parameter CNN that returns P(cry); the
window is announced only if the model is near-saturated, or if two consecutive windows agree and
the second carries real energy and the right crest. A cry is held for eight seconds, the loudest
cot keeps the alert unless another cot is clearly louder for a second and a half, and the whole
system state is published over Bluetooth as a six-byte alert packet and an eight-byte state packet,
which the wristband turns into a 2.5-second vibration and a face that names the cot. Every event —
each cry episode, each deaf spell, each boot — is also written to a thirty-two-byte record in six
megabytes of the hub's own flash, stamped with the wall clock where the hub knows it and marked
untimed where it does not; when the hub is on a network it uploads those records to a dashboard —
one offline copy, one hosted — which shows who is here, what happened, and when.
