# Chapter 21 — Glossary

Every term a defender might be asked about, defined once. Where a term has a project-specific
meaning that differs from its ordinary one, that is stated.

---

## A

**ADC / ID scale / `IN_SCALE`, `IN_ZP`** — the affine parameters that map a float into the model's
INT8 input. `q = round(v / scale) + zero_point`, clamped to [−128, 127]. The deployed model's
`IN_SCALE` is 0.116329655 and `IN_ZP` is −70. These are re-derived on every training run, which
is why the artefact-drift check exists.

**Adaptive trigger (D-63)** — the node's trigger, defined as a **multiple of the node's own running
noise floor** rather than a fixed level. `TRIGGER_MULT 3.0`, clamped to [0.005, 0.030]. The floor
rises exponentially (`g_floor += (g_rms − g_floor) * 0.002f`, a ~50 s time constant) and falls
instantly. Two consecutive readings above the level are required.

**Announcement rule** — the hub's policy for turning a window's model output into an alert. Six
gates, in the order given in [Chapter 10](#chapter-10). **The log is the evidence; the
wrist is the output** — an alert proves a notification was published, not that the right cot was
named.

**Arduino CLI (`arduino-cli`)** — the Arduino IDE's command-line compiler, used to build the node
and the wearable against core **3.3.12**.

**Arena (tensor arena)** — the single scratch buffer TFLite Micro allocates for the model. 262,144 B
reserved, 108,328 B used, and it lives in **PSRAM** (open item O-4).

---

## B

**Bandpass / crest factor** — the ratio of a signal's peak to its RMS. A cry in this system has a
crest of 2.2–2.9; the loud music that used to false-alarm had 5.6; the loudest film had 6.6–6.9.
`CRYNET_QUIET_CREST 3.5f` is the gate that uses this.

**BC547** — the small-signal NPN transistor that switches the haptic motor's current. Used here as
a **low-side switch**: the motor's + lead goes to 3.3 V through a 22 Ω stall cap, and the
transistor pulls the motor's − lead to ground.

**Basic auth** — how the caregiver's browser authenticates to the dashboard: a username and
password, separate from the hub's upload token on purpose — a leaked password only reads the
record; a leaked token writes to it (Chapter 12).

**BLE** — Bluetooth Low Energy. The hub is a **peripheral and broadcaster** (never a central); the
wearable is the client.

**Burst** — one complete window of audio moving from a node to the hub: **286 fragments** of
224 payload bytes each, ESP-NOW, unicast, with a CRC-16 per fragment and a CRC-32 over the whole
window.

---

## C

**CMVN** — **cepstral mean and variance normalisation**, applied over the *whole* 81 × 64 feature
plane of a window: one mean and one standard deviation, with `+1e-6f` in the denominator. This is
what makes the model **level-invariant** — ICD cries sit at RMS ≈ 0.006 while negatives sit at
0.3–0.46, and without CMVN the model would be a level meter.

**`CRYNET_TRIGGER_RMS`** — 0.030. The hub's fixed audio-pull threshold. *Not* the node's trigger,
which is adaptive.

**CRC-16/CCITT-FALSE** — the per-fragment checksum (polynomial 0x1021, init 0xFFFF, no reflection).
**CRC-32/IEEE** — the whole-window checksum, computed on the host with `zlib.crc32`.

**CRC-32 MATCH** — the log line that means the window the hub reassembled is bit-identical to the
window the node froze. It is the proof that the audio crossed the radio unchanged.

**COTS 1 2** — the wearable's alert-face label when **both** cots are crying (D-86). Built from the
state characteristic's `crying_mask` unioned with the cot the alert packet named. Rendered at text
size 2 (96 px) because size 3 would be 144 px on a 128 px glass. One cot still reads `COT n` at size 3.

**Cry mode (D-69)** — the node's behaviour after it has frozen a window: it will not freeze
again until the room goes quiet (`g_rms < 0.01f && g_loud_streak == 0`), unless a much louder
sound arrives (`g_rms >= 3.0f * g_frozen_rms`).

**Cry log** — the hub's record of every event, thirty-two bytes per record in six megabytes of
SPIFFS reserved for it from the first build. Written whether or not there is a network; uploaded in
batches when there is. Its record numbers are what the wrist's alert shows and what the dashboard
stores (Chapter 12).

---

## D

**D-n** — a **decision** in `DECISIONS.md`: what was decided, why, and what it cost. **108 decision
rows** numbered D-1…D-108, carrying **106 distinct numbers**: D-51 and D-52 were each used twice for
different decisions, and D-70 and D-95 were skipped. All 108 are in this repository's file and
reproduced in Appendix A.

**D1 (Cloudflare)** — the SQLite database behind the hosted dashboard copy. One Worker, one D1
database, two secrets; see Chapter 12 and `dashboard/worker/README.md`.

**DIO / QIO** — the two flash access modes. This board **must be booted with DIO**; a QIO image
watchdog-resets in a loop before the bootloader has configured its own timing. The bootloader
switches to QIO by itself once running, so DIO costs nothing. The trap: `sdkconfig` shows the
*choice symbol* `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y` while the *string* esptool acts on says
`dio`.

**DFT / probe** — the hub's **boot self-check**: it computes log-Mel features on known probe audio
and compares them with references generated by the notebook's own front end. Pass is
**5184/5184 features exact on every probe**, plus a PCM CRC check. The hub refuses to bring up the
radio, Bluetooth or the display if the probes fail.

**Dropout / fade** — the mic's DC offset. The INMP441 sits at about **+18,000 counts**, so the front
end subtracts the mean in exact **int32** arithmetic before anything else.

---

## E

**ESC-50** — a 2,000-clip environmental sound corpus. 40 of its clips are `crying_baby` and are
held out entirely as a cross-domain test; the other 1,960 are negatives.

**ESP-NOW** — Espressif's Wi-Fi-derivative protocol: no router, no association, direct
point-to-point frames on a chosen channel (**channel 6** here).

**ESP-NN** — Espressif's optimised kernels for INT8 neural networks. On an S3 it is the difference
between ~40 ms and ~2.3 s per convnet invoke. It is vendored and pinned alongside the TFLM port.

**ESP-IDF** — Espressif's IoT framework, and the hub's. **6.1.0** in this project, installed **by
hand** (D-45).

---

## F

**FIR / filterbank / `slaney`** — the Mel filterbank, generated by `librosa` with the **slaney**
normalisation (not HTK), 64 bands from 20 Hz to 8 kHz, with **497 non-zero weights**. The same
filterbank is emitted as a C table, so the firmware and the training pipeline compute *identical*
features.

**`FROZEN_HOLD_MS`** — 3000. How long the node keeps a frozen window before discarding it.

**FLOOR (noise floor)** — the node's running estimate of the room's background level. In the
reference room it settled at **0.0028** with a level of 0.0083.

---

## G

**GAP (global average pooling)** — the model reduces each 16-channel feature map to one number per
channel before the dense layers. It is what keeps the parameter count at 122,770.

**GTZAN** — the 1,000-clip, ten-genre music corpus. It was **not** in the training mix until D-51,
which is why the model used to false-alarm on **8.19 %** of it. Now **0.21 %**.

---

## H

**Hann window** — the 512-point analysis window, **symmetric** (not periodic). Symmetric matters:
the two differ by one sample in the endpoints, which is enough to break the parity test.

**Hop** — 400 samples (25 ms). 81 frames fit in 2.0 s after 256 samples of front padding and 512
of rear padding.

---

## I

**I-n** — an **issue** in `DECISIONS.md`: what it looked like, how it was diagnosed, what was done,
what happened. 41 numbered, I-1…I-41.

**ILI9341** — the 2.8" 320 × 240 TFT controller on the hub. Driven by a hand-written driver
(`ili9341.c`, 413 lines) over SPI2 at 40 MHz, write-only.

**INT8** — 8-bit integer inference. The deployed model is **137,384 bytes**. Measured against
float32: ΔAUC **−0.00137**, decision agreement **99.956 %** over 11,386 windows.

**IRQ / ISR** — an interrupt. The hub's radio receive path runs in a Wi-Fi callback, and one
specific lesson (**D-2x, the peer deadlock**) is that adding a peer from inside that callback
deadlocks: the peer must be added **deferred**, out of the callback.

---

## J

**Jetson / JSON / JPEG** — not used.

---

## K

**Keyed / key-value** — not used.

---

## L

**Librosa** — the Python audio library whose `slaney` Mel filterbank and log scaling the C front
end reproduces exactly.

**`log_mel` / `log10(max(P, 1e-10))`** — the power spectrum is converted to decibels and floored at
**−80 dB** before CMVN.

**LX-LCBST** — the adjustable boost module that takes a 1-cell Li-ion to 4.2–28 V. Its trimpot
must be set to **5.1 V before any board is attached** (D-84).

---

## M

**Mel band** — one of the 64 triangular filters of the Mel filterbank. 64 of them, over 20 Hz–8 kHz.

**Model data (`model_data.h`)** — the INT8 model as a C byte array. 8,604 lines of generated data;
it is the reason the appendix reproduces the source but not this file.

**MSB / LSB** — the on-device feature-parity criterion is **worst ≤ 1 LSB** and **≤ 1 % of the
5,184 features differing**; the boot probes require **exact** agreement.

**Link bar / signal bar** — the four-bar glyph that shows the strength of a radio link, on the hub's
panel for each cot and on each cot's console for the hub. Four bars above −60 dBm, three above
−70, two above −80, one above −90. **The two ends measure different directions** — the hub reads
the cot's telemetry, the cot reads the hub's heartbeat — so they are not expected to agree.

---

---

## N

**NVS** — the ESP-IDF **non-volatile storage** partition. The node's id lives there, so it survives
a reflash — provided the flash tool does not erase that partition. That proviso is why the offline
flasher writes the flash *regions* rather than one merged file: a merged image fills the NVS gap
with `0xFF` and would silently turn a working cot into an invisible one.

**Node id** — the cot's number, **1 or 2**. It is not a label: the hub's receive path drops any frame
whose id falls outside 1..2 before it can claim a slot, so a cot on any other number is never heard.
`NODE_LINK_MAX_NODES` is **2** and `HUB_DISPLAY_MAX_NODES` is **2**; the sketch carries
`CRYNET_COT_COUNT = 2` to match. The id is set over the serial console with `id 1` / `id 2`.

**`node_capture`** — the second node sketch: it records raw audio over USB and makes no decisions.
It is how the in-domain corpus was collected.

**Node (cot node)** — an ESP32-C3 **Pro Mini** with an INMP441. It samples at 16 kHz, tracks its own
noise floor, freezes a two-second window when something crosses its trigger, and sends that window
to the hub as a 286-fragment ESP-NOW burst.

**Heartbeat** — a twelve-byte frame the hub broadcasts **once a second** asking for nothing. Its only
job is to give each cot an RSSI reading of the hub, from which the cot builds its own link bar. It
shares the REQUEST's layout exactly; a heartbeat built with the full header would be sixteen bytes
and every one would be rejected as malformed. `research/test_heartbeat_framing.py` holds the rule.

---

**Notch** — the one-pixel line on a cot card's level bar marking **that cot's own trigger level**: the
level at which it ships audio to the model rather than only listening. The bar is square-rooted and
scaled to `LEVEL_BAR_FULL 0.25`, so the notch and the fill agree by construction. The bar turns
**amber** once the cot crosses it and **rose** while the hub is announcing a cry from it.

---

---

## O

**O-n** — an **open item**: work identified and deferred. **O-1…O-9** in `DECISIONS.md`, plus the two-cot
sub-items **O-1a…O-1g** and **O-10…O-13** discussed in [Chapter 19](#chapter-19). **O-2** (the model has
never heard a real infant cry) is the largest, and **O-1d** (no *runtime* has ever been measured, though
the wearable has run on its pouch) is the largest hardware gap. **O-1b is closed** by D-86; **O-1f** is
this repo's unflashed D-86 image and **O-1g** the microphone's close-range blind spot.

**OdB (one-decibel-below)** — not used.

**Prebuilt / offline image** — the built firmware for all three roles, committed in
`firmware/prebuilt/` with a `SHA256SUMS` manifest and a `BUILD_INFO.json` recording the SHA-256 of
every source file that went into each image. `flash_unit.py` writes it with `esptool` alone — no
compiler, no toolchain, no network — and `check_prebuilt.py` refuses to flash an image that is stale
relative to its source.

---

---

## P

**Presence report** — the hub's every-30-second post that says who is in the room: itself, and for
each cot whether it is answering, deaf, and how strong its radio is. A report yields to a cot's
burst (up to 20 s), the service calls a hub gone after 90 s without one (D-105), and a cot is online
only while the hub's word about it is fresh (D-108).

**Pro Mini (ESP32-C3 Pro Mini)** — the board the **two cot nodes** use. Same ESP32-C3 chip, 4 MB
flash and native USB (`303A:1001`) as the SuperMini, so the firmware image is identical; the swap was
made and verified live on 2026-11-02. The two on the bench are `90:DA:72:85:C5:44` (id 1) and
`90:DA:72:87:CB:98` (id 2). See **SuperMini** for the board that moved to the wrist.

**PSRAM** — the hub's 8 MB of octal external RAM. The framebuffer (153,600 B) lives here, and so
does the tensor arena. The DSP's scratch buffers **do not** — putting them in PSRAM took the front
end from 41.7 ms to 135 ms (D-46's neighbour, the memory move).

**P(cry)** — the model's output probability of a cry. On real audio in this room the model is not
ambivalent: measured values are either near-zero or saturated, with **nothing between 0.2148 and
0.9922** across 45 verdicts.

**Partial window** — a burst with holes in it. **A burst is analysed only when every one of its 286
fragments is present** (D-23): the link tolerates loss by *recovering* it, not by pretending it
away.

**Peaks / `CRYNET_CLIP_PEAK`** — 31000 (0.946 of full scale). A window whose peak reaches this is
**refused**, not clipped and analysed.

**Promiscuous mode (`CRYNET_LINK_PROMISCUOUS`)** — a build flag that counts the radio frames
carrying the CryNet magic against the frames the ESP-NOW layer hands up. It is the instrument that
separates "lost in the air" from "dropped by the hub's receive path".

**Prometheus / pytest** — not used.

---

## Q

**QIO** — see DIO.

**Quantisation** — see INT8 and `IN_SCALE`/`IN_ZP`.

**Quiet room** — the reference measurement: **0 false alarms in 236 windows** on this INMP441, and
**0 in 20.5 minutes** of a room with people talking.

---

## R

**Radio busy** — the fraction of time the radio is occupied. **89 %** in the busiest recorded session —
which is why the BLE advertising interval is throttled during a burst.

**Reassembly / resend** — the hub reassembles fragments into the window; if a fragment is missing it
logs "the burst stalled with N of 286 fragments", asks the node for the missing ones, and the
resend rounds recover nearly all of it. `RESEND_DEDUPE_MS 250` on **both** sides (same sequence
number **and** same bitmap).

**RMS** — root mean square, the project's usual level measure. Note the caveat: the quantity that
actually decides refusal is the **peak**, not the RMS (see O-14).

**Rotation (`MADCTL_MY`)** — the panel is **landscape-first** and wants `MADCTL_MY`, not the
`MADCTL_MV` the legacy firmware used. A legacy setting is not evidence about a different module.

---

## S

**SuperMini (ESP32-C3 SuperMini)** — the board the **wearable** uses. It was the original cot-node
prototype; when the cots moved to Pro Mini stock on 2026-11-02 this board was reassigned to the wrist.
Same chip and same FQBN as the Pro Mini, which is why one toolchain covers all three C3 units.

**SPIFFS** — the flash file system that holds the cry log, on the six-megabyte `storage` partition
the partition table reserved from the first build (D-96). Append-only from the log's point of view:
records are written once and never changed.

**SNTP** — how the hub learns the time when it is on a network. Two servers configured; the wall
clock is anchored to the hub's monotonic uptime and persisted in NVS, so a restart loses only the
duration of the power cut (Chapter 12).

**S3 / ESP32-S3** — the hub's MCU: dual-core Xtensa LX7 at 240 MHz, 512 KB SRAM, 8 MB PSRAM,
16 MB flash.

**Sample rate** — 16 kHz, mono, everywhere.

**Silane / slaney** — the two Mel-filterbank normalisations; this project uses **slaney**.

**Silence gate (`SILENCE_RMS_GATE`)** — 0.0015. Windows below it are not asked about.

**SMA / SNR / softmax** — the model's final layer is a two-way softmax over `[no_cry, cry]`.

**Splash** — the startup sequence on the panel (`SPLASH_MS 5600` = `BOOT_MS 2400` + the title card +
`FADE_MS 600`). Two faces: a boot face with the wordmark and a progress bar, and a title card with
the project's name, the owner's name and id, and `ESP32-S3 HUB - TWO COT NODES`.

**Static assert** — a compile-time check. There are **eight** in `crynet_dsp.c`, guarding the input
scale and zero-point, the output scale and zero-point, the silence gate, `N_SAMPLES 32000`,
`N_FRAMES 81` and `N_MELS 64`. They are the reason a mis-staged model fails at build time rather
than on a cot.

---

## T

**TFLM** — TensorFlow Lite Micro, the microcontroller inference runtime.

**TFLite** — the `.tflite` file itself; `crynet_int8.tflite` is the deployable artifact.

**Threshold** — 0.95 on the INT8 output, chosen as **the largest threshold in `arange(0.05, 0.96,
0.01)` whose recall is still ≥ 0.95**. It is calibrated on the validation fold, not chosen.

**Trigger** — the level at which audio is interesting enough to be sent. Three of them, and they
are different things:

| Trigger | Where | Value |
|---|---|---|
| The node's adaptive trigger | the node | **3 × the node's own floor**, clamped to [0.005, 0.030] |
| The hub's fixed pull | the hub | `CRYNET_TRIGGER_RMS` **0.030** |
| The announcement rule's gates | the hub | `CRYNET_ANNOUNCE_MIN_RMS` 0.006, `CRYNET_MAYBE_MIN_RMS` 0.020, `CRYNET_PULL_CRY_RMS` 0.050, `CRYNET_LOUD_ANNOUNCE_RMS` 0.080 |

---

## U

**UMD / USB CDC** — the C3's serial console. **USB CDC on boot must be enabled** or the console
never appears.

**Uptime / `up 0:39`** — the panel's footer shows the hub's uptime and the number of cots linked.

---

## V

**VCC / VBUS / VO+ / VO−** — the power-chain vocabulary. `VO+`/`VO−` are the LX-LCBST's output
terminals; `VBUS` is the USB 5 V rail, and **it is the same net as the board's 5 V pin** through
the board's protection diode. That is why the boost and USB must never be connected at the same
time (D-84).

**`VERBOSE` / `vs` / `volatile`** — not used in this sense.

---

## W

**Wearables / wearable** — the caregiver's wristband: an ESP32-C3 SuperMini, an SSD1306 OLED and a
coin ERM on a BC547 low-side drive. It runs **no model**. It receives a six-byte alert packet and
vibrates.

**Window** — two seconds of audio: 32,000 int16 samples at 16 kHz. The unit the model classifies
and the unit the radio carries.

**Wi-Fi coexistence** — ESP-NOW and BLE share one radio. The hub's Bluetooth is brought up **after**
the radio, and the advertising interval is throttled during a burst (Chapter 11).

**Watermark** — the number the uploader may claim as sent after a batch: everything up to it has
gone, nothing above it has. Clamped below the lowest number that did not fit in the batch and the
lowest number an open episode still holds, so the hub never says "sent" while a record is still
being measured (D-94).

**WDT / watchdog** — `rst:0x7 TG0WDT_SYS_RST` is the reset reason that identifies a QIO image
looping on this board.

---

## X

**XNNPACK** — a host-side delegate for TFLite. It is **filtered out** of the INT8 conversion,
because it has no TFLM kernel; the notebook asserts the operator list at export time and records it
in `deploy_config.json`.

---

## Y

**Y-axis / `MADCTL_MY`** — see Rotation.

---

## Z

**Zeropoint / zero-point** — see `IN_ZP`, `OUT_ZP`.

**Zlib** — the host's CRC-32 and DEFLATE library. `zlib.crc32` is the *host-side reimplementation of
the check*, used by `verify_burst.py` so that the reference is independent of the implementation
under test.

---

## Acronyms at a glance

| | | | |
|---|---|---|---|
| **ADC** | analog-to-digital converter | **LM** | linear model |
| **AP** | access point | **LRU** | least recently used |
| **AUC** | area under the ROC curve | **ML** | machine learning |
| **BLE** | Bluetooth Low Energy | **MP3/WAV** | audio container formats |
| **BN** | batch normalisation | **NR** | new radio (5G) |
| **BW** | bandwidth | **PSRAM** | pseudo-static RAM |
| **CMVN** | cepstral mean-variance normalisation | **PWM** | pulse-width modulation |
| **CNN** | convolutional neural network | **RIR** | room impulse response |
| **CRC** | cyclic redundancy check | **RMS** | root mean square |
| **CS** | chip select | **RTC/RTT** | real-time clock / round-trip time |
| **DC** | direct current (offset) | **SNR** | signal-to-noise ratio |
| **DFT** | discrete Fourier transform | **SoC** | system on a chip |
| **DMA** | direct memory access | **SPI** | Serial Peripheral Interface |
| **DSP** | digital signal processing | **SRAM/DRAM** | static / dynamic RAM |
| **FFT** | fast Fourier transform | **TFLM/TFLite** | TensorFlow Lite (Micro) |
| **GAP** | global average pooling | **TX/RX** | transmit / receive |
| **GPIO** | general-purpose I/O | **UART** | serial port |
| **I²S** | Inter-IC Sound (mic data bus) | **USB** | Universal Serial Bus |
| **IDF** | Espressif IoT Development Framework | **WAV** | audio file format |
| **INT8** | 8-bit integer | **WDT** | watchdog timer |

---

## The project's own vocabulary, in one table

| Term | Meaning |
|---|---|
| **D-n** | a decision — what, why, what it cost |
| **I-n** | an issue — the symptom, the diagnosis, the fix, the outcome |
| **O-n** | an open item — deferred work, with the reason it is still open |
| **The log is the evidence** | an alert proves a notification was published; only the hub's serial log proves the right cot was named, at what confidence, on what window |
| **The wrist is the output** | the wearable is what the caregiver feels; it is not the evidence |
| **The model has never heard a real infant cry** | every positive in the room is a phone-speaker proxy; the negatives are authentic |
| **Frozen contract** | the signal contract (D-11): the firmware, the exported tables and the weights change together or not at all |
| **One artifact per checkpoint** | the project's working discipline: deliver one thing, verify it, then move on |
| **Passive observation before intervention** | the host tools measure without stimulating, so a result cannot be an artefact of the tool |
| **Host-side reimplementation of the check** | verify the thing on the host with an independent implementation (`zlib.crc32`, the notebook's own front end), not with the code under test |
| **Measured vs projected** | every runtime figure is labelled *projected* until it is read off a cell. None is, yet (O-11) |
