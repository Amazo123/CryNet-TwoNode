# Flashing the CryNet units — offline, step by step

**Written 2026-11-07, against the D-83 firmware (no battery sense, no status LEDs).**

This guide is written so that **you can put the firmware on any unit yourself** —
a new hub, a spare cot node, a replacement wearable — without asking anyone and
without needing the internet.

Read it with `SYSTEM_WIRING.md` (what to wire) and `SYSTEM_UPDATE.md` (what has happened).

---

> **Have never flashed a chip before? Start with `GETTING_STARTED_FLASHING.md` instead.**
> It is written for someone who has never opened PlatformIO or the Arduino IDE:
> where every file is, what a COM port is, and three ways to do the job —
> double-click a `.bat`, use PlatformIO IDE, or use the Arduino IDE.
>
> This file is the **reference**: every option, every escape hatch, the reasoning.
> The other one is the **walkthrough**.

---

## 0. What you need

**One program: `esptool`.** That is the whole offline path. It is already on this
machine:

```
%USERPROFILE%\.platformio\packages\tool-esptool\esptool.exe
```

`esptool` writes a firmware image to a board over USB. It does not compile
anything, so it does not need the Arduino core, PlatformIO, a compiler or a
network connection.

On a **new** machine, get it one of these ways:

| Where | How |
|---|---|
| Copy the folder | copy `%USERPROFILE%\.platformio\packages\tool-esptool\` to the new machine and put it somewhere on the PATH |
| pip | `pip install esptool` — this gives `esptool` as a command |
| Arduino IDE | the IDE ships one too, under `resources\app\lib\backend\resources\` |

The helper scripts in this guide are Python and need `pyserial` (`pip install pyserial`).
They are a convenience, not a requirement: `esptool` on its own can do every step.

---

## 1. Get the code and the firmware images

The repository holds the firmware **source** *and* the **built flash images**, so
you do not have to compile anything to flash a unit.

```powershell
git clone https://github.com/Amazo123/CryNet-TwoNode.git
cd CryNet-TwoNode
```

No network? Copy the folder across on a USB stick — it works just as well. The
images you need are in `firmware/prebuilt/`:

```
firmware/prebuilt/
├── README.md          what is in here and the two rules that matter
├── SHA256SUMS         the hash of every image, so you can prove it is intact
├── BUILD_INFO.json    which source each image was built from, so you can
│                      prove it is up to date
├── hub/                bootloader.bin  partitions.bin  firmware.bin
├── node/               bootloader.bin  partitions.bin  boot_app0.bin  app.bin
└── wearable/           bootloader.bin  partitions.bin  boot_app0.bin  app.bin
```

If the copy you have predates these images, pull the branch that carries them:

```powershell
git fetch origin
git checkout feature/offline-flashing
```

If you are working on the units that are on the bench, the checkout that already
exists is `C:\Users\HP\.t3\projects\fp-two-node`. Use that one.

---

## 2. Check the tools and the images before you touch a board

```powershell
python firmware/tools/flash_unit.py --check
```

It prints something like this:

```
== toolchain ==
  esptool     OK   C:\Users\HP\.platformio\packages\tool-esptool\esptool.exe
  pyserial    OK

== prebuilt images ==
  hub:
    0x000000  bootloader.bin       22560 B  aefe21ad9f40735b...  hash OK
    0x008000  partitions.bin        3072 B  463793a642ab4a90...  hash OK
    0x010000  firmware.bin      1335248 B  f7f09a34a7d115cd...  hash OK
  node:
    0x000000  bootloader.bin       19536 B  9b2fa5e4af7cf282...  hash OK
    0x008000  partitions.bin        3072 B  148b959cbff1c38a...  hash OK
    0x00e000  boot_app0.bin         8192 B  f94c5d786a7a8fab...  hash OK
    0x010000  app.bin             983328 B  aabb406f49335423...  hash OK
  wearable:
    ...
```

**If a line says `HASH MISMATCH`, stop** — the image is damaged (a truncated
download, a disk problem). Re-copy the folder; do not flash it.

`--check` flashes nothing. It only reads.

---

## 3. Work out which board is which, **before** you flash anything

This is the step that saves the most grief, because **a COM port number is not an
identity.** Windows assigns COM numbers from the USB path and the enumeration
order, so the same physical board gets a different number when you move it to
another socket or replug it. What identifies a board for good is its **MAC
address**, which is burned into the chip.

The map as it stood on 2026-11-07, when the units were last on the bench:

| Board | MAC | Port that day | How it appears on USB |
|---|---|---|---|
| **Hub** (ESP32-S3 DevKitC) | — | COM32 | `USB-Enhanced-SERIAL CH343` — a USB-serial bridge |
| **Cot node 1** | `90:DA:72:85:C5:44` | COM31 | `USB Serial Device` (Espressif native USB) |
| **Cot node 2** | `90:DA:72:87:CB:98` | COM37 | `USB Serial Device` (Espressif native USB) |
| **Wearable** | — | COM30 | `USB Serial Device` (Espressif native USB) |

**Treat that table as a memory aid, not as a script.** The numbers will move.

### 3a. List what is on USB

```powershell
python firmware/tools/flash_unit.py --list
```

or, without Python:

```powershell
Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.Name -match 'COM\d+' -and $_.Name -notmatch 'Bluetooth' } |
  ForEach-Object { "$($_.DeviceID)  |  $($_.Name)" }
```

Read it like this:

- **`USB-Enhanced-SERIAL CH343 (COM32)`** → the **hub**. The S3 DevKitC has a CH343
  USB-serial bridge on it.
- **`USB Serial Device (COMxx)`** → an Espressif board on its own native USB. That is
  a cot node **or** the wearable; you cannot tell them apart from the USB descriptor
  alone.

### 3b. Ask each board who it is

```powershell
python firmware/tools/who_is_who.py COM30 COM31 COM32 COM37
```

For each port the tool resets the board over RTS/EN and reads the banner it prints
at boot. **It does not flash anything.** A cot node answers with its id and its MAC:

```
CryNet node firmware — Stage 2b
node id 1 (derived from the MAC; change it with "id <n>")
...
node 1  mac 90:DA:72:85:C5:44
```

A node whose id was set by hand says so instead — `node id 2 (saved; the MAC would
have said 7)` — which is how you know the id in NVS is yours and not the derived
one.

The wearable answers with its OLED line and then its Bluetooth lines:

```
[oled] up
[ble] hub found (30:30:F9:17:2F:80)
[ble] connecting to 30:30:F9:17:2F:80
[ble] hub connected
[ble] state: 2 cot(s), mask 0x00
```

If a board prints something else entirely, it is running some other sketch — flash the
right one onto it and move on.

### 3c. If a node is on the wrong id

The id lives in the board's own NVS and **survives a reflash** — the flash in §5
writes the application, not the NVS partition. A board that has never been named
derives its id from its MAC — **the last byte of the MAC, masked and plus one**, so
it can be anything from 1 to 16 — and two identical boards can derive the *same*
number, so the MAC is what settles a doubt.

To rename a node, over its serial console (115200 baud):

```
id 2          <- sets and saves the id
status        <- prints the id, the MAC, the link bar and the window
```

**The two-cot hub watches cots 1 and 2 only.** A node left on id 3 — or on a
MAC-derived id such as 7 — is ignored by it, and says so on its console:
*"WARNING: this hub watches cots 1 and 2 only."*

### 3d. Identifying a board that has never been flashed

A brand-new board is running whatever the factory put on it, so it will not print
a CryNet banner for `who_is_who.py` to read. Read its MAC address directly:

```powershell
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32c3 --port COM31 chip-id
```

That prints the MAC, and it also proves the board answers on that port at all. The
MAC is the identity that never changes, so write it down next to the board.

---

## 4. The order: **hub first, then the nodes, then the wearable**

This is not a preference. The telemetry frame changed in this build:

- the **new** node sends a **32-byte** payload (16 base bytes, then the radio counters);
- the **old** node sent **34 bytes** (the same, plus two bytes of battery voltage in
  the middle).

The **new hub reads both** — it looks at the payload length and picks the right
offsets — so a node that has not been reflashed yet cannot turn the hub's radio
counters to noise. But the **old hub only understands 34 bytes.** So:

> **Flash the hub first.** Then a node never meets a hub that misreads it.

---

## 5. Flash a unit

One command per unit, with **its own port named**. The port is never guessed: a COM
number is not an identity (§3), and the incident recorded as **I-40** in
`DECISIONS.md` — a flash aimed at the wrong port parking a node in its bootloader —
is the reason the scripts refuse to guess.

### The hub (ESP32-S3)

```powershell
python firmware/tools/flash_unit.py --role hub --port COM32 --log 25
```

### A cot node (ESP32-C3)

```powershell
python firmware/tools/flash_unit.py --role node --port COM31 --log 15
python firmware/tools/flash_unit.py --role node --port COM37 --log 15
```

### The wearable (ESP32-C3)

```powershell
python firmware/tools/flash_unit.py --role wearable --port COM30 --log 15
```

`--log 25` reads the boot log for that many seconds after the flash, which is how
you see the good lines in §7. Drop it if you do not want it.

### The same thing, by hand

Every command above is a single `esptool` call. If you would rather run it
yourself — or you are on a machine with no Python — this is exactly what runs:

```powershell
# the hub
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32s3 --port COM32 --baud 921600 write-flash `
    0x0     firmware\prebuilt\hub\bootloader.bin `
    0x8000  firmware\prebuilt\hub\partitions.bin `
    0x10000 firmware\prebuilt\hub\firmware.bin

# a cot node or the wearable
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32c3 --port COM31 --baud 921600 write-flash `
    0x0     firmware\prebuilt\node\bootloader.bin `
    0x8000  firmware\prebuilt\node\partitions.bin `
    0xe000  firmware\prebuilt\node\boot_app0.bin `
    0x10000 firmware\prebuilt\node\app.bin
```

**NVS is never written.** The offsets skip it (it sits at `0x9000`–`0xE000` on the
node, `0x9000`–`0xF000` on the hub), so a node keeps its id across a reflash and the
hub keeps its stored settings.

**Do not use one combined image for the hub.** A combined image has to be written in
DIO mode; the ROM on this board cannot read the flash in QIO before the bootloader
has set up its own timing, and a QIO image makes the chip watchdog-reset in a loop
right after power-on. The three-image write above is the safe one — and the images
in `firmware/prebuilt/hub/` are already DIO (the bootloader header says so).

---

## 6. A brand-new board

Nothing in §5 changes, but two things are worth knowing about a board that has never
been flashed before:

1. **The node id.** A brand-new node has no id in NVS, so it derives one from its
   MAC (the last byte, masked and plus one — 1 to 16). Give it the right one
   straight away, over the serial console at 115200 baud (§3c): `id 1` for the first
   cot, `id 2` for the second. **Two new nodes can derive the same id**, and a
   derived id outside 1–2 is ignored by the hub outright; either way the board
   warns you on its console. Set the ids by hand — do not trust the derived value.

2. **The wearable** needs nothing: it finds the hub by Bluetooth and takes its state
   from it.

3. **The hub** needs nothing either. It comes up, runs its self-check and starts
   listening.

### A board of a *different kind*

The prebuilt images are built for the boards this project uses:

| Unit | Board the image is built for | What that fixes |
|---|---|---|
| hub | ESP32-S3 DevKitC-1 **N16R8** | 16 MB flash, 8 MB octal PSRAM, the 16 MB partition table |
| node | WeAct Studio **ESP32-C3 SuperMini** (`esp32:esp32:weact_studio_esp32c3`) | 4 MB flash, native USB, and the board's own pin map |
| wearable | the same SuperMini | 4 MB flash, native USB, SDA 5 / SCL 6 for the OLED |

The firmware targets the **chip**, not the board, so a different C3 board usually
works — but three things have to line up, and they are easy to get wrong:

- **Flash size.** The image is a 4 MB layout. A board with 2 MB of flash cannot hold
  it; a board with 8 or 16 MB can, but its partition table has to be the one the
  image was built with, so **rebuild it for that board** rather than reusing it.
- **Native USB.** The serial console — the only way to set a node's id — comes over
  the USB port. A board that only has a UART bridge still flashes, but the console
  is then on the UART pins.
- **The microphone pins.** The node sketch hard-codes the INMP441 on **SCK 4, WS 5,
  SD 6**. A board that has those pins used for something else will not hear
  anything.

To build the images for a different board, change the `FQBN` at the top of
`firmware/tools/make_prebuilt.py` and rebuild (§10):

```powershell
python firmware/tools/make_prebuilt.py --role node
```

If the new board is an **ESP32-S3 that is not a DevKitC-1 N16R8** (a different flash
size or a different PSRAM), do not use these images — the hub image is built for
16 MB of flash and 8 MB of octal PSRAM. Check what it is before you flash it.

---

## 7. Verify, unit by unit

| Unit | Check | Where to look |
|---|---|---|
| Hub | `RESULT: PASS — 4 probes` | the boot log |
| Hub | `node 1 is online`, `node 2 is online` | the boot log |
| Hub | **no `bat` field** in the `link:` lines | the boot log |
| Node 1 | `node 1  mac 90:DA:72:85:C5:44`, and **no battery line** in `status` | `who_is_who.py COM31` |
| Node 2 | `node 2  mac 90:DA:72:87:CB:98`, and **no battery line** in `status` | `who_is_who.py COM37` |
| Wearable | `[oled] up` (or the "not found" line) and `[ble] state: 2 cot(s), mask 0x00` | `who_is_who.py COM30` |
| All | the hub's cot cards show no battery text | the TFT |

A good hub boot log looks like this:

```
I (3509) crynet: RESULT: PASS — 4 probes, front end and model agree with the host
I (4363) ili9341: the panel is up: 320 x 240, rotation 2 (madctl 0x80)
I (4367) hub_display: the display is up: 320 x 240
I (4393) link: node 1 is online
I (4395) link: node 2 is online
I (5038) link: node 1: rms 0.0120  seq 1  flags 0x07  crc 0x7438FF19  level 0.0050  streak 1  win 0.0380
```

Two things to read in it:

- **`RESULT: PASS`** — the hub's own self-check agrees with the host about the model's
  arithmetic. If it says `FAIL`, do not carry on; read the lines above it.
- **there is no `bat` field** in the `link:` lines. In the old build that line ended
  `... win 0.0100  bat 1520 mV`. Its absence is how you know the new firmware is
  running.

**The panel is optional.** If the TFT is not attached the hub says *"the display
could not be started"* and carries on — the radio and the Bluetooth server still come
up. You just cannot look at the cards.

**The OLED is optional on the wearable too.** Without it the wearable prints
`[oled] SSD1306 not found at 0x3C — check SDA 5 / SCL 6` and carries on. With it, it
prints `[oled] up`. Either way it should then find the hub and print
`[ble] state: 2 cot(s), mask 0x00`. `2 cot(s)` is the hub telling it how many cots it
can hear; `mask 0x00` means no cot is crying right now.

### The audio, once the microphones are on

With no INMP441 attached, a node reads `rms 0.0000` and `mean 0` — **that is correct**,
not a fault. There is nothing on the data line to be anything but zero.

The node firmware carries the I2S zero-watchdog (D-79): it restarts the I2S peripheral
after five seconds of consecutive exact-zero samples, so that a mic which has died
does not take the cot silent for good. **A board with no microphone attached produces
nothing but exact zeros, so the watchdog will restart the I2S forever on it.** The
`status` line shows the count:

```
I2S zero watchdog restarts=0
```

- **restarts=0 with a mic fitted** → correct; a live mic in a quiet room delivers
  noise, not zeros.
- **restarts climbing with a mic fitted** → the watchdog is firing on the *installed*
  mic. That is a fault to look at, not something to sit through.

Attach the microphones, then read a live window:

```powershell
python firmware/tools/verify_burst.py --port COM31
```

It writes the node's two-second window out as a WAV and reports its mean, RMS and
peak. Then the end-to-end test: play a recorded cry at each cot in turn and watch the
panel name the right cot and the wrist buzz. Keep the phone **at least 15 cm** from
the microphone — the INMP441 is fixed-gain and saturates closer than that, and the
hub correctly refuses a clipped window.

---

## 8. When something goes wrong

### The board is sitting in the bootloader and nothing comes up

**This is the most common failure, and it is the one from I-40.** A flash that stops
partway — wrong chip, wrong port, a yanked cable — leaves the target **in the
bootloader**, not running its firmware. It looks dead: no banner, no telemetry, the
hub stops hearing it.

Bring it back with `run`:

```powershell
# a cot node or the wearable
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32c3 --port COM31 run

# the hub
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32s3 --port COM32 run
```

### `could not open port 'COMxx'`

The port does not exist — either the board is not plugged in, or **Windows
renumbered it**. Re-run §3a and §3b; do not guess.

### `A fatal error occurred: Failed to connect to ESP32: Timed out waiting for packet header`

Two usual causes: the board is in the bootloader (see above), or the wrong board is on
that port. `chip-id` settles which:

```powershell
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32c3 --port COM31 chip-id
```

### The flash wrote but the board still behaves oddly

Read what is actually on it. `esptool` can dump the application partition:

```powershell
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32c3 --port COM31 read-flash 0x10000 0x80000 "$env:TEMP\node_app.bin"
```

### The hub shows a cot as offline

Look at the hub's log for the node's counters — they say where a burst went:

```
link: node 1: the burst stalled with 274 of 286 fragments (274 frames arrived)
link: node 1: its radio handed over 288 frames since the burst began, 288 of them left it, 0 were refused
```

`handed over == left it` with fragments missing means the frames were **lost in the
air**; `refused` non-zero means the node's radio queue is too small.

### The panel is dark

The hub says *"the display could not be started"* when the TFT is absent, and that is
fine — but a **present** TFT that stays dark is a wiring problem: CS 10, MOSI 11,
SCK 12, DC 13, RST 14, backlight 4, 3V3, GND. GPIO35–37 are the Octal PSRAM bus —
never wire them.

---

## 9. Backup and rollback

**Take a backup of each board's whole flash before you flash it.** It takes two
minutes and it is the only way back if a flash goes wrong. The helper does it for
you, as the first step:

```powershell
python firmware/tools/flash_unit.py --role node --port COM31 --backup
```

By hand:

```powershell
# a cot node or the wearable (ESP32-C3, 4 MB flash)
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32c3 --port COM31 read-flash 0x0 0x400000 "$env:TEMP\fullflash_31.bin"

# the hub (ESP32-S3, 16 MB flash) - bigger, so it takes longer
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32s3 --port COM32 read-flash 0x0 0x1000000 "$env:TEMP\fullflash_hub_32.bin"
```

Rollback is then one command — write the whole thing back at `0x0`:

```powershell
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32c3 --port COM31 write-flash 0x0 "$env:TEMP\fullflash_31.bin"

& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32s3 --port COM32 write-flash 0x0 "$env:TEMP\fullflash_hub_32.bin"
```

`write_flash` also works; `write-flash` is the current spelling.

The backups that exist right now, from the 2026-11-06 bench work:

| File | Board |
|---|---|
| `%TEMP%\fullflash_31.bin` | cot node 1 (4,194,304 bytes) |
| `%TEMP%\fullflash_37.bin` | cot node 2 (4,194,304 bytes) |
| `%TEMP%\wearable_baseline_COM30.bin` | the wearable (4,194,304 bytes, md5 `0ba262cd9dd6e6f255438e79dbeb729a`) |

The node backups were diffed against each other once: the **only** difference was the
NVS partition at `0x009000–0x00E000`, so their application firmware was
byte-identical.

**Copy them out of `%TEMP%`** — Windows clears that folder on its own schedule, and a
backup that disappears with it was never a backup.

---

## 10. Changing the firmware

You only need this section when you have **changed the code**. Rebuild the images
and refresh the hashes:

```powershell
python firmware/tools/make_prebuilt.py
```

That runs the three builds and rewrites `firmware/prebuilt/SHA256SUMS` and
`firmware/prebuilt/BUILD_INFO.json`:

| Role | Built with | Needs |
|---|---|---|
| hub | PlatformIO / ESP-IDF (`firmware/hub_infer`) | the vendored `esp-tflite-micro` and `esp-nn` components — `bash firmware/tools/fetch_deps.sh` once, **which needs network** |
| node | `arduino-cli compile` | the ESP32 core 3.3.12 (installed) |
| wearable | `arduino-cli compile` | the ESP32 core 3.3.12 and `Adafruit_GFX` + `Adafruit_SSD1306` (in the sketchbook) |

Then check, and flash:

```powershell
python firmware/tools/check_prebuilt.py    # are the images up to date with the source?
python firmware/tools/flash_unit.py --check
```

### Keeping the images in step with the source

Nothing forces `firmware/prebuilt/` to match the code — a sketch can be edited
and committed while the `.bin` files stay old, and the next person to flash a
board gets firmware that is not in the repository. Three things prevent it:

1. **`BUILD_INFO.json`** records, for every unit, the SHA-256 of every source file
   that went into it. `check_prebuilt.py` recomputes them and compares; when they
   differ it names the files that moved. The hashes are of the *content*, with line
   endings normalised, so the answer is the same on every machine and in CI.
2. **`flash.bat` runs the same check before it writes anything**, in PowerShell
   (`firmware/prebuilt/check_prebuilt.ps1`) so it needs no Python. It refuses to
   flash a stale or damaged image.
3. **GitHub checks it on every push.** `.github/workflows/prebuilt-check.yml`
   rebuilds all three units from the source and fails if the result differs from
   what is committed.

When `firmware/prebuilt/` is copied on its own, with no source beside it, the
freshness check cannot be made — the check says so and carries on. The images are
still verified against `SHA256SUMS`, and they were verified as up to date when they
were committed.

Two things worth knowing about the builds:

- **Compile the Arduino sketches with one job** (`-j 1`, which `make_prebuilt.py`
  already does). The parallel build runs the compiler out of memory on this
  16 GB machine and dies with `cc1plus.exe: out of memory`.
- **The hub build is reproducible and needs no network** once the two vendored
  components are on disk. The rebuild of 2026-11-07 produced a `firmware.bin`
  **byte-identical** to the one that was flashed to the bench units.

If you prefer to build and flash in one step, the older scripts still work and
compile from source: `flash_hub.py --port COM32` and
`flash_node.py --port COM31` (`--sketch wearable` for the wearable). They are the
right tool when you are iterating on the code; the prebuilt path in §5 is the right
tool for putting firmware on a board.

---

## 11. What this build deliberately does **not** do

The battery sense and every status LED are gone by design (**D-83**), not by
omission:

- **no divider** — no 220 kΩ, no 100 kΩ, no 100 nF anywhere in the system;
- **no cell-voltage telemetry**, and no battery text on the hub's panel;
- **no status LEDs** — not the node's link LED, not the node's SOC LED, not the
  hub's BLE-status LED, not the hub's SOC LED.

The consequence to keep in mind: **nothing in the system warns the caregiver that a
cell is nearly flat.** Watch the charge by eye.

The battery *power* is untouched: the cells, the LX-LCBST modules, the switches and
the boost converters are exactly as they were.

---

## 12. The one-line version

```powershell
python firmware/tools/flash_unit.py --check                                  # once
python firmware/tools/flash_unit.py --role hub     --port COM32 --log 25     # the hub, first
python firmware/tools/flash_unit.py --role node    --port COM31 --log 15     # node 1
python firmware/tools/flash_unit.py --role node    --port COM37 --log 15     # node 2
python firmware/tools/flash_unit.py --role wearable --port COM30 --log 15     # the wearable
```

— with the ports **verified** by §3 first, not assumed.

---

## 13. The bench card

One page, in the order you actually do it. Print it, or keep it on the screen next
to the boards.

```
1. WHAT IS PLUGGED IN
   python firmware/tools/flash_unit.py --list
   python firmware/tools/who_is_who.py COM30 COM31 COM32 COM37
   -> a MAC, not a COM number, is the identity of a board

2. IS THE TOOLCHAIN GOOD
   python firmware/tools/flash_unit.py --check
   -> every image hash must say OK; HASH MISMATCH means do not flash

3. BACK UP (before every flash)
   python firmware/tools/flash_unit.py --role node --port COM31 --backup
   -> copy the .bin out of %TEMP% somewhere that is not %TEMP%

4. FLASH, HUB FIRST, THEN THE NODES, THEN THE WEARABLE
   python firmware/tools/flash_unit.py --role hub     --port COM32 --log 25
   python firmware/tools/flash_unit.py --role node    --port COM31 --log 15
   python firmware/tools/flash_unit.py --role node    --port COM37 --log 15
   python firmware/tools/flash_unit.py --role wearable --port COM30 --log 15

5. CHECK THE LOG
   hub:        "RESULT: PASS - 4 probes", "node 1 is online", "node 2 is online",
               and NO "bat" field in the link: lines
   node:       "node 1  mac 90:DA:72:85:C5:44" (id 1) / 90:DA:72:87:CB:98 (id 2)
   wearable:   "[ble] state: 2 cot(s), mask 0x00"

6. A NEW NODE NEEDS ITS ID SET (115200 baud, over the USB console)
   id 1        <- the first cot        id 2   <- the second cot
   -> the hub watches cots 1 and 2 only; a MAC-derived id is usually neither

7. NOTHING COMES UP?  IT IS IN THE BOOTLOADER
   & "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
       --chip esp32c3 --port COM31 run

8. ROLL BACK
   & "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
       --chip esp32c3 --port COM31 write-flash 0x0 "$env:TEMP\crynet_backup_node_COM31.bin"
```

The order in step 4 is not a preference: the new hub reads both the old 34-byte and
the new 32-byte telemetry, the old hub reads only 34 — so a node must never meet a
hub that misreads it.

