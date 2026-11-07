# Flashing the CryNet units — a step-by-step guide

**Written 2026-11-07, against the D-83 firmware (no battery sense, no status LEDs).**
Read it with `SYSTEM_WIRING.md` (what to wire) and `SYSTEM_UPDATE.md` (what has happened).

Every command below is run **from the repository root** — `C:\Users\HP\.t3\projects\fp-two-node`
for the two-cot system on the bench, `C:\Users\HP\.t3\projects\fp-2` for the three-cot fallback.
The tools live in `firmware/tools/` in both, and both work the same way.

---

## 0. Before you start

**You need:** the units, a USB cable for each, and this repository checked out. Nothing else —
the whole toolchain is already on the machine:

| Tool | Where it lives | Used for |
|---|---|---|
| `esptool` | `%USERPROFILE%\.platformio\packages\tool-esptool\esptool.exe` | the hub, and recovering a board stuck in the bootloader |
| `arduino-cli` | `%LOCALAPPDATA%\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe` | the two cot nodes and the wearable |
| `pyserial` | already installed for Python | the identification tools |

The two scripts that do the work are `firmware/tools/flash_hub.py` and
`firmware/tools/flash_node.py`. **Neither of them guesses a port if you give one** — always
give the port explicitly. That is the rule that exists because of the incident in `DECISIONS.md`
I-40, where a flash aimed at the wrong port parked a node in its bootloader and the radio went
silent for two minutes.

**Before you touch anything, take a backup of each board's whole flash.** It takes two minutes
and it is the only way back if a flash goes wrong:

```powershell
# a cot node (ESP32-C3, 4 MB flash) - one per node, with its own port
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32c3 --port COM31 read-flash 0x0 0x400000 "$env:TEMP\fullflash_31.bin"

# the wearable (ESP32-C3, 4 MB flash)
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32c3 --port COM30 read-flash 0x0 0x400000 "$env:TEMP\wearable_fullflash_30.bin"

# the hub (ESP32-S3, 16 MB flash) - bigger, so it takes longer
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32s3 --port COM32 read-flash 0x0 0x1000000 "$env:TEMP\fullflash_hub_32.bin"
```

Rollback is then one command — see §8.

---

## 1. Work out which board is which, **before** you flash anything

This is the step that saves the most grief, because **a COM port number is not an identity.**
Windows assigns COM numbers from the USB path and the enumeration order, so the same physical
board gets a different number when you move it to another socket or replug it. What identifies
a board for good is its **MAC address**, which is burned into the chip.

The map as it stood on 2026-11-07, when the units were last on the bench:

| Board | MAC | Port that day | How it appears on USB |
|---|---|---|---|
| **Hub** (ESP32-S3 DevKitC) | — | COM32 | `USB-Enhanced-SERIAL CH343` — a USB-serial bridge |
| **Cot node 1** | `90:DA:72:85:C5:44` | COM31 | `USB Serial Device` (Espressif native USB) |
| **Cot node 2** | `90:DA:72:87:CB:98` | COM37 | `USB Serial Device` (Espressif native USB) |
| **Wearable** | — | COM30 | `USB Serial Device` (Espressif native USB) |

**Treat that table as a memory aid, not as a script.** The numbers will move.

### 1a. List what is on USB

```powershell
Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.Name -match 'COM\d+' -and $_.Name -notmatch 'Bluetooth' } |
  ForEach-Object { "$($_.DeviceID)  |  $($_.Name)" }
```

Read it like this:

- **`USB-Enhanced-SERIAL CH343 (COM32)`** → the **hub**. The S3 DevKitC has a CH343 USB-serial
  bridge on it.
- **`USB Serial Device (COMxx)`** → an Espressif board on its own native USB. That is a cot node
  **or** the wearable; you cannot tell them apart from the USB descriptor alone.

Or, in Python, which is friendlier:

```powershell
python firmware/tools/collect_clips.py --list
```

### 1b. Ask each board who it is

```powershell
python firmware/tools/who_is_who.py COM30 COM31 COM32 COM37
```

For each port the tool resets the board over RTS/EN and reads the banner it prints at boot.
**It does not flash anything.** A cot node answers with its id and its MAC:

```
CryNet node firmware — Stage 2b
node id 1 (derived from the MAC; change it with "id <n>")
...
node 1  mac 90:DA:72:85:C5:44
```

The wearable answers with its OLED line and then its Bluetooth lines:

```
[oled] up
[ble] connecting to 30:30:F9:17:2F:80
[ble] hub connected
[ble] state: 2 cot(s), mask 0x00
```

If a board prints something else entirely, it is running some other sketch — flash the right
one onto it and move on.

### 1c. If a node is on the wrong id

The id lives in the board's own NVS and **survives a reflash** (a reflash that does not erase
the NVS partition, which is what these tools do). A board that has never been named derives
its id from its MAC — and two identical boards can derive the *same* number, so the MAC is what
settles a doubt.

To rename a node, over its serial console:

```
id 2          <- sets and saves the id
status        <- prints the id, the MAC, the link bar and the window
```

**The two-cot hub watches cots 1 and 2 only.** A node left on id 3 is ignored by it, and says
so on its console: *"WARNING: this hub watches cots 1 and 2 only."*

---

## 2. The order: **hub first, then the nodes, then the wearable**

This is not a preference. The telemetry frame changed in this build:

- the **new** node sends a **32-byte** payload (16 base bytes, then the radio counters);
- the **old** node sent **34 bytes** (the same, plus two bytes of battery voltage in the middle).

The **new hub reads both** — it looks at the payload length and picks the right offsets — so a
node that has not been reflashed yet cannot turn the hub's radio counters to noise. But the
**old hub only understands 34 bytes.** So:

> **Flash the hub first.** Then a node never meets a hub that misreads it.

---

## 3. Flash the hub (ESP32-S3)

```powershell
python firmware/tools/flash_hub.py --port COM32
```

What it does: writes three images at the offsets the partition table expects — the bootloader at
`0x0`, the partition table at `0x8000`, the application at `0x10000` — then opens the port and
prints the hub's boot log for 20 seconds.

**Do not pass `--merged`** for this job. The combined image must be written in **DIO** mode; the
ROM on this board cannot read the flash in QIO before the bootloader has set up its own timing,
and a QIO image makes the chip watchdog-reset in a loop right after power-on.

**A good boot log looks like this:**

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
  `... win 0.0100  bat 1520 mV`. Its absence is how you know the new firmware is running.

**The panel is optional.** If the TFT is not attached the hub says *"the display could not be
started"* and carries on — the radio and the Bluetooth server still come up. You just cannot
look at the cards.

To read the log without flashing again:

```powershell
python firmware/tools/flash_hub.py --port COM32 --log-only --seconds 60
```

---

## 4. Flash a cot node (ESP32-C3)

One board at a time, with **its own port named**:

```powershell
python firmware/tools/flash_node.py --port COM31      # node 1
python firmware/tools/flash_node.py --port COM37      # node 2
```

The script compiles `firmware/node/node_crynet/node_crynet.ino` with the Arduino core
(`esp32:esp32:weact_studio_esp32c3`, core 3.3.12) and uploads it. **It builds from the copy in
the repository**, not from the sketchbook, so what you flash is what is in the repo.

**A good result ends like this:**

```
Sketch uses 982357 bytes (74%) of program storage space.
Writing at 0x00100120 [===========================> ] 100.0% 604155/604155 bytes...
Wrote 983328 bytes (604155 compressed) at 0x00010000 in 3.9 seconds (2040.7 kbit/s).
Verifying written data...
Hash of data verified.
Hard resetting via RTS pin...
node on COM37 is running the new firmware
```

**`Hash of data verified` is the line that matters.** If it does not appear, the flash did not
complete — fix it before moving on.

**The node's id survives.** The flash writes the application partition, not the NVS partition,
so a node that was id 2 is still id 2 afterwards. Confirm it:

```powershell
python firmware/tools/who_is_who.py COM37
```

### The I2S zero-watchdog, and what it means when the mic is off

This firmware carries the zero-watchdog for the first time (it was committed but never flashed
while you were soldering). It restarts the I2S peripheral after five seconds of consecutive
exact-zero samples, so that a mic which has died does not take the cot silent for good.

**A board with no microphone attached produces nothing but exact zeros, so the watchdog will
restart the I2S forever on it.** The `status` line shows the count:

```
I2S zero watchdog restarts=0
```

- **restarts=0 with a mic fitted** → correct, the watchdog stays quiet because a live mic in a
  quiet room delivers noise, not zeros.
- **restarts climbing with a mic fitted** → the watchdog is firing on the *installed* mic.
  That is a fault to look at, not something to sit through.

---

## 5. Flash the wearable (ESP32-C3)

```powershell
python firmware/tools/flash_node.py --port COM30 --sketch wearable
```

Same tool, `--sketch wearable` instead. It compiles `firmware/wearable/wearable_crynet/`.

**The OLED is optional at flash time.** Without it the wearable prints
`[oled] SSD1306 not found at 0x3C — check SDA 5 / SCL 6` and carries on. With it, it prints
`[oled] up`. Either way it should then find the hub over Bluetooth and print:

```
[ble] state: 2 cot(s), mask 0x00
```

`2 cot(s)` is the hub telling it how many cots it can hear. `mask 0x00` means no cot is crying
right now.

**Nothing about the wearable changed in this build** — it never had a battery readout or a
status LED — so it only needs flashing if it is carrying some other sketch.

---

## 6. Verify, unit by unit

| Unit | Check | Where to look |
|---|---|---|
| Hub | `RESULT: PASS — 4 probes` | the boot log, §3 |
| Hub | `node 1 is online`, `node 2 is online` | the boot log |
| Hub | **no `bat` field** in the `link:` lines | the boot log |
| Node 1 | `node 1  mac 90:DA:72:85:C5:44`, and **no battery line** in `status` | `who_is_who.py COM31` |
| Node 2 | `node 2  mac 90:DA:72:87:CB:98`, and **no battery line** in `status` | `who_is_who.py COM37` |
| Wearable | `[oled] up` (or the "not found" line) and `[ble] state: 2 cot(s), mask 0x00` | `who_is_who.py COM30` |
| All | the hubs's cot cards show no battery text | the TFT |

### Then the audio, once the microphones are on

With no INMP441 attached, a node reads `rms 0.0000` and `mean 0` — **that is correct**, not a
fault. There is nothing on the data line to be anything but zero.

Attach the microphones, then:

```powershell
python firmware/tools/who_is_who.py COM31
```

and look for a **non-zero** `rms`. Then the end-to-end test: play a recorded cry at each cot
in turn and watch the panel name the right cot and the wrist buzz. Keep the phone **at least
15 cm** from the microphone — the INMP441 is fixed-gain and saturates closer than that, and the
hub correctly refuses a clipped window.

```powershell
python firmware/tools/verify_burst.py --port COM31
```

writes the node's two-second window out as a WAV and reports its mean, RMS and peak.

---

## 7. When something goes wrong

### The board is sitting in the bootloader and nothing comes up

**This is the most common failure, and it is the one from I-40.** A flash that stops partway —
wrong chip, wrong port, a yanked cable — leaves the target **in the bootloader**, not running
its firmware. It looks dead: no banner, no telemetry, the hub stops hearing it.

Bring it back with `run`:

```powershell
# a cot node or the wearable
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32c3 --port COM31 run

# the hub
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32s3 --port COM32 run
```

### `could not open port 'COMxx'`

The port does not exist — either the board is not plugged in, or **Windows renumbered it**.
Re-run §1a and §1b; do not guess.

### `A fatal error occurred: Failed to connect to ESP32: Timed out waiting for packet header`

Two usual causes: the board is in the bootloader (see above), or the wrong board is on that
port. `chip-id` settles which:

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

`handed over == left it` with fragments missing means the frames were **lost in the air**;
`refused` non-zero means the node's radio queue is too small.

### The panel is dark

The hub says *"the display could not be started"* when the TFT is absent, and that is fine —
but a **present** TFT that stays dark is a wiring problem: CS 10, MOSI 11, SCK 12, DC 13,
RST 14, backlight 4, 3V3, GND. GPIO35–37 are the Octal PSRAM bus — never wire them.

---

## 8. Rollback

Every board's flash was read before the last flash, so any board can be put back exactly as it
was:

```powershell
# a cot node or the wearable - write the whole 4 MB back at 0x0
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
    --chip esp32c3 --port COM31 write-flash 0x0 "$env:TEMP\fullflash_31.bin"

# the hub - 16 MB
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

The node backups were diffed against each other once: the **only** difference was the NVS
partition at `0x009000–0x00E000`, so their application firmware was byte-identical.

---

## 9. What this build deliberately does **not** do

The battery sense and every status LED are gone by design (**D-83**), not by omission:

- **no divider** — no 220 kΩ, no 100 kΩ, no 100 nF anywhere in the system;
- **no cell-voltage telemetry**, and no battery text on the hub's panel;
- **no status LEDs** — not the node's link LED, not the node's SOC LED, not the hub's
  BLE-status LED, not the hub's SOC LED.

The consequence to keep in mind: **nothing in the system warns the caregiver that a cell is
nearly flat.** Watch the charge by eye.

The battery *power* is untouched: the cells, the LX-LCBST modules, the switches and the
boost converters are exactly as they were.

---

## 10. The one-line version

```powershell
python firmware/tools/flash_hub.py  --port COM32                      # the hub, first
python firmware/tools/flash_node.py --port COM31                      # node 1
python firmware/tools/flash_node.py --port COM37                      # node 2
python firmware/tools/flash_node.py --port COM30 --sketch wearable    # the wearable
```

— with the ports **verified** by §1 first, not assumed.
