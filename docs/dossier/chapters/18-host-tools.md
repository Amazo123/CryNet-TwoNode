# Chapter 18 — The host tools: twenty-nine programs that made the firmware debuggable

## Why this chapter exists

None of these tools ships in the product. All of them are why the product works. A microcontroller
system with no host-side instrumentation is a system whose faults can only be guessed at, and almost
every diagnosis in this dossier was made by a tool in this list.

They live in `firmware/tools/` (**29 Python programs**, plus `fetch_deps.sh`, the PowerShell helpers
and `flash.bat`) and `research/` (the evaluation and analysis scripts). Every one is reproduced in
full in Appendix B.

## Flashing and installation

| Tool | What it does |
|---|---|
| **`flash_hub.py`** | Flashes the ESP32-S3 and prints its boot log. `--merged` combines bootloader (0x0), partition table (0x8000) and application (0x10000) into one file **with `--flash-mode dio`**, which is what a graphical flasher expects. `--flash-only`, `--log-only --seconds N`, `--port COM32`. Everything it needs is already on the machine — nothing to download. |
| **`flash_node.py`** | Builds the node sketch and flashes it over USB with `arduino-cli`. `--sketch` also selects `wearable` or `haptic_test`, so the motor's bench proof is one command. |
| **`flash_unit.py`** | **The offline path.** Flashes any of the three roles from `firmware/prebuilt/` using `esptool` alone — no Arduino core, no PlatformIO, no compiler, no network. Writes region by region and **never writes NVS**, so a cot keeps its id. `--check` verifies every image against `SHA256SUMS`; `--list`, `--backup`, `--log N`. |
| **`make_prebuilt.py`** | Compiles all three units from source, copies the images into `firmware/prebuilt/`, rewrites `SHA256SUMS` and writes `BUILD_INFO.json` — the SHA-256 of **every source file** that went into each image. |
| **`check_prebuilt.py`** | Recomputes those source fingerprints and compares. **This is the check that refuses to let a stale image be flashed**: an edited sketch with old `.bin` files is caught before anyone writes it to a board. |
| **`prebuilt_lib.py`** | The shared fingerprinting and manifest logic behind the two above, so the builder and the checker cannot disagree about what counts as a source file. |
| **`serial_monitor.py`** | A plain serial reader for when no parser is wanted — the raw log, nothing interpreted. |
| **`install_sketches.py`** | Copies the sketches into the Arduino sketchbook, because the IDE builds a sketch from its own folder while the sources live in the repo. |
| **`who_is_who.py`** | Says which node is on which port. Node id lives in **NVS**, so it survives a reflash — but only if the flash tool does not erase that partition. This script resolves the ambiguity instead of leaving it to guesswork. |
| **`patch_deps.py`** | Makes the vendored TFLite Micro port build against the vendored `esp-nn`, overriding the port's `idf_component.yml` declaration. Keeps the build offline and pinned. |
| **`fetch_deps.sh`** | Re-fetches exactly the pinned dependencies. |

## Listening and capture

| Tool | What it does |
|---|---|
| **`listen_hub.py`** | Reads the hub's log and prints the chain. **It plays nothing** — it is a passive observer, so a sound can be made by any means and the hub's reaction recorded. |
| **`listen_node.py`** | Reads the node's log: the noise floor, the trigger level, and *why* it froze each window. Since D-63 the node owns the trigger, so this log is the only place that question can be answered. |
| **`capture_serial.py`** | Reads the hub's serial log, optionally resetting the board first. |
| **`capture_multi.py`** | Watches **several boards at once** with timestamps. The bench has the hub, both cots and the wearable on one machine, so the questions that matter need every board's log aligned in time. This is what made the two-board latency measurements possible — and what settled the resend-bitmap question by putting both ends of one exchange in one file. |
| **`capture_hub_wait.py`** | Waits for a specific event and writes `research/out/hub_node1_fullchain.log` with `[t]` timestamped lines. Exit 0 on capture, 1 on timeout — so it can be used in a script. |
| **`node_console.py`** | Sends one-line commands to the node's console at 115200 and prints its state. |

Every one of these implements D-49: **resynchronise on the stream's own magic, never wait for a fixed
block, and drop any record whose CRC-16 fails.** A USB CDC port can enumerate after the sketch has
already printed its banner, and one dropped byte would otherwise shift every later sample.

## Audio collection and labelling

| Tool | What it does |
|---|---|
| **`collect_clips.py`** | Records in-domain audio from the node over USB and cuts it into fixed-length clips. The deployed model was trained on corpora this room's microphone has never produced; this is how that gap is closed. |
| **`label_session.py`** | Turns a captured session into **labelled** 5-second clips. A fixed cut is not a label — `--truth` applies the session's ground truth, so a loud non-cry take is labelled non-cry rather than being labelled by its loudness. Without this the evaluation would be circular. |
| **`dump_node_window.py`** | Dumps the node's frozen window over its serial console using the node's `burst` command, which writes it in exactly the radio's framing. This is how the *exact bytes the node holds* are compared with what the hub reassembled. |

## Measurement and verification

| Tool | What it does |
|---|---|
| **`measure_burst.py`** | Measures the hub's burst time on the real boards. This is the tool that produced the 5.54–6.93 s → 2.06–2.11 s comparison. |
| **`measure_latency.py`** | Measures end-to-end latency and whether the hub calls the cry, from the log. |
| **`verify_burst.py`** | Checks the node's audio path end to end: dumps the frozen window and verifies every fragment CRC-16 and the whole-window CRC-32, using `zlib.crc32` on the host. Can write the window as a WAV. |
| **`check_artifact_drift.py`** | Verifies that `research/out/`, `deploy_config.json` and the staged firmware copies all describe the same model bytes. Run after dropping new Kaggle outputs in and **before** building. Currently **PASS**. |
| **`gen_probe_refs.py`** | Regenerates `crynet_probe_refs.h` by running the **notebook's own** log-Mel front end, extracted from the notebook. The on-device probes therefore compare against the training pipeline itself, not against a reimplementation of it. |

## The record and the dashboard

| Tool | What it does |
|---|---|
| **`hub_console.py`** | A serial console session for the hub's own word list (`status`, `history`, `log`, `net`, `logtest`…) — the network and record configuration of Chapter 12, driven from a PC instead of a bare UART. |
| **`test_log_order.py`** | The host model of the uploader's ordering rule: the lowest unsent numbers, the clamped watermark, and a companion test that shows the *old* algorithm losing records so the guard cannot silently stop guarding. |
| **`test_dashboard_contract.py`** | Builds the hub's upload and presence bodies **byte for byte** and proves a running dashboard round-trips them — idempotence, the untimed-record rule, presence freshness. The one contract in the system no compiler checks (Chapter 12). |

## BLE

| Tool | What it does |
|---|---|
| **`ble_alert_test.py`** | A PC BLE client for the hub's GATT server. Subscribes to both characteristics and prints every packet — this produced the `ALERT {'cot': 1, ...}` lines quoted throughout the dossier. |
| **`serve_alert_page.py`** | Serves the alert page over **HTTPS**, because Web Bluetooth only works in a secure context and on a phone that means HTTPS. Lets a phone be the caregiver's device without the wearable. |

## The research scripts

| Script | What it does |
|---|---|
| **`build_notebook.py`** | Generates the training notebook (2,293 lines). The notebook is never hand-edited (D-50). |
| **`make_stub.py` / `run_stub.sh`** | A synthetic corpus and a FAST-mode run: validates the whole pipeline end to end in minutes without downloading 4.6 GB. This is how the music corpus was validated before the Kaggle run. |
| **`run_real_fast.sh`** | The real corpus, subsampled, on CPU. |
| **`test_c_parity.py`** | Compiles the C front end on the host (with `ziglang` as the compiler) and compares it with Python on the same PCM. A divergence can be debugged on a workstation rather than on a board. |
| **`verify_int8_parity.py`** | INT8 against float32 on the host. |
| **`eval_indomain.py`** | The deployed model on this room's audio. |
| **`eval_esc50.py`** | ESC-50: the 40 `crying_baby` clips and the 1,439 non-cry clips. |
| **`eval_music.py`** | GTZAN, ten genres — the script that found the 8.19 % music failure. |
| **`eval_speech.py`** | Speech negatives. |
| **`adaptive_trigger_study.py`** | Sweeps trigger multiples over the recorded sessions. **This is what chose 3.0**, not taste. |
| **`analyze_gates.py`** | What each gate in the announcement rule rejects, and what it costs. |
| **`simulate_freeze.py`** | Replays the freeze rule against the corpus: the stop-capped rule catches as many episodes as the peak-centred rule. |
| **`analyze_window.py`** | Says what is in a window and what the model makes of it. |
| **`screen_clips.py` / `score_demo_clips.py` / `build_demo_kit.py`** | Build and score the demonstration kit — every clip scored, failures listed alongside successes. |
| **`check_corners.py`** | Host-side graphics regression: the panel's four rounded corners must be exact mirror images. |
| **`test_heartbeat_framing.py`** | Compiles the real `crynet_proto.c` with `ziglang` and holds the two-cot protocol rules: a heartbeat is exactly **12 bytes** and round-trips as type 4, the other frame types are unchanged, and the id rule hears 1 and 2 while ignoring 0, 3 and 255. **Checked against the bug it was written for** — reverting the framing fix makes it fail. |
| **`ui_mock.py`** | Renders the panel to a PNG on the host, so a layout can be judged before it is flashed. The two-card redesign was rendered this way first (`research/out/two_node_display_mock.png`). |
| **`simulate_demo.py`** | Replays the demo kit against the announcement rule without any hardware. |
| **`build_font.py`** | Generates the panel's font table (and once had the 32-character offset bug). |
| **`rssi_walk_test.py`, `analyze_starvation.py`, `cry_audio_check.py`, `measure_photo.py`, `compare_photo.py`** | The specialist instruments: radio range walks, queue starvation analysis, corpus audio sanity (this is the class of check that found the contaminated "silence" class), and panel photograph measurement. |

## The offline images, and the check that guards them

`firmware/prebuilt/` holds the built firmware for all three roles, so a board can be brought up on a
laptop that has never seen this project. It needs exactly one executable: `esptool`.

| Folder | Chip | Files and offsets |
|---|---|---|
| `hub/` | ESP32-S3 | `bootloader.bin` 0x0, `partitions.bin` 0x8000, `firmware.bin` 0x10000 |
| `node/` | ESP32-C3 | `bootloader.bin` 0x0, `partitions.bin` 0x8000, `boot_app0.bin` 0xe000, `app.bin` 0x10000 |
| `wearable/` | ESP32-C3 | the same four |

**Two rules are load-bearing, and both are easy to get wrong:**

1. **Write the regions, not one merged file.** A merged image fills the gaps between regions with
   `0xFF`, and writing that would **erase NVS** — which is where a cot keeps its id. The offsets above
   skip NVS on purpose (0x9000–0xE000 on the C3 boards, 0x9000–0xF000 on the hub). A merged flash
   would silently turn a working cot into an invisible one, because its id would be gone.
2. **The hub images are DIO.** A QIO image makes the S3 watchdog-reset in a loop right after power-on
   (D-47). The bootloader header in `hub/bootloader.bin` says DIO.

`BUILD_INFO.json` is the interesting part. It records, per role, the SHA-256 of **every source file**
that went into that image — 52 files for the hub, one for each sketch — with an explicit rule set for
what does *not* count (build directories, `sdkconfig*`, the vendored third-party trees, editor
artefacts). `check_prebuilt.py` recomputes those fingerprints and compares.

**Verified at the time of writing:**

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

The reason this is worth the machinery: the failure it prevents is *silent*. A stale image flashes
successfully, boots, and behaves like the old firmware, and the person holding the board has no way to
tell. A fingerprint check turns that into a refusal with a message.

## The pattern worth defending

Three properties recur across all of these, and they are the reason the project's numbers can be
trusted:

1. **Passive observation before intervention.** `listen_hub.py` plays nothing. The measurement is
   separated from the stimulus, so a result cannot be an artefact of the tool.
2. **Host-side reimplementation of the check, not of the thing being checked.** `verify_burst.py`
   uses `zlib.crc32`; `gen_probe_refs.py` uses the notebook's own front end. The reference is
   independent of the implementation under test.
3. **Every parser is a testable class checked against synthetic streams.** A parser tested only
   against a live device is tested only on the happy path.