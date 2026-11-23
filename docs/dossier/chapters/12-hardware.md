# Chapter 12 — Hardware: wiring, bill of materials, power and the haptic drive

## The four boards and their pins

### Cot node — ESP32-C3 Pro Mini + INMP441

| INMP441 pin | Node pin | Note |
|---|---|---|
| VDD | **3V3** | 3.3 V only |
| GND | **GND** | |
| L/R | **GND** | selects the **left** channel — this is *channel select*, not gain |
| SCK | **GPIO4** | I²S bit clock |
| WS | **GPIO5** | I²S word select |
| SD | **GPIO6** | I²S data in |

No MCLK — the INMP441 generates its own clock from SCK.

**The old specification PDF assigns GPIO5/6/7 and a status LED on GPIO4. Do not wire it.** GPIO4 is
now the microphone's bit clock. GPIO9 is a boot-strapping pin. The C3's strapping pins are
**GPIO0/2/8/9** and the design avoids all of them.

Free pins since D-83: GPIO3 (was the battery ADC), GPIO7 (was the SOC LED), GPIO10 (was the link LED).
Nothing drives them.

### Microphone placement — a rule with a measurement behind it

The INMP441 is **fixed-gain**: no gain register, and its own output saturates before the node's 16-bit
window does. Measured on the bench:

- node 2 clipped at **peak 31,801 of 32,767** on ordinary room sound;
- a phone held **10 cm** from the microphone clipped the cry it was playing — that window scored
  **0.9805 instead of 0.9961**, and **the alert named the wrong cot for 42 seconds**.

There is no software cure, so the assembly rules are:

- Mount on the cot frame or a wall bracket, on a short stiff lead, **at least 30 cm** from where the
  baby's head will be, and out of the mattress's own sound path.
- **Never leave it loose on the mattress.** A soft surface damps the high frequencies the model reads,
  and the cot frame moves.
- Keep the acoustic opening unobstructed — an enclosure with a sound port, not a sealed box.

### Hub — ESP32-S3-DevKitC-1 N16R8 + 2.8" ILI9341

| TFT pin | Hub pin |
|---|---|
| CS | **GPIO10** |
| MOSI | **GPIO11** |
| SCK | **GPIO12** |
| DC | **GPIO13** |
| RESET | **GPIO14** |
| LED / backlight | **GPIO4** (LEDC PWM, 55 % default) |
| MISO | **not connected** — the panel is write-only |
| VCC / GND | 3V3 / GND |

SPI2 at 40 MHz. **Do not add the old document's 100 Ω backlight series resistor** and do not apply 5 V
to an unidentified TFT pin: module backlight circuits differ, and GPIO4 is a *control* signal, not an
instruction to drive an unknown backlight directly.

Free pins since D-83: GPIO1, GPIO2, GPIO17 (were BLE-status and SOC LEDs).

### Wearable — ESP32-C3 SuperMini + SSD1306 + coin ERM

| Function | Pin |
|---|---|
| OLED SDA | **GPIO5** |
| OLED SCL | **GPIO6** |
| Motor drive | **GPIO7** → 2.2 kΩ → BC547 base |

The haptic circuit, in full:

```
GPIO7 ──[2.2 kΩ]── B  BC547  C ── motor(−)
                    E ── GND
        100 kΩ from base to emitter (pulldown)

3V3 ──[22 Ω]── motor(+)
1N5819 across the motor, CATHODE UP (to motor +)
```

| Part | Value | Why this value |
|---|---|---|
| Base resistor | **2.2 kΩ** | (3.3 − 0.7) / 2200 ≈ **1.2 mA** of base current; a BC547A (hFE ≥ 110) saturates and sinks the motor's running current |
| Base–emitter pulldown | **100 kΩ** | the motor stays off while the C3 boots with GPIO7 floating |
| Stall cap, in the motor's **+ lead** | **22 Ω** | 3.3 / (37 + 22) ≈ **56 mA** stall, inside the BC547's 100 mA rating |
| Flyback diode | **1N5819**, cathode up | clamps the inductive kick when the transistor turns off |

**The 22 Ω is the value that is fitted**, not the 10 Ω an earlier list named. The owner had a 22 Ω and
no 10 Ω, and the bench proved the drive works with it on **2026-11-11**. It is also the safer value:
10 Ω would allow ≈70 mA. The cost is that the motor sees about **2.1 V** of the 3.3 V rail instead of
about 2.6 V, so **the buzz is softer**. That trade is recorded, not hidden.

If a different motor is fitted, **measure its stall current with a bench supply and a meter in series
before soldering — do not guess.** For anything lower-impedance than 37 Ω, fit a 2N2222A instead of
the BC547.

**Both the OLED and the motor run from the SuperMini's 3V3 output, not from 5 V.** The OLED's I²C
pull-ups ride on its VCC rail, so 5 V there would push 5 V levels into non-5 V-tolerant C3 GPIOs.

The DRV2605L breakout and the IRLML2502/AO3400 MOSFET with its 100 Ω / 10 kΩ gate resistors belonged to
earlier alternatives and are **not in this design**.

## The power chain, and its three rules (D-84)

Every unit is powered the same way:

```
cell → LX-LCBST-TC-001 boost to 5.1 V → VO+/VO− → switch → board's 5 V pin
     → the board's own linear regulator → 3.3 V
```

### The LX-LCBST-TC-001 pad map

Confirmed from the owner's photograph of the actual board:

| Pads | Printed | Meaning | Connection |
|---|---|---|---|
| B+ / B− (front and back) | 电池 | **battery** | the cell |
| VO+ / VO− (two pairs, back) | 输出 | **output** | boost output → the power switch |
| IN+ / IN− (back) | 输入 | input | alternate charging input, 4.2–6.5 V — **leave unconnected** |
| USB-C socket | — | charging | charging runs from here |

The switch goes on **VO+ → board 5 V**, never on the battery side, so B+/B− stay connected for
charging while the unit is off.

### Rule 1 — set the trimpot before any ESP32 is connected

Battery attached, meter on VO+/VO−, adjust to **≈ 5.1 V**. The module can ship set anywhere in its
**4.2–28 V** range; connecting a board before setting it **can destroy the board**. Re-check after the
first full charge cycle and occasionally thereafter.

### Rule 2 — never connect the boost and USB at the same time

The boost output goes straight to the board's 5 V pin, and that pin is hard-wired to the USB 5 V rail
through the board's own protection diode. With both connected the two supplies fight: 5.1 V and USB
5 V are the same net, and **current can be pushed back up the USB cable into the host** — a fault on
the laptop's side, not just the board's.

**To log while running on battery, use a USB cable with the 5 V (VBUS) wire cut.** The data lines still
carry the serial log and nothing can be pushed back into the host.

### Rule 3 — the linear regulator is the weak point, and it gets hot

A linear regulator passes *current*, not power. The difference between 5.1 V in and 3.3 V out is
burned as heat inside the board: **(5.1 − 3.3) × I**. At the C3's radio peaks of a few hundred mA that
is **0.5–0.7 W** in a package with no heat sink.

Two consequences:

- The cell must supply about **1.8× the 3.3 V load current** (D-82). A 100 mA load at 3.3 V means
  ≈160 mA from the cell.
- **If a unit resets when the radio transmits, check the LDO's heat and the cell's sag first — not the
  radio.**

**Runtime projection (not a measurement):** a 1000 mAh pouch ≈ **six hours**; a 3000 mAh 18650 rather
less than a day at the hub's heavier load. *No runtime has been measured on this system.*

The largest single lever on runtime is to **skip the 5 V → 3.3 V linear stage**: feed the board's
**3V3 pin** from a 3.3 V buck-boost, which removes the dissipation entirely and roughly doubles
runtime. It needs a separate module, because the LX-LCBST cannot be set below its 4.2 V minimum.
Recorded as an option to evaluate at the bench (D-82), **not** something to rewire before the current
build is finished.

## Cell choice (D-81), and why it differs per unit

| Unit | Cell | Reason |
|---|---|---|
| Nodes ×2 | **protected 18650 Li-ion, 3000 mAh** | a cot frame can puncture a pouch; the holder must survive a rail being knocked and the cell must not move |
| Hub | **protected 18650 Li-ion, 3000 mAh** | the heaviest load; the cell most worth sizing carefully |
| Wearable | **protected Li-Po pouch, 1000 mAh** | an 18650 is 18 × 65 mm and 48 g — it will not sit on a wrist. 500 mAh was too small for a night shift |

**Never LiFePO4 anywhere in this system.** The module charges to **4.2 V**; an LFP cell tops out at
3.65 V. Same chemistry otherwise: 3.7 V nominal, 4.2 V full.

The module's ~1 A charge current is **too high for the 1000 mAh pouch** — it must come down to
**~400–500 mA**. Confirm during bench validation.

And the invariant that survives every other change: **the battery voltage must never reach an ADC pin
directly.** The C3's IO is 3.3 V only and a full cell is 4.2 V.

## What was removed, and why (D-83)

The battery sense and **every status LED** were designed, costed, and then **withdrawn before they
were fitted**:

- the fixed **220 kΩ / 100 kΩ** divider (×3.2 ratio) and its **100 nF** filter;
- the node's divider read and its serial `battery` line;
- the node's link and SOC LEDs, the hub's BLE-status and SOC LEDs, the wearable's divider;
- the telemetry field — the payload went **34 → 32 bytes**.

The reasoning: the hub's panel already shows which cots are answering, and the battery figure was
always an estimate — the reading sagged **100–200 mV** under the boost and radio load, so a linear
voltage map would have been misleading anyway.

**The cost is stated plainly: nothing in the system will warn the caregiver that a cell is nearly
flat.** The cells are watched by eye.

If a readout is ever wanted back, the honest part is a **MAX17048** fuel gauge on I²C — model-based
SOC, no calibration table, indifferent to terminal sag under load — not a divider.

Do **not** buy the divider resistors, the divider capacitor or the indicator LEDs.

## Consolidated bill of materials

| Component | Total | Note |
|---|---:|---|
| ESP32-C3 development boards | **3** | 2 nodes + 1 wearable |
| INMP441 microphone breakouts | **2** | one per cot |
| ESP32-S3-DevKitC-1 with PSRAM (N16R8) | **1** | 16 MB flash, 8 MB PSRAM |
| 2.8" ILI9341 SPI TFT | **1** | 320 × 240 |
| 0.96" SSD1306 I²C OLED | **1** | 128 × 64 |
| BC547 | **1** | haptic switch |
| 1N5819 | **1** | flyback, cathode up |
| 22 Ω | **1** | stall cap, motor + lead |
| 2.2 kΩ | **1** | base |
| 100 kΩ | **1** | base–emitter pulldown |
| Coin ERM vibration motor | **1** | ~37 Ω; measure the stall current |
| LX-LCBST-TC-001 charger+boost | **3 + 1 candidate** | bench-validate **one** before buying the rest |
| Protected 18650, 3000 mAh | **3** | 2 nodes + hub |
| 18650 holders with leads | **3** | |
| Protected Li-Po pouch, 1000 mAh | **1** | wearable |
| On/off switches | **4** | ≥1 A, on VO+ |
| 100 µF electrolytic, ≥10 V | **3 + 1** | 5 V rail bulk |
| 100 nF ceramic (104) | up to **3** | optional decoupling; check what the modules already carry |
| 4.7 kΩ | up to **2** | I²C pull-ups **only if** the OLED module's are inadequate |
| Battery connector pairs | **4** | verify polarity physically, not by colour |
| Enclosures | 2 / 1 / 1 | node / hub / wearable + strap |
| Multimeter | **1** | verify supply, continuity, polarity and shorts before powering |

**The board swap is done, and it was verified live.** The two cots run **ESP32-C3 Pro Mini**
boards from the owner's stock; the original SuperMini prototype moved to the wearable. On
**2026-11-02** the same node firmware was flashed onto a Pro Mini *unchanged* — native USB
(`303A:1001`), 4 MB flash — and the bench gave link-up at once, **286/286 fragments** served, a
quiet room refused, and **two cry plays producing two alerts**. The two boards on the bench are
`90:DA:72:85:C5:44` (id 1, COM31) and `90:DA:72:87:CB:98` (id 2, COM37).

**Why no firmware changed:** the FQBN `esp32:esp32:weact_studio_esp32c3` selects the **ESP32-C3
chip** and its flash and USB settings, not one physical module. Both boards are the same chip with
the same 4 MB flash and the same native USB, so the image is identical. What differs is the
silkscreen: **confirm the pin labels against GPIO4/5/6 on the actual Pro Mini before soldering**,
because the electrical assignment does not change but the printed names may sit in different
places. This is also why one toolchain and one spare part still cover all three C3 units.

## The haptic drive — what is proven, and the one thing that is not

The motor **works**. It is worth being precise about how that was established, because "the buzzer
buzzes" is the kind of claim a defence gets pushed on.

**Proof 1 — the electrical path alone.** `firmware/wearable/haptic_test/haptic_test.ino` drives GPIO7
with the same 250 ms pulse train the alert path uses and nothing else: no BLE, no OLED, no hub. One
command flashes it:

```bash
python firmware/tools/flash_node.py --port COM30 --sketch haptic_test
```

The motor was seen to toggle. That isolates the BC547, the 2.2 kΩ base resistor, the 100 kΩ pulldown,
the 1N5819, the 22 Ω cap and the motor from every line of application code. The sketch stays in the
repository with its restore command in the header, so a fresh board can be proved without hunting for
the procedure.

**Proof 2 — the whole chain, on 2026-11-06.** Three alert cycles in a row came through complete:
`ALERT cot 1 type 1 conf 100%` on the wrist, the haptic fired, `clear` returned `type 2`. The wearable
also survived a hub reset mid-link and resubscribed to both characteristics.

**Proof 3 — the fitted cap value, on 2026-11-11.** The bench proved the drive works with **22 Ω** in
the motor's positive lead, which is the value that is actually soldered (D-85 revises D-77's 10 Ω).

**Proof 4, and it is only half a proof — the cell.** The wearable **has run on its Li-Po pouch**: it
was on the pouch, not USB, for the third round of the 2026-11-20 session, and it kept working. But
**the buzz went missing in that round.** The firmware is exonerated — D-86 touches no motor line, so
the drive is byte-identical to the build proved on 2026-11-11 — which makes a **sagging 3.3 V rail** a
live candidate: the OLED, the C3's radio peaks and the motor all share the board's one linear
regulator. A coin motor's inrush is the largest transient in the system, and a pouch through a boost
and a linear regulator is a stiffer supply than a USB port. That is O-1d, and the measurement is short:

| Reading | What it settles |
|---|---|
| Multimeter **across the motor during an alert** | voltage present and no motion → the motor or its joint; no voltage → the drive path |
| **Pouch voltage during a buzz** | a collapse there implicates the supply, not the switch |
| Cell voltage at the board's 5 V pin under a radio peak | whether the LDO is dropping out (Rule 3) |

**One inconsistency in the record, stated rather than smoothed over.** The bill of materials describes
the fitted actuator as a *3 V ERM coin motor, 85 mA*, while the stall arithmetic in D-85 assumes a
**37 Ω** coil — and 3.3 V across 37 Ω is 89 mA, which is a *stall* figure, not a running one. The two
numbers cannot both be the motor's running current. The practical consequence is that the 56 mA
"stall" figure is a calculation from an assumed coil resistance, not a measurement of the motor on the
bench. **Measure the actual stall current with a bench supply and a meter in series** before relying
on the headroom argument; if it exceeds the BC547's 100 mA rating, fit a 2N2222A.

## Safety

This is an **academic prototype**, not a certified medical device and not a substitute for an adult
caregiver. Detection, range, radio delivery, battery life and alarms have not been established to any
safety-critical standard. Keep electronics, cords, batteries and small parts out of an infant's reach.