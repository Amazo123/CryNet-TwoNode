# Chapter 13 — The hub panel: driver, UI, and five debugging rounds

## Why a panel at all

The wearable is the alerting device, but it is one device on one wrist. The panel is the system's
**shared truth**: which cots are linked, which are crying, whether the caregiver's device is attached,
and whether an alert actually got delivered. It is also the only place the system shows anything at
all, since D-83 removed every LED.

Hardware: 2.8" ILI9341, 320 × 240, SPI2 at 40 MHz, write-only (MISO unconnected).

## The driver

`ili9341.c` (413 lines) is a hand-written driver, not a library. Three reasons: the panel needed a
specific rotation and colour order, the framebuffer had to live in PSRAM, and the backlight needed
LEDC PWM control. A generic library would have fought all three.

- **Framebuffer:** 320 × 240 × 2 = **153,600 bytes of RGB565 in PSRAM**. The whole frame is composed in
  memory and pushed in one SPI transaction, so there is no tearing and no partial state on the glass.
- **Rotation:** `ROTATION_LANDSCAPE 2`.
- **Backlight:** LEDC PWM, `BACKLIGHT_DEFAULT 55` %, via `hub_display_set_brightness()`.
- **BOOT button** (`PIN_BUTTON 0`, active low) cycles **three faces**: `s_face = (s_face + 1) % 3` —
  the dashboard, the help page, and the colour check. The colour check is a grid of the palette's
  swatches, so the panel's own colours can be judged **without a camera in the loop**; the help page
  explains what every number on a cot card means.

## Five rounds of debugging, and what each one taught

This sequence is worth telling in order, because each fault was invisible until the previous one was
fixed.

### Round 1 — static noise

The first flash produced **static**. Three bugs in the driver, all found by reading the ILI9341
command sequence against the datasheet:

1. the address window was written **little-endian** (the panel wants big-endian);
2. **`CASET` was sent twice** where the second should have been `PASET`;
3. **CS was released between a command and its parameters** — the panel treats each CS assertion as a
   new transaction, so the parameters were interpreted as commands.

### Round 2 — a quarter turn out

The image appeared but rotated. This panel is **landscape-first** and wants **`MADCTL_MY`**, not the
`MADCTL_MV` the legacy firmware used. A legacy setting is not evidence about a different module.

### Round 3 — hearts and diamonds instead of letters

The new UI drew, but the text was symbols. **The font generator was reading the table 32 characters
out of place** — an ASCII offset bug in `research/build_font.py`, not in the driver. The glyphs were
correct; the indexing was not.

### Round 4 — red and blue exchanged

The first photograph of the real glass confirmed the layout, text and orientation were all correct:
`AMAZING'S CRYNET`, `S3 HUB`, `RADIO`, `PHONE`, `LISTENING`, `COT 1 / ONLINE`, `COT 2`,
`2 cots linked`, `up 0:39`.

It also exposed a colour fault: **every colour had red and blue exchanged.** The teal accent came out
olive; the amber `PHONE` pill came out blue. Cause: the driver set the panel's **`MADCTL_BGR`** bit
while the framebuffer packs standard **RGB565**. Fixed, flashed and logged (`madctl 0x80`). The second
photograph confirmed it: the `PHONE` square warm orange, the accent underline teal-green, the `RADIO`
square cyan-green — the same elements that had been blue, pink and olive.

### Round 5 — the panel lifts the dark end

The second photograph also showed a **glare**: the panel was brighter than the room, the camera
clipped it, and the white balance drifted so the whole screen read as saturated blue. The panel's side
of that was fixed with the PWM backlight at 55 %.

Then the **colour check** — the swatch grid, judged by eye rather than through a camera — proved the
hues were right and found the real fault: `BLACK` black, `WHITE` white, `TEAL` teal, `GREEN` green,
`AMBER` amber, `ROSE` rose — but the old navy background came back as a **saturated blue**. **This
panel lifts the dark end, and the blue channel hardest**: the amber's requested blue of **36 measured
back at 145**.

That is a property of the glass, not a bug in the code, and it cannot be fixed by correcting a colour
constant. The fix was to **move the whole neutral family down the ramp** until the lifted values land
where they should.

## The palette, and how it was chosen

The neutrals were moved one step darker **on the user's own pick**: shown the ramp, they chose its
**third step, `(4,8,8)`**, as the teal the screen should be, and the whole neutral family moved down
one step with it. Then a second pass from the chair (D-59) dropped the background another step,
`(4,8,8)` → `(2,4,4)`, because the cards still read as the same colour as the ground on the glass.

| Name | RGB | Use |
|---|---|---|
| `C_BG` | **(2, 4, 4)** | background |
| `C_SURFACE` | (7, 15, 16) | card fill |
| `C_SURFACE_HI` | (12, 26, 28) | raised surface |
| `C_HEADER` | **(7, 20, 15)** | header strip |
| `C_BORDER` | (78, 116, 112) | card outline |
| `C_TEXT` | (228, 240, 236) | primary text |
| `C_DIM` | (122, 150, 146) | secondary text |
| `C_ACCENT` | **(45, 212, 191)** | teal accent |
| `C_ACCENT_DIM` | (22, 124, 112) | inactive accent |
| `C_BLUE` | (96, 165, 250) | radio indicator |
| `C_GREEN` | (52, 211, 153) | online |
| `C_AMBER` | (251, 191, 36) | phone / attention |
| `C_ALERT` | (251, 113, 133) | rose, crying |

**The header strip got its own colour, `(7,20,15)`, with green pushed five steps above blue**, because
the backlight's LEDs run along the **top** of the glass and lift that strip blue. A header painted the
same colour as the cards photographed blue while the cards photographed teal. That is a physical
property of the module discovered by looking at it, and the palette compensates for it deliberately.

## Layout — two cards, one reading per row

| Element | Geometry |
|---|---|
| Header | `HEADER_H 30` |
| Banner | x 10, y 40, w 300, h 44 |
| Cot cards | `CARD_X 10`, `CARD_W 300`, **`CARD_H 64`**, `CARD_Y0 88`, **`CARD_STEP 70`** |
| Footer | `FOOT_Y 230` |
| Splash | **`SPLASH_MS 5600`** = `BOOT_MS 2400` + title + `FADE_MS 600`, `SPLASH_TICK 100` |

**Two** full-width cards, and the arithmetic is deliberate: `88 + 2 × 70` puts the second card's
bottom edge at **222**, leaving the footer at 230 clear. The cards used to be 44 tall on a 47 pitch,
which fitted three of them and put three readings on one line. With two cots there is vertical room
to give each reading its own row, and that is what the redesign spends it on:

One cot card, read row by row:

| Row | What it shows | Example |
|---|---|---|
| Top | the cot's name and its state | `COT 1` &nbsp;&nbsp;&nbsp; `ONLINE` |
| Middle | the **level bar** with the **notch** where that cot's trigger sits, and the RMS beside it | `RMS 0.012` |
| Bottom | the **signal bar** and the RSSI of the link to that cot | `LINK -58 dBm` |

The RMS used to share its line with the link, which put two readings on one row and made the card
hard to read in a dark room. **There is no battery line** — the cots do not measure their cells (D-83).

### The level bar, its scale, and its notch

`LEVEL_BAR_FULL` is **0.25**, not 1.0, and the scale is **square-rooted**:

```c
const float frac = sqrtf(v / LEVEL_BAR_FULL);
```

Both choices come from measurement. An RMS of 1.0 is a clipping signal, and a cry does not clip: the
loudest genuine cry measured on the bench carried **0.18**, the quietest one the system must catch
**0.010**. Against a full scale of 1.0 even a scream filled a third of the bar, so the bar said
nothing and only the number beside it was worth reading. At 0.25 a scream fills most of the bar, a cry
at one metre about two thirds, and a quiet room a sliver. The square root is there because **the
interesting part of this bar is the bottom fifth of the scale, where the trigger sits** — a linear
scale squashes exactly the region the caregiver needs to see.

The **notch** is a one-pixel vertical line at the cot's own trigger level, drawn through the bar:

```c
const int nx = x + 1 + (int)(sqrtf(t / LEVEL_BAR_FULL) * (float)(w - 2) + 0.5f);
fb_fill(nx, y, 1, h, C_TEXT);
```

It is the same `sqrtf` mapping as the fill, so the notch and the fill agree by construction. The bar's
colour carries the same fact: **green** while the cot is below its trigger (only being listened to),
**amber** once it crosses it (audio is going to the model), **rose** while the hub is announcing a cry
from it. That is what turns the bar from "a number in colour" into a picture of the decision the cot
is about to make.

The field is called `rms`, and the *threshold* is called `trigger`. This distinction is load-bearing
in the project's vocabulary: **"level" means the threshold, never the loudness.** The banner's bare
number is labelled `RMS 0.012` for the same reason — a bare number in a corner reads as a clock.

### The signal bar

Four bars, 3 pixels wide on a 5-pixel pitch, heights 4/7/10/13, unfilled bars in `C_SURFACE_HI`:

```c
const uint16_t col = (bars >= 3) ? C_GREEN : C_AMBER;
```

| Bars | Threshold | Colour |
|---|---|---|
| 4 | ≥ −60 dBm | green |
| 3 | ≥ −70 dBm | green |
| 2 | ≥ −80 dBm | amber |
| 1 | ≥ −90 dBm | amber |
| 0 | below −90, or no reading | amber, all four empty |

The dBm is printed beside it (`LINK -43 dBm`), and `LINK --` when there is no reading at all — the
sentinel is `0`, which is not a plausible dBm value. The number and the bars are the same reading, and
the help page says so explicitly, because a caregiver who sees four bars and −43 dBm should not have
to wonder whether they are two different measurements.

This reading is the RSSI of the cot's **telemetry as heard at the hub**. The cot prints its own bar on
its serial console from the RSSI of the hub's **heartbeat as heard at the cot**. Two directions, two
numbers, and they are not expected to match.

### The help page

The BOOT button's second face exists because of an obvious question: the panel says `RMS 0.023` next
to a bar with a notch in it, and `LINK -43 dBm`, and none of those words mean anything to a caregiver
at three in the morning who cannot go and look up what an RMS is. Twenty lines of small text, ten
pixels apart, explain the four readings in plain language — a quiet room near 0.005, a cry at one
metre about 0.03 to 0.05, the notch as "the level that cot sends audio over", −60 and better as
strong, −90 and worse as barely there. The footer reads `press BOOT to go back`.

### The splash, and the project's identity

The panel boots through **two** faces before the dashboard: a boot face (the waveform, the breathing
wordmark, the boot steps, a filling progress bar) and a title card. The title card carries
`AMAZING'S CRYNET` in accent teal, the strapline, the full project title across three lines,
**AMAZING AYOMIKUN ADELOWO**, the id **22/05/04/0029**, and along the bottom:

```
ESP32-S3 HUB  -  TWO COT NODES
```

The waveform moved up and shrank to make room for the stacked name (`WAVE_Y` 84 → **46**, `WAVE_MAX`
26 → **12**), and nothing collides: the wave ends at 59, the name runs 68 to 116, the strapline at
134, the boot step at 190, the bar at 206, the footer at 222.

### The footer counts cots, not cards

`snprintf(foot, …, "%u cot%s linked", online, …)` — the count is the number of cots **answering**, not
the number of cards drawn (D-54). The bug this fixed is worth remembering: the panel said
`3 cots linked` above cards that all read `NO SIGNAL`, because it was counting slots. With two fixed
slots that bug would have been permanent and invisible.

### Online versus offline treatment

Swapped on the user's request, then amended:

- a **live** cot carries the **full-strength vibrant teal outline** (rose when crying) and the
  *denser, more active* border-washed fill;
- an **offline** cot recedes — outline and empty bar washed towards the background, the faint accent
  wash for a fill — and its word is **OFFLINE**.

The original treatment blended live cards at 45 %, which made the *active* cards the faint ones. That
is backwards: the eye should be drawn to what is alive.

### The caregiver's device on the panel

Round 4 added the `PHONE` pill and, under a confirmed cry with nobody attached, the words
**`ALERT NOT DELIVERED`**. A cry the system detected but could not hand to a human is not a success,
and the panel says so.

## The rounded corners, and a host-side regression check

Every rounded corner had been drawing its arc on the **inside** of the shape — only the bottom-right
one looked right — because the corner loop walked its offsets inward from each disc's centre. Each
disc is now walked **towards its own corner**.

The fix is protected by `research/check_corners.py`, a host-side check that requires the four corners
to be **exact mirror images of each other**. That is the right shape for a graphics regression test:
not "does it look right" but a symmetry property that must hold, checkable without a display.

## What the panel is not

It is not a touch interface, not a configuration surface, and not required for the system to work.
`hub_display_start()` failing produces a warning and the hub carries on: *"a dead display does not
stop the monitoring, it only stops the showing."*