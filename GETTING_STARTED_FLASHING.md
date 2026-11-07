# Flashing CryNet units — the guide for someone who has never flashed anything

**Written 2026-11-07.** For the D-83 firmware (no battery sense, no status LEDs).

This guide assumes you have **never** flashed a chip before. It does not
assume you know what PlatformIO is, what Arduino IDE is, where the
firmware files live, or what a COM port is. Every step is spelled out.

There are three ways to do this, and you only ever need **one** of them:

| | What you use | When you use it |
|---|---|---|
| **Way A** ⭐ | `flash.bat` — a file you double-click | **Most of the time.** Puts the finished firmware on a board. No IDE, no typing of long commands. |
| **Way B** | PlatformIO IDE (in VS Code) | You changed the hub's code and want to rebuild it and put it on the board. |
| **Way C** | Arduino IDE | You changed the node's or the wearable's code and want to rebuild it. |

Start with **Way A**. You can read B and C later, when you change code.

---

## The one-paragraph version

A microcontroller board has no program on it when it comes out of the box.
"Flashing" means copying a file onto it over the USB cable. The file is
called a **firmware image**. We keep those images finished and checked in
the repository at `firmware\prebuilt\`, so you never have to compile
anything. You plug the board in, you double-click `flash.bat`, you press
`2` (if it is a cot node), you type the port it is on, and it is done.

That is the whole job.

---

# WAY A — flash a board with `flash.bat` (no IDE needed)

## A1. What you need

1. **The board**, plugged into this PC with a **USB-C data cable**.
   A cable that only charges will not work — this is the single most
   common reason a board does not show up. If you have several cables,
   try another one before you suspect the board.

2. **The repository**, which is on this PC at:

   ```
   C:\Users\HP\.t3\projects\fp-two-node
   ```

   You do not need to move or copy it. Everything below happens inside it.

3. **`esptool`** — the one program that writes firmware to a chip. It is
   already on this PC at:

   ```
   C:\Users\HP\.platformio\packages\tool-esptool\esptool.exe
   ```

   `flash.bat` finds it by itself. You never type that path.

## A2. Where the files are

The firmware images are **already built** and sitting in the repository:

```
C:\Users\HP\.t3\projects\fp-two-node\firmware\prebuilt\
    hub\          bootloader.bin  partitions.bin  firmware.bin
    node\         bootloader.bin  partitions.bin  boot_app0.bin  app.bin
    wearable\     bootloader.bin  partitions.bin  boot_app0.bin  app.bin
```

Those `.bin` files **are** the firmware. Flashing = copying them onto the
board. The folder `firmware\prebuilt\` also holds `SHA256SUMS`, a list of
fingerprints. `flash.bat` checks every image against that list **before
it writes anything**, so a damaged file (a truncated copy, a disk
problem) is caught rather than flashed.

The tool you double-click is:

```
C:\Users\HP\.t3\projects\fp-two-node\firmware\prebuilt\flash.bat
```

## A3. Do it

1. Plug the board in with the USB cable.

2. Open File Explorer (the yellow folder on the taskbar). Paste this into
   the address bar at the top and press Enter:

   ```
   C:\Users\HP\.t3\projects\fp-two-node\firmware\prebuilt
   ```

   You should see `hub`, `node`, `wearable`, `flash.bat`, `watch.bat`,
   `check_prebuilt.ps1`, `list_ports.ps1` and `SHA256SUMS`.

3. **Double-click `flash.bat`.** A black window opens. It shows the path
   of the `esptool` it found, then checks the images:

   ```
   ok       hub\bootloader.bin
   ok       hub\firmware.bin
   ...
   all 11 images verified.
   ```

   If any line says **BAD** or **MISSING**, it stops there and flashes
   nothing. Copy the `firmware\prebuilt\` folder again from a good copy
   and try once more.

   Then the menu appears:

   ```
   Which unit are you flashing?

     1 = hub        the ESP32-S3 board with the screen
     2 = cot node   the ESP32-C3 board with the microphone
     3 = wearable   the ESP32-C3 board with the wrist screen
     4 = just tell me which board is on which port - flashes nothing
   ```

4. **Type the number and press Enter.** `1` for the hub, `2` for a cot
   node, `3` for the wearable.

5. It lists the USB ports currently on the PC, then asks:

   ```
   Which port is the node on - for example COM31 -
   ```

   Type the port it showed you in the list and press Enter.

   > **What is a port?** Every USB device that can talk to Windows gets a
   > name like `COM31`. The board is one of them. The list printed just
   > above the prompt is the list of what is plugged in *right now*, so
   > just pick the one that is new. `flash.bat` refuses a port that is not
   > in that list, so you cannot flash a board that is not plugged in.

6. It **backs up the board first** (to `C:\Users\HP\CryNet_Backups\`),
   then writes the firmware, then says:

   ```
   DONE.  The node on COM31 now has the CryNet firmware.
   ```

7. Press any key to close the window.

## A4. If the board is new and the backup fails

A brand-new board sometimes refuses the backup read. The script notices
and asks:

```
Flash anyway without a backup?  Type y to go ahead:
```

Type `y` and press Enter. Nothing is wrong — a board with no old firmware
on it has nothing worth backing up.

If the board will not connect at all, hold its **BOOT** button while you
plug the USB cable in, then let go. That puts it into its bootloader, and
it will answer.

## A5. See what the board says

To read a board's messages (this is the Arduino IDE's "Serial Monitor",
without the IDE), double-click:

```
C:\Users\HP\.t3\projects\fp-two-node\firmware\prebuilt\watch.bat
```

It asks which port, then prints what the board says, live, at 115200 baud.
Press **Ctrl+C** to stop.

What a healthy board says:

| Unit | Lines to look for |
|---|---|
| Hub | `RESULT: PASS — 4 probes`, then `node 1 is online`, `node 2 is online` |
| Cot node | `node 1 mac 90:DA:72:85:C5:44` (or `node 2 mac ...`) |
| Wearable | `[oled] up` and `[ble] state: 2 cot(s), mask 0x00` |

The hub's `link:` lines must **not** contain a `bat` field — that was
removed in D-83.

## A6. Which board is which? (finding out without guessing)

If you have several boards plugged in and do not know which is which,
run `flash.bat` and choose **4**. It reads the MAC address of every board
on every port and tells you which chip is on each:

```
    COM31 ...
      this is an ESP32-C3 - a cot node or the wearable
      MAC: 90:DA:72:87:CB:98
    COM32 ...
      this is an ESP32-S3 - the hub
      MAC: 30:30:F9:17:2F:80
```

**Write the MAC down on the board itself.** The COM number can change
when you unplug and replug something, or plug into a different USB
socket. The MAC never changes. It is the board's real identity.

The two cot nodes are told apart by their MAC:

| Unit | MAC |
|---|---|
| Cot node 1 | `90:DA:72:85:C5:44` |
| Cot node 2 | `90:DA:72:87:CB:98` |

## A7. A brand-new node needs its number set

A node's number (which cot it is) is stored **on the board itself**, so
it survives a reflash. A brand-new board has no number, so it guesses
one from its MAC — and two new boards can guess the same one.

The hub only listens to **cot 1 and cot 2**. A node on any other number
is ignored, and **the node says so on its own console** at boot:

```
WARNING: this hub watches cots 1 and 2 only. Set this board with "id 1" or "id 2".
```

To set it, open `watch.bat` on that node's port and type:

```
id 1
```

for the first cot, or

```
id 2
```

for the second. The node saves it and keeps it through every future flash.

Type `status` to see its number, MAC and link bar. Type `help` for the
full list of commands.

## A8. The order to flash in

If you are reflashing a whole set, do the **hub first**.

A new node sends 32 bytes of telemetry; an old one sends 34. A new hub
reads both. An old hub only understands 34. So a node that has not been
reflashed yet, talking to an old hub, is misread.

**Hub first, then the nodes, then the wearable.**

---

# WAY B — PlatformIO IDE (for changing the hub's code)

You do not need this to flash a board. You need it when you have **edited
the hub's source** and want to rebuild and redeploy.

## B1. What PlatformIO IDE is

It is an **add-on to VS Code** (the code editor you may already have).
It adds a sidebar panel with buttons like *Build*, *Upload* and *Monitor*.
VS Code is at:

```
C:\Users\HP\AppData\Local\Programs\Microsoft VS Code
```

The PlatformIO add-on is already installed inside it (you can see it in
the extensions list as `platformio.platformio-ide`). So there is nothing
to install.

## B2. Where the hub's files are

```
C:\Users\HP\.t3\projects\fp-two-node\firmware\hub_infer\
    platformio.ini          <- the settings: which board, which chip
    CMakeLists.txt
    sdkconfig.defaults      <- ESP-IDF settings
    partitions_16mb.csv     <- the memory map
    src\                    <- the hub's actual code
        main.c
        probes.c
        link_stage.c
        console.c
    components\             <- the model's DSP, inference and display code
        crynet_dsp\  crynet_infer\  crynet_model\  crynet_proto\
        node_link\   ble_alert\    hub_display\
        esp-tflite-micro\  esp-nn\   <- fetched, see B6
```

`platformio.ini` is the file that says what board this is:

```ini
[env:esp32s3]
platform = espressif32 @ 8.0.0
board = esp32-s3-devkitc-1     ; the ESP32-S3 DevKitC-1 N16R8
framework = espidf
board_build.flash_size = 16MB
upload_speed = 921600
monitor_speed = 115200
```

## B3. Open it

1. Start **VS Code**.
2. Menu **File → Open Folder…**
3. Pick `C:\Users\HP\.t3\projects\fp-two-node\firmware\hub_infer`
   (the `hub_infer` folder itself, not its parent).
4. VS Code reloads. On the left edge, a **blue alien-head icon** appears
   (the PlatformIO icon). Click it.

That panel is PlatformIO. It is where the buttons live.

## B4. The buttons

There are **two** places to click, and they do the same things.

**Place 1 — the PlatformIO sidebar.** The blue alien-head icon on the far
left of VS Code opens the PlatformIO panel. It has two sections:

- **PROJECT TASKS** — a tree. Expand it and you see your project, then
  **General**, and under that the four actions:

  | Task | What it does |
  |---|---|
  | **Build** | Compiles the code into `.bin` files. Takes ~15 s. Writes nothing to the board. |
  | **Upload** | Builds, then writes the new firmware to the board over USB. |
  | **Monitor** | Opens a live window of what the board says at 115200 baud. |
  | **Clean** | Deletes the build output, so the next build starts fresh. |

  (There is also **Test** and sections for **Platform** and
  **Libraries** — you do not need those.)

- **QUICK ACCESS** — a shortcut to the PlatformIO home page.

**Place 2 — the editor's title bar.** When a source file is open, the
same actions appear as small icons at the **top right of the tab bar**:
a **✓** for Build, a **→** for Upload, a **🗑** for Clean. (If they are
not there, they are switched off — see *Settings* → search
`platformio-ide.showEditorTitleShortcuts` and turn it on.)

**Upload** is the one that flashes. **Build** alone never touches the
board.

**Before you can upload**, PlatformIO needs to know which port the board
is on. It usually finds it by itself and shows the name in the bottom
status bar. If it picked the wrong one, or shows "Auto", click the port
field in the **bottom-right status bar** and pick yours from the list.

## B5. Build and upload, step by step

1. Plug the hub in.
2. Open `firmware\hub_infer` in VS Code as above.
3. Click the PlatformIO icon → press **Build** (✓). The terminal at the
   bottom shows the compile. It must end with:

   ```
   ========================= [SUCCESS] Took 15.23 seconds =========================
   ```

   ```
   RAM:   [=         ]  13.0% (used 42496 bytes from 327680 bytes)
   Flash: [======    ]  63.6% (used 1334819 bytes from 2097152 bytes)
   ```

4. Check the bottom-right status bar says the right port. If not, click
   it and choose the hub's port.
5. Press **Upload**. It writes the three images and the board reboots.
6. Press **Monitor**. You should see:

   ```
   I (3509) crynet: RESULT: PASS — 4 probes, front end model agree host
   I (4363) ili9341: panel up: 320 x 240, rotation 2 (madctl 0x80)
   I (4393) link: node 1 is online
   I (4395) link: node 2 is online
   ```

   `RESULT: PASS` means the hub's own self-check agrees with the host
   about the model's arithmetic. If it says `FAIL`, stop and read the
   lines above it.

   Press **Ctrl+C** to close the monitor.

## B6. The two fetched dependencies

The hub uses Espressif's TFLite Micro port and ESP-NN. They are **not** in
git — they are pinned by commit and fetched once. If the folder
`firmware\hub_infer\components\esp-tflite-micro` or
`firmware\hub_infer\components\esp-nn` is missing, run this **once**
(needs internet):

```bash
bash firmware/tools/fetch_deps.sh
```

On this PC they are already there, so you will not need it.

## B7. If you prefer the terminal

VS Code's terminal (Ctrl+`) opens in the project folder. The same three
buttons, as commands.

**Careful with the command.** PlatformIO has its **own** Python, inside
`C:\Users\HP\.platformio\penv\`. It is not the `python` you get on the
command line, so plain `python -m platformio` says *"No module named
platformio"*. Use PlatformIO's own executable instead:

```powershell
cd C:\Users\HP\.t3\projects\fp-two-node\firmware\hub_infer

# build
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run

# build and flash
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -t upload

# watch the boot log
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor
```

If you prefer the module form, it works with PlatformIO's Python:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -m platformio run
```

## B8. Where the built files end up

After a build, the images PlatformIO produced are here:

```
C:\Users\HP\.t3\projects\fp-two-node\firmware\hub_infer\.pio\build\esp32s3\
    bootloader.bin     22,560 bytes   -> goes to 0x0
    partitions.bin      3,072 bytes   -> goes to 0x8000
    firmware.bin    1,335,248 bytes   -> goes to 0x10000
```

Those exact three bytes are also copied into
`firmware\prebuilt\hub\` by `make_prebuilt.py`, so Way A and Way B flash
the same firmware. The build is **reproducible**: rebuilding gives a
byte-identical `firmware.bin` (checked 2026-11-07).

---

# WAY C — Arduino IDE (for changing the node's or the wearable's code)

You need this when you have edited a **`.ino`** sketch. The node and the
wearable are ordinary Arduino sketches; the hub is not (it is ESP-IDF).

## C1. Why there are two IDEs

| | Hub | Cot node / wearable |
|---|---|---|
| Board | ESP32-S3 DevKitC-1 | ESP32-C3 SuperMini |
| Build | ESP-IDF (PlatformIO) | Arduino (`.ino`) |
| Where | `firmware\hub_infer\` | `firmware\node\node_crynet\`, `firmware\wearable\wearable_crynet\` |

The hub runs TensorFlow Lite Micro with ESP-NN SIMD kernels, which are
ESP-IDF-level components with their own build rules. The nodes are
ordinary sketches. Keeping them apart means each is built the way that
suits it — and the IDE you touch most often stays simple.

## C2. Where the node's and wearable's files are

```
C:\Users\HP\.t3\projects\fp-two-node\firmware\node\node_crynet\node_crynet.ino
C:\Users\HP\.t3\projects\fp-two-node\firmware\wearable\wearable_crynet\wearable_crynet.ino
```

Each `.ino` is one self-contained file. Open it in a text editor and you
can read the whole firmware.

## C3. The one rule that catches everyone

**The Arduino IDE cannot build a sketch that lives in a normal folder.**
It only builds sketches that sit inside its own sketchbook:

```
C:\Users\HP\Documents\Arduino\
```

So the source of truth is in the repository, and it is **copied** into the
sketchbook before building. If you edit the `.ino` in the repository and
open it in the IDE, you will be building the **old** copy — this has
caught out everyone who tried it.

**So: edit in the repository, then copy across.** The copy is one
double-click:

```
C:\Users\HP\.t3\projects\fp-two-node\firmware\tools\copy_sketches.bat
```

It copies `node_crynet`, `node_capture` and `wearable_crynet` into
`C:\Users\HP\Documents\Arduino\`, replacing what was there.

## C4. Build and upload a node in the Arduino IDE

1. Run `copy_sketches.bat` (double-click it).
2. Start the **Arduino IDE** (it is at
   `C:\Users\HP\AppData\Local\Programs\Arduino IDE\Arduino IDE.exe`).
3. Menu **File → Open…** (or **File → Sketch → Open**). Pick:
   `C:\Users\HP\Documents\Arduino\node_crynet\node_crynet.ino`
4. Menu **Tools → Board → WeAct Studio ESP32C3**
   (if the board list is not showing, click on "Select a Board" in the
   toolbar's first dropdown and type `esp32`).
5. Menu **Tools → Port** → pick the node's port. (Check `flash.bat`
   option 4, or the Arduino IDE's own bottom-right port dropdown, to
   see which port is which board.)
6. Menu **Tools → USB CDC On Boot** should say **Enabled**. It already
   is by default for this board — leave it. This option is what makes the
   serial console run over the native USB; with it off, the console is
   dead and you cannot set the node's number.
7. Click the **→ (Upload)** button in the toolbar. (The → is Upload; the
   ✓ is Verify, which only compiles and tells you the size.)

   The first build takes a minute or two. Arduino prints the sketch size
   at the end:
   ```
   Global variables use 9,437 bytes (3%) of dynamic memory
   ```
8. It reboots the board. **Wait ~8 seconds** before opening the serial
   monitor — the node takes a moment to boot and start its radio.

To watch it, use **Tools → Serial Monitor**, set the baud rate to
**115200** at the bottom right, and press the board's **RESET** button.
You should see:

```
CryNet node firmware — Stage 2b
node id 1 (saved)
```

## C5. Build and upload the wearable

Same as above, except:

- Open `C:\Users\HP\Documents\Arduino\wearable_crynet\wearable_crynet.ino`
- Board: **WeAct Studio ESP32C3** (same)
- USB CDC On Boot: **Enabled** (same)
- The OLED uses **SDA = GPIO 5, SCL = GPIO 6**

Its libraries (`Adafruit_GFX`, `Adafruit_SSD1306`) are already in the
sketchbook at `C:\Users\HP\Documents\Arduino\libraries\`, so the IDE
finds them with no download.

## C6. Where the Arduino build's files end up

The Arduino IDE keeps them in a temporary folder that it cleans up. To
get a copy that stays put, use the repository's own build script:

```powershell
cd C:\Users\HP\.t3\projects\fp-two-node
python firmware/tools/make_prebuilt.py --role node
python firmware/tools/make_prebuilt.py --role wearable
```

That writes the finished images into `firmware\prebuilt\node\` and
`firmware\prebuilt\wearable\` and refreshes `SHA256SUMS`, so they become
usable by Way A.

Two things to know about that script:

- It compiles **one job at a time** (`-j 1`). A parallel Arduino build
  runs the compiler out of memory on this 16 GB PC and dies with
  `cc1plus.exe: out of memory`.
- **All three units rebuild byte-identical.** Re-checked 2026-11-07: the
  node's `app.bin` came back as `aabb406f…` and the wearable's as
  `193cdaaf…`, the same hashes as the shipped images, and the hub's
  `firmware.bin` as `f7f09a34…`. So a rebuild that changes nothing
  changes nothing in the image either — which is what makes
  `SHA256SUMS` a meaningful check.

---

# When it fails

## "There is no port called COM31 on this PC right now."

The board is not plugged in, or Windows gave it a different number.
Run `flash.bat` option 4 to see what is actually there.

## `could not open port 'COMxx'`

Same cause. Check the cable — **a charge-only USB cable is the usual
reason**. Then check the port list again.

## `Failed to connect to ESP32-C3: No serial data received`

The board did not answer. In order of likelihood:

1. **It is in its bootloader.** Hold **BOOT** while plugging it in,
   release, and retry. If the flash was interrupted, this is the usual
   state — it looks dead, prints nothing, and the hub stops hearing it.
2. **Wrong port.** Run `flash.bat` option 4.
3. **The wrong chip type was assumed.** `flash.bat` picks the chip from
   the unit you chose, so this only happens if a hub is plugged into
   the port you are using for a node.

To bring a board out of its bootloader:

```powershell
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32c3 --port COM31 run
```

(`--chip esp32s3` for the hub.)

## The flash wrote, but the board still misbehaves

Read what is actually on it:

```powershell
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" --chip esp32c3 --port COM31 read-flash 0x10000 0x80000 "$env:TEMP\node_app.bin"
```

## The hub says a cot is "lost in the air"

`refused` non-zero means the node's radio queue is too small, not that
the link is broken.

## The hub's screen stays dark

The hub prints "the display could not be started" when the TFT is
missing — that is fine. If the TFT **is** there but the screen stays
dark, it is a wiring problem: CS 10, MOSI 11, SCK 12, DC 13, RST 14,
backlight 4, 3V3, GND. **GPIO 35–37 are the octal PSRAM bus — never wire
them.**

## The node shows `rms 0.0000`

**That is correct** when no microphone is attached. There is nothing on
the data line but zero. The node's I2S zero-watchdog restarts the
peripheral after five seconds of exact zeros, so the cot does not go
permanently silent. Check the counter with `status`:

```
I2S zero watchdog restarts=0
```

- `restarts=0` with a mic fitted → correct.
- `restarts` climbing with a mic fitted → a fault to look at.

---

# Backup and rollback

**Take a backup before every flash.** `flash.bat` does this
automatically, to `C:\Users\HP\CryNet_Backups\<unit>_<port>_backup.bin`.

> Windows clears `%TEMP%` on its own schedule. A backup left there
> disappears. `flash.bat` uses `C:\Users\HP\CryNet_Backups\`, which it
> does not.

To roll back, write the backup file back at address `0x0`:

```powershell
& "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
  --chip esp32c3 --port COM31 write-flash 0x0 "$env:USERPROFILE\CryNet_Backups\node_COM31_backup.bin"
```

---

# The one-page bench card

Print this, or keep it on screen next to the boards.

```
1. WHAT IS PLUGGED IN
   flash.bat, choose 4          -> MAC of every board on every port
   write the MAC on the board   -> COM numbers move, MACs do not

2. FLASH IT
   flash.bat, choose 1/2/3, type the port
   hub FIRST, then nodes, then wearable

3. SET A NEW NODE'S NUMBER (USB console, 115200)
   id 1     first cot
   id 2     second cot
   -> the hub only listens to cots 1 and 2

4. CHECK THE LOG (watch.bat, or Arduino IDE Serial Monitor)
   hub:      "RESULT: PASS - 4 probes", "node 1 is online", "node 2 is online"
             and NO "bat" field in the link: lines
   node:     "node 1 mac 90:DA:72:85:C5:44"  (id 1)
             "node 2 mac 90:DA:72:87:CB:98"  (id 2)
   wearable: "[ble] state: 2 cot(s), mask 0x00"

5. NOTHING COMES UP?  IT IS IN ITS BOOTLOADER
   & "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
     --chip esp32c3 --port COM31 run

6. ROLL BACK
   & "$env:USERPROFILE\.platformio\packages\tool-esptool\esptool.exe" `
     --chip esp32c3 --port COM31 write-flash 0x0 `
     "$env:USERPROFILE\CryNet_Backups\node_COM31_backup.bin"
```

---

# Why the firmware is written in pieces, not as one file

`flash.bat` writes each image at a fixed address:

| Unit | Address | File |
|---|---|---|
| Hub | `0x0` | `bootloader.bin` |
| | `0x8000` | `partitions.bin` |
| | `0x10000` | `firmware.bin` |
| Node / wearable | `0x0` | `bootloader.bin` |
| | `0x8000` | `partitions.bin` |
| | `0xe000` | `boot_app0.bin` |
| | `0x10000` | `app.bin` |

**These offsets skip the NVS partition on purpose.** NVS lives at
`0x9000`–`0xE000` on the C3 boards and `0x9000`–`0xF000` on the hub, and
it is where a node keeps its number. Writing over it would wipe that.
One merged image would fill the gaps with `0xFF` and destroy it.

**The hub's images are DIO, not QIO.** The ROM on the ESP32-S3 cannot
read flash in QIO mode before the bootloader has set up its own timing,
so a QIO image makes the chip watchdog-reset in a loop the moment it
powers up. The bootloader in `firmware\prebuilt\hub\bootloader.bin`
already has the DIO header, so writing these three files is safe. The
same holds for the C3 boards.

---

# What changed in D-83 (so you recognise the log)

- **No battery sense.** No divider, no 100 nF capacitor, no telemetry of
  the cell voltage. The node's telemetry frame is 32 bytes, not 34.
- **No status LEDs.** Not the node's link LED, not the node's SOC LED,
  not the hub's BLE-status LED, not the hub's SOC LED. The wearable's
  OLED carries the status instead.

The consequence to keep in mind: **nothing in the system warns the
caregiver that a cell is nearly flat.** Watch the charge by eye. The
battery *power* side is untouched — cells, LX-LCBST modules, switches and
boost converters are exactly as they were.
