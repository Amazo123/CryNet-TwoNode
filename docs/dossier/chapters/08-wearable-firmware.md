# Chapter 8 — The wearable firmware

## The job

`firmware/wearable/wearable_crynet/wearable_crynet.ino` — 750 lines on an ESP32-C3 SuperMini. It runs
no model, makes no decisions, and has exactly one purpose: **be trusted to tell a caregiver something
they must not miss.** Every design choice in it follows from that.

Hardware: SSD1306 128 × 64 OLED on I²C (SDA 5, SCL 6), and a coin ERM vibration motor on GPIO7 through
a BC547 low-side switch.

## The rule that shapes the whole file: the radio must never block the human interface

Every Arduino BLE call blocks its caller. The two-argument `scan->start()` waits on a semaphore
**forever**. `connect()` can hold for up to thirty seconds. A characteristic read waits for a peer that
may never answer.

So the BLE work lives in its own FreeRTOS task, and `loop()` does only two things:

```cpp
void loop() {
    haptic_tick();                                  // the motor, every 10 ms
    if (g_dirty || now - g_last_draw_ms >= 100) {   // the screen
        g_dirty = false; g_last_draw_ms = now; render();
    }
    delay(10);
}
```

```cpp
xTaskCreate(ble_task, "ble", 6144, nullptr, 1, nullptr);
```

The comment states the intent exactly: *"Unplugging the hub can stall this task for a while; the
screen, the buzz and the animation keep going."* A caregiver whose wristband freezes because the hub
went out of range has been failed by the device, not informed by it.

The stack is 6,144 bytes — generous, because service discovery and the library's own bookkeeping run
on it. Priority 1: above the idle task, below nothing the user sees.

## The contract it is written against

```cpp
HUB_NAME     = "INFANT_MONITOR_HUB";
SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
ALERT_UUID   = "19b10001-e8f2-537e-4f6c-d104768a1214";
STATE_UUID   = "19b10002-e8f2-537e-4f6c-d104768a1214";
```

This is the **frozen legacy contract**. The wearable existed before the hub was rebuilt, and the
rebuilt hub was written to serve these exact UUIDs and packet layouts. That is why the two halves
could be developed and tested independently, and it is why the model is binary — `alert_type` has one
value for cry.

## The alert callback

```cpp
if (len < 6) { log("short alert"); return; }
prev_type = g_type;
g_cot      = data[0];
g_type     = data[1];
g_conf_pct = data[2] | (data[3] << 8);
g_event    = data[4] | (data[5] << 8);
g_have_alert = true; g_alert_ms = millis(); g_dirty = true;

if      (g_type == 1 && prev_type != 1) haptic_trigger();   // cry
else if (g_type == 3 && prev_type != 3) haptic_trigger();   // deaf
```

Three things are worth defending here.

**Length is checked before anything is read.** A malformed notification cannot read past the buffer.

**One buzz per cry, not one per announcement.** The hub re-issues the alert when a louder cot joins
the cry — the display follows the baby from cot to cot, but the wrist buzzes once. The edge test
`prev_type != 1` is what implements that. Without it, a cry heard by both cots would buzz twice
and the caregiver would learn to ignore the buzz. **This was measured, not assumed:** on 2026-11-20
nine cry announcements across five episodes produced exactly five buzzes, and the four silent ones
were handovers between cots.

**Deafness buzzes too.** `alert_type = 3` means the hub cannot get that cot's audio, so it cannot
announce a cry from it. *"It is not being watched, and the caregiver has to hear that from the wrist,
not only see it on the hub's panel."* A silent failure of a safety device is the worst failure it can
have, and this is the line that prevents it.

## The state callback

```cpp
if (len < 8) return;
g_cots = data[0];
g_mask = data[1];        // bit 0 = cot 1
g_dirty = true;
```

The hub publishes state whenever it changes and **at least once a second** while a link is up, so the
idle face's crying mask is never more than a second stale and nothing on the wearable ever blocks
waiting for a read the hub may never answer. Push, not poll — the same reasoning as the BLE task.

`g_mask` drives the idle face's crying list — **and, since D-86, the alert face too.**

### The alert face names every crying cot — D-86

The alert packet names **one** cot: the hub's loudest-crying-cot choice. That is deliberate and it
stays, because one cry must be one buzz. But the *screen* used to draw its cot number from that single
`cot_id` and then hold the glass for `ALERT_HOLD_MS` = 60 s — so the one face a caregiver actually
looks at during a cry hid the list the wrist was already receiving. Detection was never the gap: the
nodes gate independently, the hub confirms each cry on its own evidence, and `crying_mask` has carried
every crying cot since D-24.

The face now builds its label from **`crying_mask` unioned with the named cot**:

```cpp
const uint8_t limit = g_cots ? g_cots : 8;
uint8_t mask = g_mask;
if (g_cot >= 1 && g_cot <= 8) mask |= (uint8_t)(1u << (g_cot - 1));
```

**Why the union and not the mask alone.** The alert is instant; the mask is published on change plus a
1 s heartbeat. So the mask can be a second behind the alert, or already clear while this face still
holds. Without the union the screen could say `CRY` with nobody named — a safety device showing an
alarm with no subject. The named cot is therefore always in the list.

**Why the text shrinks.** One cot renders exactly as before: `COT n` at size 3. Both crying render
**`COTS 1 2`**, which is 8 characters — 144 px at size 3 on a 128 px glass, so it drops to size 2
(96 px). The loop still walks all eight mask bits and steps the size down again rather than let
`snprintf` cut a cot off the end, because the state characteristic's mask byte is eight bits wide even
though this hub only ever sets two. **A deaf cot keeps the mask out** — deafness is one cot by
definition.

**What it deliberately does not do:** no second buzz when a second cot joins, no change to detection,
to the serialized loudest-first pulls, to the 1.5×/1.5 s handover dwell, or to BLE/Wi-Fi coexistence.
No new BLE traffic, and the hub image does not move — only the wrist is reflashed. The alternative, a
seventh mask byte on the alert characteristic, was rejected: every consumer checks a *minimum* length
so it would not have broken them, but it edits a frozen legacy contract and forces a hub reflash to
buy about one second of freshness the wrist already has.

**The confidence bar stays the loudest cry's figure** — the only one the hub sends. It is not per-cot,
and the code now says so.

**Verified on the bench, 2026-11-20.** One clip heard by both node microphones put the hub's mask at
`0x03` for **fifteen consecutive seconds**, and the owner watched the glass read the two-cot label.
Three separate two-cot events were captured. Over the whole session, **nine cry announcements across
five episodes produced exactly five buzzes** — the four silent ones were handovers between cots, which
is the one-cry-one-buzz rule working, not a miss.

## Reconnection, and the bug that made a live link deaf

```cpp
class HubClientCallbacks : public BLEClientCallbacks {
    void onDisconnect(BLEClient *) override {
        g_connected = false;
        g_alert = nullptr; g_state = nullptr;
        g_mask = 0; g_cots = 0;      // a stale mask names cots nobody is watching
        g_dirty = true;
    }
};
```

Clearing the mask on disconnect is deliberate: the alert face outlives a drop by up to a minute, and a
stale mask would name cots that are no longer being watched. Cleared, the face falls back to the cot
the alert itself named — which is still true.

And in `connect_to_hub()`:

> Fresh service discovery, every connection. The library keeps the previous connection's service
> handles across a disconnect — `m_haveServices` survives it — so without this the second connect
> hands back handles that point at a peer that no longer exists: **subscriptions go nowhere and the
> link looks alive but is deaf.**

That is a nasty class of fault: every indicator says connected, and no alert ever arrives. Forcing
discovery on each connect is the cure, and the check `getServices()->empty()` fails the connection
loudly rather than proceeding with nothing.

The scan runs in **two-second windows** with `setWindow(30)`, results cleared each round so the heap
does not grow with every advertisement heard.

## The haptic drive

```cpp
HAPTIC_MS       = 2500;   // the whole buzz
HAPTIC_PULSE_MS = 250;    // one pulse

void haptic_trigger() {
    g_haptic_start = millis();
    g_haptic_until = g_haptic_start + HAPTIC_MS;
    Serial.printf("[haptic] alert %u — motor on GPIO7 for %u ms\n", g_event, HAPTIC_MS);
}

void haptic_tick() {
    bool on = false;
    if (millis() < g_haptic_until)
        on = (((millis() - g_haptic_start) / HAPTIC_PULSE_MS) % 2) == 0;
    digitalWrite(PIN_MOTOR, on ? HIGH : LOW);
}
```

250 ms on, 250 ms off, for 2.5 seconds — five pulses. The rhythm is the same as the alert band
blinking across the top of the screen, *"so the wrist and the eye agree on what is happening."*

`haptic_tick()` is called from `loop()` every 10 ms and is non-blocking: no `delay()` inside an alert,
ever. GPIO7 is driven **low before anything else happens** in `setup()`, so the motor cannot spin
during boot.

### How the motor was proved, and what is still unproven

The motor is a real coin ERM on a BC547 low-side switch, not the DRV2605L breakout the earliest
planning documents named (D-77). Getting to a buzz took four separate proofs, and it is worth being
able to tell them apart in a defence — because the fourth one is only half a proof, and saying so is
the difference between an honest account and a sales pitch.

**Proof 1 — the electrical path, with no hub in the room.** A dedicated bench sketch,
`firmware/wearable/haptic_test/haptic_test.ino`, drives GPIO7 with exactly the same pulse train the
alert path uses and nothing else — no BLE, no OLED, no hub. It is flashed with one command:

```bash
python firmware/tools/flash_node.py --port COM30 --sketch haptic_test
```

The motor was seen and felt to toggle. That isolates the transistor, the base resistor, the flyback
diode, the stall cap and the motor itself from every line of application code. The sketch stays in
the repository, with the restore command in its header comment, so a fresh board can be proved
without hunting for the procedure.

**Proof 2 — the whole chain.** On 2026-11-06 three alert cycles in a row came through complete:
`ALERT cot 1 type 1 conf 100%` on the wrist, the haptic fired, and `clear` came back as `type 2`. The
wearable also recovered from a hub reset mid-link — `hub lost — rescanning`, found again, resubscribed
to *both* characteristics.

**Proof 3 — the fitted cap.** On 2026-11-11 the motor was replaced (the first one's coil was open,
which showed up as the full **3.296 V** appearing across the motor with GPIO7 switching — no current
means no drop across the cap) and the new motor vibrates correctly with the **22 Ω** that is actually
fitted (D-85).

**Proof 4 — on a cell, and this is where it gets interesting.** The wearable **has run from its Li-Po
pouch**: during the third round of the 2026-11-20 session it was on the pouch, not USB — which is
precisely why COM30 was absent and no wrist log could be captured that round. So the unit works on its
cell. **But the buzz went missing in that round**, and that is an open fault, not a closed proof.

The firmware is exonerated: D-86 touches no line matching `haptic|PIN_MOTOR|digitalWrite|prev_type`,
so the drive is byte-identical to the build proven on 2026-11-11, and `[haptic] … motor on GPIO7 for
2500 ms` fired on all four alerts of the round before. **That log proves the command, not the
current.** A sagging 3.3 V rail on the pouch is a live candidate — the OLED, the C3's radio peaks and
the motor all share the board's one linear regulator.

**The decisive test is a meter across the motor while an alert is live**, and the three readings mean
three different things:

| Reading | Meaning |
|---|---|
| ≈ **3.3 V** | no current — open coil or a dry joint |
| ≈ **2.1 V** | current flowing; a weak motor or a sagging rail |
| ≈ **0 V** | the BC547 is not switching |

**What is still unproved:** the rail's behaviour during a buzz on a cell, and **runtime** — no unit's
battery life has ever been measured. A coin motor's inrush is the largest transient in the system, and
a pouch through a boost and a linear regulator is a stiffer test than a USB port. That is O-1d.

**One trap worth knowing.** `Adafruit_SSD1306` 2.5.17's `begin()` **returns `true` unconditionally** —
the only failure path is the framebuffer allocation — and the library discards the I²C
`endTransmission()` return value. So `[oled] up` does not mean a display is attached, and the
`SSD1306 not found at 0x3C` line can never fire. The firmware's `g_oled_ok` is true on a board with no
glass, writing a kilobyte per frame into a bus that NACKs it. Harmless, but it means **the OLED must
be judged by eye, never by that log line.**

## The display

The OLED is monochrome, so it cannot copy the hub panel's colour. It copies its *structure*: the
waveform along the bottom edge, the wordmark, the accent band across the top of the title card, the
boot progress bar. The accent is drawn **inverted**, and an alert turns the whole screen upside down
for as long as the wrist is buzzing — *"the loudest thing one bit can say."*

| Face | Duration | Content |
|---|---|---|
| Boot | `WEAR_BOOT_MS` 2400 ms | wordmark + a progress bar that fills as the device comes up |
| Title | `WEAR_TITLE_MS` 6400 ms | `AMAZING'S` / `CRYNET` on two lines, the owner's name and id, accent band, waveform |
| Dashboard | while idle | link state, cot count, crying mask, animated waveform |
| Alert | `ALERT_HOLD_MS` **60000 ms** | inverted screen; `COT n` at text size 3 for one cot, **`COTS 1 2`** at size 2 for both (D-86); confidence on a bar, blinking band |

`centre_x()` is arithmetic rather than measurement because the classic Adafruit font is six pixels
wide per cell at any text size — so centring is `(128 − 6·size·strlen(s)) / 2`, not a `getTextBounds`
call. On a 1 KB-RAM display driver that matters.

The renderer redraws on a steady 100 ms beat *and* immediately whenever `g_dirty` is set, so an alert
appears at once and also leaves on its own when its minute is up. No face is ever entered or left by a
blocking wait.

## Build

Same toolchain as the node: Arduino CLI, ESP32 core 3.3.12, FQBN `esp32:esp32:weact_studio_esp32c3`.
One board type across three of the four units — both cots and the wrist — means one toolchain,
one spare, one flashing procedure.