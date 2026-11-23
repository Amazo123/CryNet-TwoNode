# Chapter 16 — Toolchain: what was installed, what broke, and why it is pinned

## The starting point

The machine had **no ESP-IDF, no PlatformIO, no Arduino IDE and no Xtensa compiler**. Everything the
build needs is now reproducible **from the repository** rather than from the state of one machine
(D-48). That is the standard the toolchain work was held to, and it is why `dependencies.lock`,
`fetch_deps.sh` and `patch_deps.py` are tracked.

## The versions that are known to work

| Layer | Version |
|---|---|
| Python | **3.11.9** |
| TensorFlow (CPU) | **2.21.0** |
| librosa | **0.11.0** |
| soundfile | **0.14.0** |
| numpy | **2.4.6** |
| scipy | **1.17.1** |
| ziglang (used as the host C compiler for the parity test) | **21.1.0** |
| PlatformIO | **6.2.0** |
| platform-espressif32 | **8.0.0** |
| ESP-IDF | **6.1.0** (bundled as `framework-espidf 4.60100.0`) |
| Arduino ESP32 core | **3.3.12** |
| Node/wearable FQBN | `esp32:esp32:weact_studio_esp32c3` |

## D-45 — why ESP-IDF is installed by hand

PlatformIO 6.2 installs a **URL-specified** `platform_packages` entry by treating the archive as an
**npm package**. It picks the wrong `package.json` out of the tree, writes a bogus version into
`.piopm`, and leaves `packages/framework-espidf` holding only a **test-fixture package**. CMake then
fails with:

```
include could not find requested file: .../tools/cmake/project.cmake
```

That is I-6, and it cost real time. IDF 5.3.2 could not be installed through PlatformIO at all; 6.1.0
was already on disk and satisfies the TFLM port's `idf >= 5.1`.

**The fix is to install the framework manually and pin it with `packages/framework-espidf/.piopm`,
and never to put a `platform_packages` URL in `platformio.ini`.** The ini carries a comment saying
exactly that, so the next person does not repeat it.

## D-46 — why TFLM is vendored inside the project

PlatformIO re-compiles IDF components with SCons using the **source basename** for object names. The
TFLM port has **twelve basename collisions**, so the build died with:

```
Multiple ways to build the same target
```

Moving the vendored components **inside** `firmware/hub_infer/components/` makes the paths relative
and distinct. `esp-nn` is wired as the port's own dependency with the registry copy removed, and
`board_build.esp-idf.overwrite_managed_components = no` stops PlatformIO wiping `managed_components`
on every configure.

`firmware/tools/patch_deps.py` keeps the build **offline and pinned**; `fetch_deps.sh` re-fetches
exactly what was fetched.

This is the general lesson: a build that downloads a moving dependency is not a build that can be
reproduced in a year, and vendoring is not untidiness — it is the reproducibility mechanism.

## D-47 — DIO flash mode

The effective configuration is `CONFIG_ESPTOOLPY_FLASHMODE="dio"`, and both `bootloader.bin` and
`firmware.bin` carry flash-mode byte **`0x02`**.

A combined image built with QIO makes the chip **watchdog-reset in a loop** —
`rst:0x7 TG0WDT_SYS_RST` repeating, with no application output at all. The ROM cannot read this
board's flash in QIO before the bootloader has configured its own timing. **The bootloader switches
the chip to QIO by itself once it is running**, so DIO costs nothing at this workload.

`flash_hub.py --merged` passes `--flash-mode dio` explicitly when combining the three images at
`0x0` (bootloader), `0x8000` (partition table) and `0x10000` (application).

Note the trap: `sdkconfig.esp32s3` still shows `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y` as the *choice
symbol*, while the *string* that esptool acts on says `dio`. Reading only the choice symbol gives the
wrong answer.

## D-48 — the Arduino side

The node and wearable sketches are compiled with the **Arduino IDE's own `arduino-cli`** against core
**3.3.12**, FQBN `esp32:esp32:weact_studio_esp32c3` — the WeAct Studio ESP32-C3 definition, which selects
the **chip** and its flash/USB settings rather than one physical module,
which is the exact module on the bench. **USB CDC on boot** must be enabled, or the serial console
does not appear.

`firmware/tools/install_sketches.py` places the sketches where the CLI expects them;
`flash_node.py` is the one-command flasher.

### The fourth toolchain: none at all

The three units above need a compiler. The **offline path** needs none: `firmware/prebuilt/` holds
the built images, and `flash_unit.py` writes them with `esptool` alone. That is a deliberate fourth
option, not a convenience — it exists so a board can be brought up on a machine that has never seen
this project, with no Arduino core, no PlatformIO, no ESP-IDF and no network.

What stops it going stale is `BUILD_INFO.json`, which records the SHA-256 of every source file that
went into each image, and `check_prebuilt.py`, which recomputes them. Chapter 17 has the details;
Chapter 19 has the commands.

Two firmwares, two toolchains — ESP-IDF for the hub (because NimBLE, coexistence and PSRAM need
`sdkconfig`) and Arduino for the two C3 units (because they are simple and the core is already
proven). That split is deliberate, not accidental.

## D-49 — every serial tool resynchronises on its own magic

A USB CDC port can enumerate **after** the sketch has already printed its banner. And a single dropped
byte on the USB link would otherwise **shift every later sample and quietly ruin the dataset**.

So every host tool that reads a serial stream:

- **resynchronises on its own magic** rather than waiting for a fixed block;
- treats capture records as CRC-16-protected, and **drops any record that fails**;
- is written as a **testable parser class**, checked against synthetic streams.

That last point is the one that makes it trustworthy: a stream parser tested only against a live
device is a parser tested only on the happy path.

## D-50 — the notebook is a build artefact

`notebooks/crynet_training.ipynb` is **generated** from `research/build_notebook.py` and **never
hand-edited**. Editing it directly makes it impossible to regenerate and to diff. It is validated
with `nbformat.validate()` after every regeneration.

```bash
cd research && python build_notebook.py
```

The generator is 2,293 lines and emits the notebook cell by cell, with the reasoning as markdown
cells inside the notebook itself — so a person running it on Kaggle reads the *why* next to the code,
not in a separate document.

## The build commands

```bash
# hub — about a minute incremental
cd firmware/hub_infer && python -m platformio run

# node
arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/node/node_crynet

# wearable
arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/wearable/wearable_crynet

# re-fetch the pinned dependencies
bash firmware/tools/fetch_deps.sh
```

## Where the evidence lives

Every run's log is under **`research/toolchain/`** and every run's conclusion is in
**`SYSTEM_UPDATE.md`'s change log**. That pairing — raw log plus a written conclusion — is what makes
the project's claims checkable rather than remembered.