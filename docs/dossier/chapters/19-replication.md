# Chapter 19 — Replication: building the whole thing from an empty checkout

## The rule that makes this chapter possible

**You do not need a Kaggle account, a GPU, or 4.6 GB of downloads to build and flash the system.**

The trained artifacts are **in the repository**:

| Artifact | Path | Committed? |
|---|---|---|
| The INT8 model | `research/out/crynet_int8.tflite` | **yes** |
| The model as a C array | `research/out/model_data.h` | **yes** |
| The Mel filterbank, Hann window, quantisation constants | `research/out/crynet_tables.h` | **yes** |
| The portable reference front end | `research/out/dsp_crynet.c`, `.h` | **yes** |
| The deployment manifest | `research/out/deploy_config.json` | **yes** |
| The metrics | `research/out/metrics.json` | **yes** |
| The staged copies the firmware actually compiles | `firmware/hub_infer/components/crynet_model/include/` | **yes** |

`research/out/` holds **176 tracked files** — the artifacts *and* the logs that produced every number
in this dossier. So the repository alone is enough to rebuild the firmware, flash it, and reproduce
every bench measurement.

And the repository alone is enough to flash it **without a compiler at all**: `firmware/prebuilt/` holds
the built images for all three roles, with a SHA-256 manifest and a source-fingerprint record. See
§7.4.

What the repository is **not** enough for is **retraining**. The training run needs a GPU and the
corpora, and that is a separate, optional path — given in §11 below.

The corollary matters for the defence: **the model is a committed, hash-identified artifact**, not a
result someone has to trust. `deploy_config.json` carries the SHA-256, and
`check_artifact_drift.py` proves that the bytes the firmware compiles are the bytes the
evaluation scripts scored.

---

## 0. What you need before you start

| Thing | Why | Where it comes from |
|---|---|---|
| A Windows or Linux machine with git, Python and a C compiler | everything | free |
| **Python 3.11.9** | the research pipeline | python.org |
| PlatformIO **6.2.0** | builds the hub | `pip install platformio` |
| `platform-espressif32` **8.0.0** | the board support package | PlatformIO, on first build |
| **ESP-IDF 6.1.0** (`framework-espidf 4.60100.0`) | the hub's framework | **installed by hand — see §2.2. This is the single biggest trap in the project** |
| Arduino CLI + core **3.3.12** | builds the node and the wearable | `arduino-cli` + the ESP32 board package |
| `ziglang` **21.1.0** | the host C compiler for the parity test | `pip install ziglang` (there is no gcc on the reference machine) |
| An ESP32-S3-DevKitC-1 N16R8 | the hub | the bench |
| 2 × ESP32-C3 **Pro Mini** + INMP441 | the cot nodes | the bench |
| 1 × ESP32-C3 SuperMini + SSD1306 + coin ERM | the wearable | the bench |

**Versions that are known to work together** (Chapter 16):

```
Python 3.11.9 · TensorFlow 2.21.0 (CPU) · librosa 0.11.0 · soundfile 0.14.0
numpy 2.4.6 · scipy 1.17.1 · ziglang 21.1.0 · PlatformIO 6.2.0
platform-espressif32 8.0.0 · ESP-IDF 6.1.0 · Arduino ESP32 core 3.3.12
FQBN: esp32:esp32:weact_studio_esp32c3
```

TensorFlow is only needed for the research pipeline, not for the firmware. If you only want to
build and flash, you can skip it entirely.

---

## 1. Get the code

```bash
git clone https://github.com/Amazo123/CryNet-TwoNode.git
cd CryNet-TwoNode
git log --oneline -1        # 0a82711  at the time of writing
```

Check that the artifacts are present:

```bash
ls research/out/crynet_int8.tflite research/out/model_data.h research/out/crynet_tables.h
ls firmware/hub_infer/components/crynet_model/include/
```

If `research/out/` is missing the model files, the clone is incomplete — they are tracked, so
`git checkout -- research/out` will restore them.

---

## 2. The toolchain

### 2.1 PlatformIO

```bash
pip install platformio==6.2.0
pio --version            # PlatformIO Core, version 6.2.0
```

The first build downloads `platform-espressif32 8.0.0` and the Xtensa toolchain. That download is
several hundred megabytes and takes a while. It happens once.

### 2.2 ESP-IDF 6.1.0 — install it **by hand**

This is D-45 and it is the trap that cost the project real time. **Do not put a `platform_packages`
URL for the framework in `platformio.ini`.** PlatformIO 6.2 installs a URL-specified package by
treating the archive as an **npm package**: it picks the wrong `package.json` out of the tree,
writes a bogus version into `.piopm`, and leaves `packages/framework-espidf` holding only a
**test-fixture package**. CMake then fails with:

```
include could not find requested file: .../tools/cmake/project.cmake
```

The fix that worked, and it is idempotent:

1. `pio pkg install` once (or let the first build fail) so the platform package is present.
2. Find the platform's own framework archive — it ships with
   `platform-espressif32 8.0.0` as `framework-espidf 4.60100.0` (= ESP-IDF **6.1.0**). It is
   normally in `~/.platformio/.cache/downloads/` or the platform's own `packages/` directory.
3. Delete `~/.platformio/packages/framework-espidf` and **move the fully extracted tree into that
   place**. A partially extracted tree (missing `tools/`, `main/`, `examples/`, `version.txt`) is
   the signature of an install that was interrupted — delete it and start again.
4. Write `~/.platformio/packages/framework-espidf/.piopm` **by hand**:

```json
{"type": "tool", "name": "framework-espidf", "version": "4.60100.0", "spec": {"owner": "platformio", "id": null, "name": "framework-espidf", "requirements": "~4.60100.0", "uri": null}}
```

5. Confirm: `cat ~/.platformio/packages/framework-espidf/version.txt` → `6.1.0`.

**Why 6.1.0 and not 5.3.2.** 5.3.2 was the original target, but PlatformIO's registry only offers
`~4.60100.0` (6.1.0) or `~3.50505.0` (5.5.0) for this platform, and the 5.3.2 archive could not be
installed through PlatformIO at all. 6.1.0 satisfies the TFLM port's `idf >= 5.1` requirement.

**Fallback if the port misbehaves under IDF 6.1 / GCC 14:** install `platform-espressif32 6.9.0`
(framework `~3.50301.0` = IDF 5.3.1, toolchain 13.2.0) and let PlatformIO fetch both.

### 2.3 Arduino CLI, for the node and the wearable

```bash
pip install arduino-cli          # or download the binary from arduino.cc
arduino-cli config init
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32@3.3.12
arduino-cli board listall | findstr -i weact
```

The board is **WeAct Studio ESP32C3** — FQBN `esp32:esp32:weact_studio_esp32c3`. It is the exact
module on the bench, and its definition is what the node's USB CDC configuration depends on.

> **USB CDC on boot must be enabled** in the board options, or the serial console never appears.
> `firmware/tools/flash_node.py` uses the FQBN as-is; if the console is missing, check this first.

---

## 3. Fetch the pinned firmware dependencies

```bash
bash firmware/tools/fetch_deps.sh
```

This clones exactly two trees, at exactly two revisions:

| Dependency | Repository | Revision |
|---|---|---|
| esp-tflite-micro | `github.com/espressif/esp-tflite-micro` | `dd4085950a119d9e33a6de1d7be1fc7fe29e0cfc` |
| esp-nn | `github.com/espressif/esp-nn` | `744d48deae6aa4a4d7b93b6a80f548d5298813a4` |

into `firmware/hub_infer/components/`, and then runs `patch_deps.py`, which makes the vendored
TFLM port build against the vendored `esp-nn` instead of the component registry. **This is what
keeps the build offline and pinned.** The script is idempotent — re-running it on an existing
checkout does not re-clone.

> **Why the vendoring is not untidiness.** PlatformIO re-compiles IDF components with SCons using
> the *source basename* for object names, and the TFLM port has **twelve basename collisions** —
> the build dies with *"Multiple ways to build the same target were specified for …/circular_buffer.cc.o"*.
> Moving the components **inside** `firmware/hub_infer/components/` makes the paths relative and
> distinct. (D-46)

---

## 4. Prove there is no artefact drift — **before you build**

```bash
python firmware/tools/check_artifact_drift.py
```

This checks five things and must print **PASS**:

1. `research/out/crynet_int8.tflite`'s SHA-256 equals `deploy_config.json`'s `model_sha256`;
2. `model_data.h` embeds exactly `model_bytes` bytes;
3. `crynet_tables.h` defines the same macros as the ones mirrored into `crynet_model.h`;
4. `deploy_config.json` agrees with `crynet_tables.h` on scale, zero-point and threshold;
5. the staged copies under `firmware/hub_infer/components/` are **byte-identical** to the ones in
   `research/out/`.

This check exists because the notebook **re-derives the threshold and the quantisation scales on
every run**. Dropping a new set of Kaggle outputs into `research/out/` without restaging them
leaves the firmware compiling against the *old* constants with the *new* weights — a silent
mismatch that no compiler would catch.

If it fails, the message says what moved. Restage the artifacts and re-run.

---

## 5. Build the hub

```bash
cd firmware/hub_infer
python -m platformio run
```

About a minute incremental; several minutes the first time (the toolchain is being unpacked).

**Expected at the end:**

| Figure | Value |
|---|---|
| `firmware.bin` | ~1.3 MB |
| Flash used | 61.9 % of 2 MB (the partition table is `partitions_16mb.csv`, so 16 MB flash) |
| RAM used | 12.9 % (42,236 B) of 512 KB |
| Free internal heap at boot | 298,763 B |

The build prints `ESP-NN enabled` and the octal PSRAM at 80 MHz.

> **The flash-mode subtlety (D-47).** `sdkconfig.esp32s3` still shows
> `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y` as the *choice symbol*, while the *string* that esptool
> actually acts on says **`dio`**. Reading only the choice symbol gives the wrong answer. The
> effective configuration is `CONFIG_ESPTOOLPY_FLASHMODE="dio"`, and both `bootloader.bin` and
> `firmware.bin` carry flash-mode byte **`0x02`**. The bootloader switches the chip to QIO by
> itself once it is running, so DIO costs nothing at this workload — and a **QIO image makes this
> board watchdog-reset in a loop** (`rst:0x7 TG0WDT_SYS_RST`, no application output at all),
> because the ROM cannot read the flash in QIO before the bootloader has configured its own timing.

---

## 6. Build the node and the wearable

The Arduino IDE builds a sketch from **its own folder**, and the sources live in the repository,
so they are copied into the sketchbook first:

```bash
python firmware/tools/install_sketches.py
```

That copies `node_crynet`, `node_capture` and `wearable_crynet` into `~/Documents/Arduino/`.

Then either use the Arduino IDE (board **WeAct Studio ESP32C3**, USB CDC on boot enabled), or
build from the command line:

```bash
arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/node/node_crynet
arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/node/node_capture
arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/wearable/wearable_crynet
```

Or, in one command per unit, which builds *and* flashes:

```bash
python firmware/tools/flash_node.py --port COM30 --sketch node
```

| Figure | Value |
|---|---|
| Node flash / RAM (current tree, compiled 2026-11-23) | **983,177 B (75 %) / 166,404 B (50 %)** |
| App partition / RAM budget on the C3 | 1,310,720 B / 327,680 B |

> **I-11.** The Arduino core's serial driver can block on a full TX buffer. The sketches call
> `Serial.setTxTimeoutMs(0)` so a write never stalls the audio loop. If you edit the sketches and
> see the trigger stop working, check that line survived.

---

## 7. Flash

### 7.1 The hub

```bash
python firmware/tools/flash_hub.py --port COM32
```

This writes the three images at the offsets the partition table expects — `bootloader.bin` at
`0x0`, `partitions.bin` at `0x8000`, `firmware.bin` at `0x10000` — and then prints the boot log.

For a graphical flasher (the Arduino IDE's "ESP32 Flash Tools" extension), make one combined file:

```bash
python firmware/tools/flash_hub.py --merged
```

> **The merged image MUST be built with `--flash-mode dio`.** `flash_hub.py` passes it explicitly.
> A merged image built with QIO produces the watchdog-reset loop described in §5.

Other flags: `--flash-only` (flash, no log), `--log-only --seconds N` (just watch).

### 7.2 The nodes and the wearable

```bash
python firmware/tools/flash_node.py --port COM31 --sketch node      # cot node 1
python firmware/tools/flash_node.py --port COM37 --sketch node      # cot node 2
python firmware/tools/flash_node.py --port COM30 --sketch wearable # the wristband
```

The port map above is the one read from the last verified bench session with `who_is_who.py`; your
ports will differ, and the script is how you find out which is which.

> **I-40 — the wrong-port trap.** A flash aimed at the wrong serial port parks the cot node in its
> **download mode**, and the radio then goes silent (**0 frames for two minutes**). The hub is on a
> CH343 bridge (COM32 on the reference bench); the C3 units enumerate on their own native USB.
> **Check `who_is_who.py` before you flash anything.**

### 7.3 Which unit is which

```bash
python firmware/tools/who_is_who.py
```

The node id lives in **NVS**, so it survives a reflash — but only if the flash tool does not erase
that partition. This script resolves the ambiguity rather than leaving it to guesswork.

**On a two-cot system the id is not a label — it is the difference between being monitored and being
invisible.** The hub's receive path drops any frame whose node id is outside 1..2 before it can claim
a slot, so a cot left on a MAC-derived id is simply never heard. A node outside 1..2 prints a warning
at boot, but the definitive check is that the hub's console lists it:

```
node 1 heard for the first time
node 2 heard for the first time
```

Set the ids over each cot's own serial console, then **re-check them after the flash** — the id lives
in NVS, so a flash that erased that partition would leave a cot invisible with no other symptom:

```
id 1     # on COM31
id 2     # on COM37
```

```bash
python firmware/tools/node_console.py --port COM31 --command "id 1"
```

---

### 7.4 The offline path — no compiler, no network, no toolchain

This is the route that exists because the owner flashes boards himself, offline, on a machine that may
never have seen this project. `firmware/prebuilt/` holds the built images for all three roles. It
needs exactly one executable on the machine: **`esptool`**.

```powershell
python firmware/tools/flash_unit.py --check                              # verify the images
python firmware/tools/flash_unit.py --list                               # what is on this machine

python firmware/tools/flash_unit.py --role hub     --port COM32 --log 25
python firmware/tools/flash_unit.py --role node    --port COM31 --log 15
python firmware/tools/flash_unit.py --role wearable --port COM30 --log 15
```

`--backup` writes the board's current flash to a file first; `--log N` prints N seconds of the boot
log after the write.

**Two rules the tool enforces, and both matter.**

1. **The regions are written, not one merged file.** The offsets are `bootloader.bin` 0x0,
   `partitions.bin` 0x8000, `boot_app0.bin` 0xe000, `app.bin` 0x10000. A merged image fills the gaps
   between regions with `0xFF`, and writing that would **erase NVS** — which is where a cot keeps its
   id. The skipped gap (0x9000–0xE000 on the C3, 0x9000–0xF000 on the hub) is deliberate. A merged
   flash would silently turn a working cot into an invisible one.
2. **The hub images are DIO.** A QIO image makes the S3 watchdog-reset in a loop right after power-on
   (D-47). The bootloader header in `hub/bootloader.bin` says DIO.

**The staleness check is the important part.** `BUILD_INFO.json` records, per role, the SHA-256 of
**every source file** that went into that image — 52 files for the hub, one for each sketch — with an
explicit rule set for what does not count (build directories, `sdkconfig*`, the vendored third-party
trees, editor artefacts). `check_prebuilt.py` recomputes those fingerprints and compares.

```powershell
python firmware/tools/check_prebuilt.py     # are the images current with the source?
```

At the time of writing it reports:

```
== the offline images vs the source ==
  images: 11 files, all match SHA256SUMS
  hub       source fingerprint 7ebe61d46bec5b4b... over 52 files - up to date
  node      source fingerprint a715bd57edc46a8a... over 1 files - up to date
  wearable  source fingerprint 7071ab878821afe3... over 1 files - up to date

OK  the offline images are up to date with the source
```

`flash.bat` runs the same check in PowerShell — so it needs no Python — before it writes anything, and
refuses a stale or damaged image. A GitHub workflow (`.github/workflows/prebuilt-check.yml`) rebuilds
all three on every push and fails if the result differs from what is committed.

The reason this machinery is worth having: **the failure it prevents is silent.** A stale image
flashes successfully, boots, and behaves like the old firmware, and the person holding the board has
no way to tell. A fingerprint check turns that into a refusal with a message.

**To rebuild the images from source** (this needs the full toolchain of §2):

```powershell
python firmware/tools/make_prebuilt.py
```

which compiles all three, copies the images in, rewrites `SHA256SUMS` and regenerates
`BUILD_INFO.json`. **Never hand-edit either file.**

## 8. Verify the chain, stage by stage

Do these in order. Each one isolates a different layer, so a failure tells you where to look.

### 8.1 The hub's own boot self-check

```bash
python firmware/tools/flash_hub.py --port COM32 --log-only --seconds 30
```

The hub runs its **probe** before anything else. It computes log-Mel features on known probe
audio and compares them with references generated by the **notebook's own** front end
(`gen_probe_refs.py`), and it checks the PCM CRC.

**Expected:**

```
RESULT: PASS — 4 probes, 5184/5184 features exact on every probe
```

plus `front end 48.2 ms, inference 103.5 ms` and a clean radio counter line.

**If the probes fail, nothing else starts.** The hub deliberately refuses to bring up the radio,
Bluetooth or the display if the probes fail — a wrong answer is worse than no answer. The two
static-assert failures you will meet here are described in §12.

### 8.2 The node's audio path

```bash
python firmware/tools/verify_burst.py --port COM30 --out research/out/node_window.wav
```

This asks the node to dump its frozen window over its serial console in exactly the radio's
framing, checks every fragment's CRC-16 and the whole window's CRC-32 with `zlib.crc32` on the
host, and reports the mean, the RMS and the peak.

**What the numbers tell you:** the INMP441's DC offset is around **+18,000 counts**, so the mean
should be near zero *after* the front end removes it, the RMS should be small (0.002–0.016 in a
room), and the peak tells you whether the microphone is clipping (the refusal threshold is
31,000 of 32,767).

### 8.3 The radio burst

```bash
python firmware/tools/measure_burst.py --port COM32 --seconds 45 --sound-seconds 14
```

Play something loud during the `--sound-seconds` window. **Expected: 286/286 fragments, CRC-32
MATCH, burst duration 2.06–2.11 s** with the current airtime fixes (it was 5.54–6.93 s before
them).

### 8.4 The end-to-end verdict and the BLE alert

```bash
python firmware/tools/listen_hub.py --port COM32 --seconds 90     # the hub's log
python firmware/tools/listen_node.py --port COM30 --seconds 90    # the node's log, alongside it
python firmware/tools/ble_alert_test.py --listen --seconds 90    # the BLE client
```

Play a cry clip from a phone at **15 cm** from the microphone. **Expected on the hub's log:**

```
node 1: front end 48.2 ms, inference 103.5 ms, P(no_cry)=0.0039 P(cry)=0.9961
node 1: ALERT — cry
```

and on the BLE client:

```
ALERT {'cot': 1, 'alert': 'cry', 'confidence_pct': 100}
```

**That second line, on the node you played at, is the pass condition.**

### 8.5 The full demonstration

`DEMO_RUNBOOK.md` is the procedure, and [Chapter 15](#chapter-15) explains it in full:
the phone 15 cm from the mic, **one** play, let the whole 5-second clip run out, wait 5 s, read
the log, wait 10 s so the 8-second hold clears before the next cot. After the last cot, wait 10
seconds of quiet and check that **nothing announces**.

---

## 9. Reproduce the host-side checks

These need no hardware and are the fastest way to convince a sceptic.

```bash
cd research

python make_stub.py && bash run_stub.sh        # synthetic end-to-end smoke test, minutes
bash run_real_fast.sh                          # the real corpus, subsampled, on CPU
pip install ziglang && python test_c_parity.py # C front end vs Python on the same PCM
python verify_int8_parity.py                   # INT8 vs float32
python eval_indomain.py                        # the deployed model on this room's audio
python eval_esc50.py                           # ESC-50: 40 crying_baby + 1,439 non-cry
python eval_music.py                           # GTZAN, ten genres
python eval_speech.py                          # speech negatives
```

**Expected, with the deployed model:**

| Check | Result |
|---|---|
| C vs Python front end | max deviation **6.9 × 10⁻⁵** |
| INT8 vs float32 | ΔAUC **−0.00137**, decision agreement **99.956 %** over 11,386 windows |
| ESC-50 `crying_baby` recall | **36 / 40** |
| ESC-50 non-cry false alarms | **17 / 1,439 = 1.18 %** |
| GTZAN music false alarms | **2 / 965 = 0.21 %** |
| Quiet room | **0 / 236 windows** |

### The trigger study and the gate analysis

```bash
python adaptive_trigger_study.py     # this is what chose 3.0 as the trigger multiple
python analyze_gates.py              # what each gate in the announcement rule rejects
python simulate_freeze.py            # the stop-capped freeze rule against the peak-centred one
```

### The confusion session — the in-room measurement

The full procedure is `research/CONFUSION_SESSION.md`. In outline:

```bash
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session9 --seconds 60
python firmware/tools/label_session.py --session research/in_domain/session9 --truth cry
```

Nine one-minute takes (quiet room; speech at desk distance and at 30 cm; music at 1 m and at
30 cm; film at 1 m and at 30 cm; the phone-played cry at 15 cm and at 1 m), labelled with the
session's **ground truth** rather than by loudness.

> **`--truth` is not optional.** The old auto-label called a clip a cry if it was *loud*, which for
> the music and film takes would have labelled the loudest non-cry clips as cries — and the
> evaluation would have been circular.

**Expected: 0 false alarms in 308 windows of non-cry audio; 86.4 % per-window recall on the cry at
15 cm; and 0 of 590 records crossing the trigger on the cry at 1 m.**

### The demo kit

```bash
python build_demo_kit.py
python screen_clips.py
python score_demo_clips.py
```

**Expected: 27 of 37 clips announce under the rule; 17 clip if turned up; the freeze lands
2.0–5.4 s after the clip starts, median 2.9 s.**

### The host-side graphics regression

```bash
python check_corners.py        # the panel's four rounded corners must be exact mirror images
python build_font.py           # regenerates the panel's font table
```

---

## 10. Reproduce the hardware documents

```bash
cd tools/wiring
python build.py
```

This regenerates `SYSTEM_WIRING_DIAGRAMS.pdf` — the hub, node, wearable and overview pages, plus
the LX-LCBST pad map (电池 / 输出 / 输入). The pages are generated from the same data as
`SYSTEM_WIRING.md` and `HARDWARE_COMPONENTS.md`, so a change to the wiring is a change to the
generator, not to the PDF.

---

## 11. Reproduce the *training* — the optional path

This is the only part that needs a GPU and the corpora. It is **not** needed to build or flash the
system; it is needed to produce a *different* model.

### 11.1 Regenerate the notebook

The notebook is a **build artefact** and is never hand-edited (D-50):

```bash
cd research && python build_notebook.py
```

This emits `notebooks/crynet_training.ipynb` cell by cell (2,293 lines of generator) and validates
it with `nbformat.validate()`. The reasoning lives inside the notebook as markdown cells, so a
person running it reads the *why* next to the code.

### 11.2 Run it on Kaggle

1. New notebook → *Add Input* → attach nothing (everything downloads).
2. Accelerator **GPU T4**, Internet **On**.
3. Upload `notebooks/crynet_training.ipynb` → *Run All*.

Expected: ~10 min download (4.6 GB, resumable via `huggingface_hub`) + ~5 min feature extraction +
~20–40 min training for the variants + mining + INT8 export. Artifacts land in
`/kaggle/working/out/`.

### 11.3 Or run it locally

```bash
pip install numpy librosa soundfile soxr scipy scikit-learn tensorflow huggingface_hub
CRYNET_FAST=1 python research/run_notebook_local.py     # smoke test, minutes
```

| Environment variable | Effect |
|---|---|
| `CRYNET_FAST=1` | subsample the corpora and train 3 epochs |
| `CRYNET_OFFLINE=1` | never download; require the archives to be in the cache |
| `CRYNET_KINDS` | which variants to train (`conv_cnn,sep_cnn,temporal_cnn`) |
| `CRYNET_EPOCHS` | training epochs (default 35) |
| `CRYNET_MINING_ROUNDS` | hard-example mining rounds (default 1; 0 disables) |
| `CRYNET_CACHE` / `CRYNET_WORK` / `CRYNET_OUT` | cache, scratch and output directories |

Caches: the HF archives at `research/_cache/audio/positive.zip`,
`research/_cache/audio/negative.zip`, `research/_cache/metadata/all28479.csv`; the Kaggle archives
at `research/_cache/<key>__<owner>__<slug>.zip`.

> **`research/_cache/speech__fsd50k_speech.zip` must not be deleted.** Its GitHub release has no
> asset on it, so it cannot be re-fetched.

### 11.4 Stage the new artifacts — in this order

1. Drop the notebook's `out/` into `research/out/`.
2. **Back up the old model**: `research/out/deployed_model_backup/`.
3. `python firmware/tools/check_artifact_drift.py` → it will now FAIL, because the staged copies in
   `firmware/hub_infer/components/` are the old ones. That is the check working.
4. Copy the new `crynet_tables.h`, `model_data.h` and `deploy_config.json` into
   `firmware/hub_infer/components/crynet_model/include/`, and the new `dsp_crynet.c` / `.h` into
   `firmware/hub_infer/components/crynet_dsp/reference/`.
5. `python firmware/tools/check_artifact_drift.py` → **PASS**.
6. `python firmware/tools/gen_probe_refs.py` → regenerate `crynet_probe_refs.h` by running the
   **notebook's own** log-Mel front end, extracted from the notebook. The on-device probes then
   compare against the training pipeline itself, not against a reimplementation of it.
7. Rebuild, flash, and re-run the evaluations **before** believing the new model:
   `eval_esc50.py`, `eval_music.py`, `eval_indomain.py`, `verify_int8_parity.py`,
   `test_c_parity.py`.
8. Only then flash the board and check the boot probe.

That is exactly the order D-58 followed, and the reason the music fix could be defended with
numbers instead of hope.

---

## 12. The traps, and what each one looks like

| Symptom | Cause | Fix |
|---|---|---|
| `include could not find requested file: .../tools/cmake/project.cmake` | PlatformIO installed the framework as an **npm package** (D-45, I-6) | Install ESP-IDF 6.1.0 by hand and write `.piopm` — §2.2 |
| `Multiple ways to build the same target were specified for …/circular_buffer.cc.o` | PlatformIO's SCons object naming collides on basenames (D-46) | The components must live **inside** `firmware/hub_infer/components/` — §3 |
| The chip watchdog-resets in a loop: `rst:0x7 TG0WDT_SYS_RST`, no output | A **QIO** image on this board (D-47) | The effective mode is **DIO**; `--merged` passes `--flash-mode dio` |
| The build succeeds but the boot probe fails: `max delta 87, 0/5184 exact -> FAIL` | The weights moved but the front end did not (I-41) | The static asserts in `crynet_dsp.c` are the drift guards; fix the constants or regenerate the probe references |
| The radio is silent: 0 frames for two minutes | The node was flashed at the wrong port and is parked in **download mode** (I-40) | `python firmware/tools/who_is_who.py` before flashing anything |
| The serial console never appears | **USB CDC on boot** is off in the board options | Enable it, or the sketch's logs go nowhere |
| The node's trigger stops working after an edit | The Arduino TX timeout (I-11) | Keep `Serial.setTxTimeoutMs(0)` |
| A stale model compiles into the firmware | The notebook re-derives the threshold and the scales every run | `check_artifact_drift.py` **before** the build — §4 |
| The panel shows static / is rotated / has red and blue swapped / has hearts for letters | I-30, I-31, I-35, I-33 | Chapter 13, rounds 1–4 |
| The rounded corners are wrong | I-39 | `python check_corners.py` |
| The hub asks for audio 5–11 times a minute in a quiet room | The adaptive trigger's 3× floor (D-63) | Expected; the hub then answers "no cry" on every window. Measured: **32 verdicts, 0 false alerts** |

---

## 13. The time and disk budget

| Stage | Wall time | Notes |
|---|---|---|
| PlatformIO's first-time downloads | 15–40 min | once, ~2 GB |
| Hub build (incremental) | ~1 min | ~4 min from clean |
| Node / wearable build | ~1 min each | Arduino CLI |
| Flash + boot log | ~1 min | |
| Host-side checks (§9) | 10–30 min | `run_real_fast.sh` is the slow one |
| The full Kaggle training run | 45–90 min | GPU; optional |
| The confusion session | ~30 min | nine takes plus the labelling |
| **This dossier** | ~1 min | `python docs/dossier/build.py` |

Disk: the toolchain is ~2 GB, the corpora are 4.6 GB (cacheable), the repository with its tracked
`research/out/` is well under 500 MB.

---

## 14. The checklist

Print this. Tick it. You have reproduced the project.

- [ ] `git clone` → the artifacts are in `research/out/`
- [ ] PlatformIO 6.2.0 installed, ESP-IDF 6.1.0 installed **by hand**, `.piopm` written
- [ ] `bash firmware/tools/fetch_deps.sh` → two trees at two pinned revisions
- [ ] `python firmware/tools/check_artifact_drift.py` → **PASS**
- [ ] `python firmware/tools/check_prebuilt.py` → the offline images are **up to date with the source**
- [ ] `python -m platformio run` → the hub builds
- [ ] `arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 …` → the node and the wearable build
- [ ] The hub flashes, boots, and prints `RESULT: PASS — 4 probes, 5184/5184 features exact`
- [ ] Each cot's id is set (`id 1`, `id 2`) and **still set after the flash**
- [ ] The hub's console shows `node 1 heard for the first time` and `node 2 heard for the first time`
- [ ] `verify_burst.py` → the node's window, CRC-32 MATCH
- [ ] `measure_burst.py` → 286/286 fragments, 2.06–2.11 s
- [ ] `listen_hub.py` + `ble_alert_test.py` → `P(cry)=0.9961` and `ALERT — cry` on the right cot
- [ ] `test_c_parity.py` → max deviation 6.9 × 10⁻⁵
- [ ] `verify_int8_parity.py` → ΔAUC −0.00137, agreement 99.956 %
- [ ] `eval_music.py` → 2 / 965 = 0.21 %; `eval_esc50.py` → 36 / 40 and 17 / 1,439
- [ ] The confusion session → 0 false alarms in 308 non-cry windows, 86.4 % recall at 15 cm
- [ ] Both cots hear one clip → the hub's mask reaches **`0x03`** and the wrist reads **`COTS 1 2`** (D-86)
- [ ] Five cry episodes → **five** buzzes, with handovers silent
- [ ] The phone is far enough back that no window's peak reaches **31000** — check peak, not RMS
- [ ] `python docs/dossier/build.py` → this document, in PDF
