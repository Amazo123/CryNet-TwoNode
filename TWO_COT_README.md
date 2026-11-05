# CryNet — two-cot edition

A separate build of CryNet, the infant cry monitor, for a hub that watches
**two cots** instead of three. The three-cot system lives in its own
repository and is not modified by anything here.

The chain is unchanged and was verified end to end before this fork: a
microphone on a cot node → a frozen two-second window over ESP-NOW → the
INT8 model on the hub → a named cot on the panel and on the caregiver's
wrist. What is different here is the **panel layout** and the **link
reporting**.

## What this edition changes

**Two cots, enforced.** `NODE_LINK_MAX_NODES` and `HUB_DISPLAY_MAX_NODES`
are 2, and the hub's link layer rejects any frame whose node id falls
outside 1..2 before it can claim a slot. A third board is not hidden from
the panel — it is never heard.

**The panel, redesigned.** Two full-width cards, one per cot:

```
┌──────────────────────────────────────┐
│ COT 1                      ONLINE    │   name and state
│ ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬  RMS 0.012      │   level bar with its number
│ ▂▃▄█  LINK -58 dBm        BAT ~92%   │   network bar, link, battery
└──────────────────────────────────────┘
```

The RMS used to share its line with the battery, which put three readings
on one row and made the card hard to read in a dark room. Each pair now has
a row of its own.

**A network bar on both ends.** The hub's link layer already measured each
cot's RSSI but never exposed it; it now reaches the panel, where each cot
gets a four-bar glyph — green at three bars or more, amber below — with the
dBm beside it and `LINK --` when there is no reading.

The cot nodes show the same bar for their own view of the link, on the
serial console (`status` prints `link   [####] -58 dBm`). For that reading
to be live the hub now sends a **heartbeat every second** — the protocol
already defined that frame type and the nodes always understood it, but the
hub had never sent one.

**The connection LED is now real.** `SYSTEM_WIRING.md` 5.1 specifies a
GPIO10 connection LED on the node, lit only while a valid hub heartbeat has
arrived within a timeout. That was not implementable while the hub sent no
heartbeat. It now lights on a fresh heartbeat, slow-blinks when the board is
alive but the hub is answering nothing, and goes dark after three seconds of
silence.

## Layout on the bench

| Unit | Notes |
|---|---|
| Hub | ESP32-S3 DevKitC-1, N16R8. TFT on GPIO10–14, backlight on GPIO4 |
| Cot nodes | ESP32-C3 SuperMini × 2, INMP441 on GPIO4/5/6. **Node ids 1 and 2** |
| Wearable | ESP32-C3 SuperMini, SSD1306 OLED, BLE to the hub |

The node ids matter now: set them over the node's serial console with
`id 1` and `id 2`. A node left on a MAC-derived id outside 1..2 prints a
warning at boot, because the hub ignores every other number.

## Building

The hub is a PlatformIO / ESP-IDF project:

```bash
cd firmware/hub_infer
C:/Users/HP/.platformio/penv/Scripts/platformio.exe run
```

The vendored `esp-tflite-micro` and `esp-nn` components are not in the
repository (they are gitignored upstream and pinned in
`firmware/tools/fetch_deps.sh`); copy them into `firmware/hub_infer/components/`
before the first build.

The node and wearable sketches are Arduino projects:

```bash
python firmware/tools/install_sketches.py
arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/node/node_crynet
```

The FQBN matters: the generic `esp32:esp32:esp32c3` builds `Serial` as a
UART, and the sketches call `setTxTimeoutMs`, which only the USB-CDC
`HardwareSerial` has.

## Status

Built and compile-verified on all three targets: hub RAM 13.0 % / flash
63.6 %, node 75 % flash / 50 % RAM, wearable 51 % flash / 5 % RAM. The
redesigned panel was rendered to a mock (`research/out/two_node_display_mock.png`)
before flashing. The hardware pass is still owed: flash the hub and the two
cots, confirm the two cards and their network bars on the real panel, and
confirm the GPIO10 LED lights when the hub is answering.

`SYSTEM_UPDATE.md` holds the full history and the reasoning behind each
change.
