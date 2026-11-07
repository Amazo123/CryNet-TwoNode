# CryNet — USB Test and Complete-System Wiring Guide

**Revision:** 7 November 2026. Read alongside `HARDWARE_COMPONENTS.md`.

> **Important:** The node + hub signal wiring in section 2 reflects the working prototype. The wearable and battery power are **not implemented or verified**. There are **no status LEDs anywhere in the system** (D-83): the node's connection LED, the node's SOC LED, the hub's BLE-status LED and the hub's SOC LED have all been removed, and the battery sense divider has been removed with them. Their exact part-to-part power wiring and GPIO choices cannot safely be finalised until the actual board and charger modules, cell and motor are selected. Section 3 is a proposed connection architecture, not permission to wire an unspecified lithium charger. This academic prototype is not a certified infant-monitoring device and must not replace supervision. Keep cables, cells, modules and small parts out of reach of the infant.

## 1. System picture

```text
  Cot 1: INMP441 → C3  ── ESP-NOW ──┐
  Cot 2: INMP441 → C3  ── ESP-NOW ──┼→ ESP32-S3 hub → 2.8-inch TFT
                                             │
                                             └── BLE → phone (tested)
                                                  or → C3 wearable (on the bench)
                                                           ├→ SSD1306 OLED
                                                           └→ BC547 → haptic motor
```

No audio or signal wires connect the cot nodes to the hub: the link is wireless. Each assembly has its own local power and ground. The node, hub and wearable do not need grounds connected to each other.

> **This is the two-cot system.** The three-node version is the sibling repository `fp-2`. The wearable's haptic is a **BC547 low-side switch**, not the DRV2605L the older planning documents describe (D-77).

## 2. Wiring A — USB-powered bench test

**Before wiring:** disconnect power; identify actual board/module pin labels; use a multimeter to check for shorts and verify the display module voltage. These are board pin labels, not physical header positions. Do not assume every breakout uses the same pin order.

### 2.1 Cot node: ESP32-C3 + INMP441

Repeat the same connections for each node. **Multi-node operation has been verified** — on 2026-11-04 three nodes, the hub and the wearable ran together on one laptop for twenty-five minutes with **no brownout, no reset and no false alarm** (node 1's own counters: 6 385 frames sent, 0 lost, 0 times the radio had no room). *That session ran three cots; this repository's build is two.*

| From | To | Note |
|---|---|---|
| C3 **3V3** | INMP441 **VDD / 3V3** | 3.3 V only; not USB 5 V. |
| C3 **GND** | INMP441 **GND** | Common local ground. |
| C3 **GND** | INMP441 **L/R** | Select left I²S channel. |
| C3 **GPIO4** | INMP441 **SCK** | I²S bit clock. |
| C3 **GPIO5** | INMP441 **WS** | I²S word select. |
| C3 **GPIO6** | INMP441 **SD** | Microphone data to C3. |
| Regulated USB supply or computer | C3 **USB connector** | Use a compatible data cable for flashing/serial. |
| Optional 100 nF capacitor | Between mic **VDD and GND** | As close as practical to microphone; check existing breakout decoupling. Ceramic is non-polar. |

```text
 C3 3V3 ───────────── VDD   INMP441
 C3 GND ─────┬─────── GND
             └─────── L/R
 C3 GPIO4 ─────────── SCK
 C3 GPIO5 ─────────── WS
 C3 GPIO6 ─────────── SD
 USB source ───────── C3 USB socket
```

The old PDF's GPIO5/6/7 microphone assignment does **not** match the current firmware. C3 GPIO4 is already used by SCK and must not also be connected to the old red status LED.

**Where the microphone goes — a placement rule, measured.** The INMP441 is a **fixed-gain** part: it has no gain register and its own output saturates before the node's 16-bit window ever does, so a sound close enough to it arrives flat-topped and the window cannot be trusted. Measured on the bench: node 2 clipped at peak 31 801 of 32 767 on ordinary room sound, and a phone held 10 cm from the microphone clipped the cry it was playing — that window scored 0.9805 instead of 0.9961, and the alert named the wrong cot for 42 seconds. There is no software cure, so the rules for the finished assembly are:

- **Keep the microphone out of the cot's near field.** Mount it on the cot frame or a wall bracket, on a short stiff lead, at least **30 cm** from where the baby's head will be, and out of the mattress's own sound path.
- **Do not point it at a speaker, a radiator or a window.** A reflective surface doubles the level at the mic.
- **Never leave it loose on the mattress.** A soft surface damps the high frequencies the model reads, and the cot frame moves.
- The hub now **refuses a clipped window and says so in its log** (`the window is CLIPPED`), so a bad mount is visible rather than silent. Watch for that line in the hub's log after the first night of use; it is the fastest way to find a microphone that is too close to the sound.

### 2.2 Hub: ESP32-S3 + 2.8-inch ILI9341

The project log records the following signal and 3.3 V connections on the existing display. Match the actual module's labels and confirm its supply and backlight circuit before copying it to a different TFT.

| From S3 | To display | Note |
|---|---|---|
| **3V3** | **VCC** | Recorded working connection for the existing module; do not assume another module has identical power requirements. |
| **GND** | **GND** | Local common ground. |
| **GPIO10** | **CS** | Chip select. |
| **GPIO11** | **MOSI / SDI** | SPI data to TFT. |
| **GPIO12** | **SCK / CLK** | SPI clock. |
| **GPIO13** | **DC / D-C** | Data/command. |
| **GPIO14** | **RST / RESET** | Display reset. |
| **GPIO4** | **BL / LED control** | Recorded on the existing board. Check the module's backlight drive current and circuit; do not drive an unknown bare LED backlight from a GPIO. |
| Not connected | **MISO / SDO** | The current driver does not read TFT data. |
| Regulated USB supply or computer | S3 **USB connector** | Match the actual connector used for programming. |

No external 100 Ω backlight resistor should be added blindly; use the specific module's circuit. Touchscreen and SD-card pins, if present, are not used by the current display firmware. The S3's BOOT button is used by the existing UI; it is already on the development board.

### 2.3 USB wearable bench wiring — proposed, not yet built

> **SUPERSEDED — this section describes the DRV2605L option, which is not what was built.** The wearable that is on the bench drives a **real haptic motor through a discrete BC547 low-side switch** (D-77), and the firmware exists and has been verified end to end. **The BC547 wiring is in §5.3 — build from there, not from the table below.** The DRV2605L is retained below only as the record of the alternative that was considered, so the two do not get confused again.

The connection list for the **DRV2605L alternative** — not a tested pin map, and not the design in use:

| From | To | Condition |
|---|---|---|
| C3 **GND** | OLED **GND** and DRV2605L **GND** | Common local ground. |
| C3 **3V3** | OLED **VCC** | Only if the specific OLED breakout accepts 3.3 V. |
| Appropriate regulated supply | DRV2605L breakout **VIN/VDD** | Follow the actual breakout's voltage requirements; do not assume its VIN and logic pins are identical to the IC pins. |
| Selected C3 I²C SDA | OLED **SDA** and driver **SDA** | Bus pull-ups must go to a safe 3.3 V logic rail. Check existing pull-ups before adding any. |
| Selected C3 I²C SCL | OLED **SCL** and driver **SCL** | Same. Verify address compatibility. |
| Driver **OUT+ / OUT−** | Compatible motor's two terminals | Use the specific breakout's labels and motor requirements. Do not connect either motor lead to 3V3 or ground as in the old MOSFET circuit. |
| USB source | C3 USB socket | Supply capability and driver power arrangement must be checked. |

Use the selected breakout's documentation for EN, I/O supply, power, pull-ups and any other control pins; these vary by board. DRV2605L uses an H-bridge, unlike the old low-side MOSFET design. No separate MOSFET or old motor flyback-diode wiring is used for this driver. See [TI DRV2605L datasheet](https://www.ti.com/lit/ds/symlink/drv2605l.pdf).

## 3. Wiring B — proposed battery-powered complete system

### 3.1 Connections that remain the same

For each of the **two** nodes, retain **all six microphone connections** in section 2.1. For the hub, retain the TFT signal and ground connections in section 2.2. For the wearable, use only a finalised and tested version of section 2.3. Only the **power source** changes; never join the four batteries together. The **battery sensing and the status LEDs are gone** (D-83) — there is nothing on B+/B− but the cell, and no indicator of any kind on any unit.

### 3.2 Power architecture for each separate unit

```text
 USB charging input
        │
        ▼
 [charger + properly designed power-path/load sharing] ←→ [protected 1-cell battery]
        │ regulated/selected system output, as the module specifies
        ▼
 [suitable regulated converter, if needed] → [power switch as designed]
        │                                      │
        ├── appropriate board power input      └── local loads, if designed
        └── local ground / return
```

**Concrete pad names, from the photographed board (§6):** the charging input is the module's **USB-C socket**; the battery lands on **B+/B−** (printed 电池); the load chain starts at **VO+ / VO−** (printed 输出). IN+/IN− (printed 输入) stay unconnected.

For each of the **two** nodes and the hub, the BOM proposes a protected 1-cell battery and a 5 V boost if the selected board uses its 5 V input. The wearable's suitable voltage/converter remains undecided. A lithium cell can be **4.2 V fully charged**, so do not connect it to a 3.3 V rail or GPIO; do not apply 5 V to 3V3. The converter's output must remain within the board input specifications under measured peak loads and low cell voltage. A 100 µF bulk capacitor is a **candidate**, not an unconditional connection: confirm location, voltage rating and stability requirements in the actual converter datasheet, then connect + to the intended rail and − to local GND only if appropriate. Do not connect bench USB and a battery supply simultaneously without a designed, verified power path preventing backfeed.

**Cell selection (D-81):** the nodes and the hub take a **protected 18650** (3.7 V nominal, 4.2 V full, 3000 mAh) in a holder; the wearable takes a **1000 mAh Li-Po pouch**. The two are opposite choices for opposite reasons — a node sits on a cot frame within a baby's reach and needs a cell that cannot be punctured, while an 18650 is 18 × 65 mm and 48 g and cannot go on a wrist. **Never an LiFePO4 cell anywhere**: the module charges to 4.2 V and an LFP cell tops out at 3.65 V.

### 3.3 No battery sensing, and no status LEDs

**This section used to describe a divider and two LEDs. It does not any more (D-83).**

There is **no battery sense divider on any unit** — not on the nodes, not on the hub, not on the wearable. B+ and B− carry the cell and nothing else. There is **no 220 kΩ, no 100 kΩ and no 100 nF** in the system, and there is **no LED on any unit**: no connection LED, no SOC LED, no BLE-status LED. The parts that were on the bill of materials for them should not be bought and must not be fitted.

The **battery power itself is unchanged**: the cells, the LX-LCBST modules, the switches and the boost converters are exactly as planned in §3.2, §5.1, §5.2 and §5.3. What has been removed is only the *measurement* of the cell and the *indication* of it.

Why: the hub's panel already shows which cots are answering, and it shows it better than a second, slower LED on the cot could. The battery reading was always an estimate — a resting-voltage curve printed with a tilde — and the owner does not want it. The cost of removing it is that **nothing in the system will warn the caregiver that a cell is nearly flat**; the charge-prompt idea (§7) is gone with it.

**For the record, the divider that was designed and then withdrawn.** It was a fixed pair — B+ → 220 kΩ → sense node; sense node → 100 kΩ ∥ 100 nF → B−; sense node → GPIO3 (ADC1_CH3) on the nodes and the wearable, GPIO1 (ADC1_CH0) on the hub — a ratio of ×3.2, so 4.2 V on the cell read as ≈ 1.31 V at the pin, drawing ≈ 13 µA continuously. It was a fixed pair and **not** a potentiometer, on purpose (D-81): a **two-terminal** pot cannot divide at all, since the ADC pin's only path to ground is its own high-impedance input, so the pin still sits near 4.2 V — past the C3 IO's 3.6 V absolute maximum. A **three-terminal** pot used as a real divider does work, and the firmware does not need to read the wiper; what it costs is a **per-unit measured ratio**, **silent drift** with heat, vibration and wear, and **magnitude** — the SOC curve moved 100 mV = 20 percentage points around 3.8 V, so 1 % of ratio error was already ~10 points of SOC error, against a pot's 1–5 %. Two 1 % resistors gave a ratio the firmware knew exactly on every unit with no per-unit step. All of that was sound; it was simply not wanted. The reasoning is kept in `DECISIONS.md` (D-81, D-83) and is not repeated here.

### 3.4 Wearable battery and haptics

The wearable's power follows the same LX-LCBST pattern as the nodes (§5.3): VO+ → switch → SuperMini 5V pin; the OLED from the SuperMini's 3V3 output so the I²C bus stays at 3.3 V; the motor driven by the **BC547 low-side switch on GPIO7** (D-77), not by the DRV2605L the older documents describe. The proposed 1,000 mAh **Li-Po pouch** cell only buys runtime if the module's measured charge current suits it — at ~1 A it does not, so the charge current must come down to ~400–500 mA (D-81). The IRLML2502 and its gate resistors/diode belong to the alternative MOSFET drive and are **not wired into the BC547 path**.

## 4. Checks before power-up

1. With power disconnected, check continuity and make sure no 3.3 V or 5 V rail is shorted to ground. Inspect vero-board copper tracks, intentional cuts and solder bridges.
2. Confirm the exact module labels, voltage ratings, polarity, cell protection and regulator settings. Check converter output with a meter **before** connecting its load.
3. For initial testing use a current-limited bench supply where possible. Test one assembly at a time; avoid unattended charging.
4. Test the known USB node-to-hub setup first. The wearable and additional nodes require their own implementation and verification.
5. Before using battery and USB together, verify the actual charger/load-sharing and backfeed behaviour. Secure cells against puncture/shorts and use appropriate enclosures.

## 5. Proposed safe GPIO and component plan

This is the proposed design for the next firmware/hardware branch. It deliberately avoids the documented boot-strapping pins and the pins already used by the microphone, TFT or native USB. It is a **pin plan**, not yet flashed or measured.

### 5.1 Cot node — two identical units

| Function | GPIO / connection | Components |
|---|---|---|
| I²S BCLK | GPIO4 | Existing INMP441 SCK |
| I²S WS | GPIO5 | Existing INMP441 WS |
| I²S data | GPIO6 | Existing INMP441 SD |
| Battery sense | **none** | The divider is removed (D-83): no 220 kΩ, no 100 kΩ, no 100 nF, and nothing on GPIO3. B+/B− are the pads printed 电池 (battery) on the board photo, and they carry the cell only. |
| Status LEDs | **none** | The GPIO10 connection LED and the GPIO7 SOC LED are removed (D-83). GPIO7 and GPIO10 are free. |
| Power switch | **VO+ → switch → C3 5V pin** | SPST switch rated ≥1 A. VO+ / VO− are the pads printed 输出 (output). B+/B− stay connected for charging while the node is off. Do not switch the battery side. |

**There is no battery reading on this unit (D-83), and no LED of any kind.** The divider and its 100 nF are not fitted; the ADC pin is not read; the telemetry carries no cell voltage; and the hub's panel carries no battery text. GPIO3, GPIO7 and GPIO10 are free.

What the node *does* still do is the part that mattered for the link, and it is unchanged: it sends a heartbeat to the hub and the hub answers with a matching ACK.

```text
node → hub: HEARTBEAT(node_id, counter, CRC)
hub → node: HEARTBEAT_ACK(node_id, counter, CRC)
node: connection_ok = a matching hub ACK received within the last 3 seconds
```

The heartbeat and its ACK stay, because they are how the node knows the hub is there. What has gone is the *output* — the LED that used to show the answer. The node now prints the same fact on its serial console (`status`), and the hub shows it on the panel, which is where the caregiver looks. The hub must still track the last heartbeat/telemetry time; an ESP-NOW send callback alone is not application delivery confirmation.

### 5.2 Hub — one unit

The current TFT assignments remain fixed: GPIO10 CS, GPIO11 MOSI, GPIO12 SCK, GPIO13 DC, GPIO14 RST and GPIO4 backlight. Proposed additions avoid those pins and the S3 strapping pins:

| Function | GPIO / connection | Components |
|---|---|---|
| Battery sense | **none** | The divider is removed (D-83): no 220 kΩ, no 100 kΩ, no 100 nF, and nothing on GPIO1. |
| Status LEDs | **none** | The GPIO2 BLE-status LED and the GPIO17 SOC LED are removed (D-83). GPIO2 and GPIO17 are free. |
| Power switch | **VO+ → switch → S3 5V pin** | Battery remains on module B+/B− while the hub is off. Verify the DevKitC input and converter output under TFT/radio load; the hub's peak draw is the heaviest of the five units and is not yet measured. |

The hub TFT keeps its working assignments (GPIO4 backlight, GPIO10–14 signals) and the hub has **no battery sense and no status LED** (D-83). Avoid GPIO0/3/45/46 (S3 strapping) and GPIO35–37 (Octal PSRAM bus on the N16R8). GPIO1, GPIO2 and GPIO17 are free.

### 5.3 Wearable — one unit

The wearable uses the same C3 board class, but the final board must be checked against its pin labels. **This unit is built and working on the bench** — the OLED, the BLE client and the haptic motor are all in place (D-76, D-77). What it does not have yet is its battery, and the rows below are what remains to be built:

| Function | GPIO / connection | Components |
|---|---|---|
| OLED SDA | **GPIO5** | Shared I²C SDA; add no external pull-up until the OLED module's own pull-ups are checked |
| OLED SCL | **GPIO6** | Shared I²C SCL; pull-ups, if needed, to 3.3 V only |
| Haptic output | **GPIO7 → 2.2 kΩ → BC547 base** | The low-side switch that is actually fitted: GPIO7 → 2.2 kΩ → base, 100 kΩ base-emitter pulldown, motor in the collector leg, 1N5819 across the motor with the cathode up, emitter → GND, 10 Ω in the motor's + lead. **No IRLML2502 and no DRV2605L in this path** (D-77). |
| Power switch | **VO+ → switch → C3 5V pin** | Same pattern as the node: disconnects the device, battery stays on B+/B− for charging. |
| **Status LEDs** | **none** | The wearable has **no status LEDs** — and now it has no battery sense either (D-76, D-83). An earlier revision gave it a blue link LED on GPIO1 and a red SOC LED on GPIO4; neither ever had firmware, and the OLED already carries LINK/SCAN. The OLED stays the only display on the wrist, and it says nothing about the cell. |

**Wearable power:** the wearable uses the same LX-LCBST pattern as the node: VO+ → switch → the SuperMini's 5V pin, VO− → GND. The OLED is powered from the SuperMini's **3V3 output pin**. Check the board's 3.3 V regulator current budget before final assembly: C3 radio peaks (hundreds of mA) + OLED (~25 mA) + motor bursts (~85 mA) all share it; if it sags or resets during vibration, the motor supply design gets revisited on a branch. ESP32-C3 strapping pins are GPIO0/2/8/9 — the plan above avoids all of them.

**Runtime (D-82):** the chain **cell → boost to 5.1 V → the SuperMini's 5 V pin → its onboard linear regulator → 3.3 V** means the cell supplies roughly **1.8× the 3.3 V load current**, because a linear regulator passes current rather than power. On a 1000 mAh pouch that projects to **about six hours** — a projection, not a measurement. Feeding the SuperMini's **3V3 pin** from a 3.3 V buck-boost would roughly double it; the OLED's always-on ~25 mA is the other lever. The cell is a **1000 mAh Li-Po pouch** (D-81) and the module's ~1 A charger must be reduced to ~400–500 mA for it.

## 6. LX-LCBST-TC-001: decision and exact conditional wiring

**Pad map confirmed from the user's front-and-back photograph (2026-11-02):**

| Pad group | Printed label | Meaning (Chinese on silk) | Use |
|---|---|---|---|
| B+ / B− (front) / B+ / B− (back) | 电池 | **battery** | The cell connects here — an 18650 on a node or the hub, a Li-Po pouch on the wearable (D-81) |
| VO+ / VO− (two pairs, back) | 输出 | **output** | Boost output — feeds the power switch |
| IN+ / IN− (back) | 输入 | **input** | Alternate charging input, 4.2–6.5 V; leave **unconnected** (charging runs from USB-C) |
| Front − / + pair (unlabelled) | — | ambiguous | Most likely a paralleled output tap; **verify with a meter before use** — compare it against VO+/VO− and B+/B− with the battery installed |
| Trimpot (front, beside the charger IC) | — | — | Sets the boost output, 4.2–28 V |

No **T** pad is visible on this board — the family listing's T-shorting instructions belong to other variants and **do not apply here**; do not short anything.

```text
cell +        → B+   (pad printed 电池)   [18650 on nodes/hub, Li-Po pouch on wearable]
cell −        → B−
USB-C socket  → charging input (nothing wired to IN+/IN−)
VO+ → power switch → ESP32 board 5V pin
VO− → ESP32 board GND pin
```

**Set the trimpot before any ESP32 is connected:** battery attached, meter on VO+/VO−, adjust to ≈ 5.1 V. The module can ship set anywhere in its 4.2–28 V range; connecting a board before setting it can destroy the board. Re-check after the first full charge cycle and occasionally thereafter.

Two characteristics remain unknown and must come from the bench validation: the **actual charge current** (the charger's program resistor is too small to read in the photo; if it programmes near 1 A, the wearable's 1,000 mAh pouch needs it reduced to ~400–500 mA, and a node's 3000 mAh 18650 is fine at 1 A), and the boost converter's **quiescent drain while the unit is switched off** (the switch disconnects the load, not the converter — if off-state drain proves significant, the switch moves or the module changes). Note also that B− and VO− connect through the module's protection FET: in normal operation they are effectively the same ground, but at deep-discharge cutoff the battery disconnects and the unit dies — which, with no battery readout anywhere (D-83), is exactly the moment the caregiver will notice it. Take the unit off the cot when the cell is nearly flat rather than waiting for that.

### Required one-board validation before buying four more

1. ~~Identify every terminal~~ — done from the photograph (§6 pad map). Remaining unknowns: actual charge current, boost quiescent drain, protection thresholds, the unlabelled front −/+ pair.
2. With no ESP32 attached, measure boost output range, no-load voltage, output under a dummy load and startup behaviour at full and partly discharged cell voltage.
3. Measure charging current and confirm termination at 4.2 V; verify whether the protection circuit disconnects at low voltage and short/overcurrent without deliberately abusing the cell.
4. Confirm that switch OFF disconnects the converter/load but leaves charging connected, and measure switch-off battery drain.
5. Run one node from it: compare reboot count, burst completion, radio range and microphone noise with the known USB baseline.
6. Only then decide whether it is suitable for the hub and whether a separate 3.3 V regulator is needed for the wearable.

## 7. There is no battery readout (D-83)

**This section used to describe the SOC display and the charge prompt. Both are gone.**

There is no battery text on the hub's panel, no battery readout on the wearable's OLED, and no battery LED anywhere. The hub's cot card shows the cot's name, whether it is answering, the RMS bar and its number, the trigger notch, the confidence, and the radio link — and nothing about the cell. The node's `status` command no longer prints a cell voltage.

**The consequence is worth stating plainly: nothing in the system will tell the caregiver that a cell is nearly flat.** That was the whole point of the feature, and it is the thing being given up. The cells still need watching by eye: charge each unit before it is put back on a cot, and take the unit off the cot when the cell is nearly flat rather than waiting for it to protect itself.

**What was removed, for the record.** The plan was a fixed 220 kΩ / 100 kΩ divider (ratio ×3.2) with a 100 nF across the bottom leg, read on ADC1 and averaged over sixteen samples every four seconds, with a trust gate that refused a reading until three landed in the expected window, and a banded result on the panel: `BAT ~80 %`, `BAT LOW`, `BAT CRIT`, the band moving on hysteresis so one radio-load dip could not flash a warning at the caregiver. The map from voltage to percent was a curve, not a line — **4.20 V = 100 %, 4.05 ≈ 90 %, 3.90 ≈ 65 %, 3.80 ≈ 40 %, 3.70 ≈ 20 %, 3.55 ≈ 8 %, 3.45 ≈ 3 %, 3.30 ≈ 0 %** — because a lithium cell is not linear between 3.0 V and 4.2 V, and a straight line would call a genuinely quarter-full cell "58 %". The bottom was anchored at 3.3 V, not 3.0 V, because 3.0 V is where a protected cell's protection circuit cuts out: that is end-of-life, not "empty".

**If it is ever wanted back**, the honest version is not the divider but a real fuel gauge — a **MAX17048** on I²C (the hub and the wearable have a spare bus; the node's microphone occupies I²S, so a node would need the ADC divider or a part on another interface). A gauge reports charge in the cell's own coulombs and does not care how much the terminal sags under load, which was the divider's other weakness. The reasoning is in `DECISIONS.md` (D-81 for the divider, D-83 for the withdrawal).

## 8. What is still required before this counts as verified

The LX-LCBST pad map is now known from the photograph; what remains is bench truth. Build **one** node power assembly exactly as in §5.1/§6, measure charge current, set the trimpot to 5.1 V, confirm switch-off behaviour and off-state drain, then run the working node firmware from it and compare with the USB baseline (reboots, bursts, mic noise). In parallel the user plans a **board swap**: ESP32-C3 Pro Mini boards for the two nodes and the existing SuperMini for the wearable — the firmware targets the chip, not the board, but each Pro Mini must prove native USB, 4 MB flash and the needed pins (GPIO4/5/6) before the swap counts; re-verify one node end to end on a branch. The battery sense and the status LEDs have been removed rather than built (D-83), so the pins they would have used — GPIO3, GPIO7, GPIO10 on the node, GPIO1, GPIO2, GPIO17 on the hub — are free and need no verification. No merge into `main` without the user's decision.

**Evidence:** `firmware/node/node_crynet/node_crynet.ino` (GPIO4/5/6); `firmware/hub_infer/components/hub_display/hub_display.c` (TFT pins); `SYSTEM_UPDATE.md` (working display wiring and hardware tests); `HARDWARE_COMPONENTS.md` (proposed BOM).
