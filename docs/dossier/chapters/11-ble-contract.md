# Chapter 11 — The Bluetooth contract and the caregiver's device

## The frozen legacy contract

The wearable existed before the hub was rebuilt. Rather than change both ends at once, the project
**froze the BLE contract** and wrote the new hub to serve it byte-for-byte. That is why the two halves
could be developed, flashed and tested independently — and it is the reason for several constraints
that would otherwise look arbitrary.

| Item | Value |
|---|---|
| Device name | `INFANT_MONITOR_HUB` |
| Service UUID | `19b10000-e8f2-537e-4f6c-d104768a1214` |
| Alert characteristic | `19b10001-e8f2-537e-4f6c-d104768a1214` |
| State characteristic | `19b10002-e8f2-537e-4f6c-d104768a1214` |
| Stack | **NimBLE**, peripheral + broadcaster only |
| Max connections | **1** |
| Preferred MTU | 247 |

### The alert packet — 6 bytes

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0 | `cot_id` | u8 | which cot |
| 1 | `alert_type` | u8 | **1 = cry, 2 = stopped/cleared, 3 = deaf** |
| 2–3 | `confidence_pct` | u16 LE | 0–100 |
| 4–5 | `event_id` | u16 LE | the cry log's record number for this event, truncated to 16 bits — the same number the dashboard stores; 0 means the log was unavailable and the hub counted the event itself |

### The state packet — 8 bytes

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0 | `cots` | u8 | how many cots the hub knows |
| 1 | `crying_mask` | u8 | **bit 0 = cot 1**, bit 1 = cot 2; bits 2–7 always 0 on this hub |
| 2 | `deaf_mask` | u8 | same bit order |
| 3 | `confidence_pct` | u8 | the loudest cry's confidence |
| 4–7 | `started_at_s` | u32 LE | when the current cry episode began |

**`alert_type` has one value for "cry".** That single byte is why the model is binary (D-1). A
four-class cause classifier would have needed a new packet layout, a new wearable, and a new
validation of the whole path — for a distinction the project explicitly decided not to make.

`crying_mask` is a bitmask rather than a single id so that the wrist can know about *both* cots at
once. Only two bits can ever be set here — the hub refuses ids outside 1..2 in its link layer — but
the byte is eight bits wide because the contract is frozen legacy and was not narrowed when the cot
count was fixed. The deployed wearable uses the mask for its idle face **and, since D-86, for its alert
face too** — unioned with the cot the alert named, so the screen can never say `CRY` with nobody
named. The six-byte alert still carries a single `cot_id`, and that is what gates the buzz.

## Why NimBLE and not Bluedroid

From `sdkconfig.defaults`: *"the hub is already using the Wi-Fi radio for ESP-NOW and the internal
RAM for the front end's working buffers, and NimBLE is the smaller stack."*

The roles are trimmed to exactly what a server needs:

```
CONFIG_BT_NIMBLE_ROLE_PERIPHERAL=y
CONFIG_BT_NIMBLE_ROLE_BROADCASTER=y
CONFIG_BT_NIMBLE_ROLE_CENTRAL=n
CONFIG_BT_NIMBLE_ROLE_OBSERVER=n
CONFIG_BT_NIMBLE_MAX_CONNECTIONS=1
```

Central and observer are compiled out — the hub never scans and never connects. Every role removed is
RAM and flash the coexistence budget gets back.

## The advertising policy — the sharpest trade-off in the firmware

One radio carries both protocols. While the BLE stack transmits an advertisement the Wi-Fi receiver
is deaf, and the hub's window arrives as 286 ESP-NOW fragments it must not miss. NimBLE's fastest
default interval is `0x0020` = **20 ms**, and each advertisement goes out on all three BLE channels —
about **150 radio transmissions a second**, every one of them a moment when the burst can lose a
frame.

The policy, quoted from the source:

| Situation | Behaviour | Reason |
|---|---|---|
| A caregiver's device is **connected** | **not at all** | nobody needs to *find* a hub that is already connected; notifications travel over the connection, not over advertising |
| A burst is **in the air** | **slowly, 320 ms** (`ADV_INTERVAL_SLOW 0x0200`) | the wearable is the thing that has to be found |
| Otherwise | **100 ms** (`ADV_INTERVAL 0x00A0`) | the phone still finds it in well under a second |

The middle row is the interesting one, and it reversed an earlier decision. Advertising used to be
**stopped** during a burst. Then the bench measured a session in which the radio was busy **89 % of
the time** (230 s of burst airtime in 260 s), so the wearable was left waiting for a gap and **could
take a minute to attach**.

> An advertisement every 320 ms costs the burst a frame or two, and the resend path recovers them;
> silence cost the caregiver the device altogether.

That is the correct ordering of costs: a slightly slower burst is a nuisance the protocol already
repairs; an unattachable wearable is a failure of the device's whole purpose.

### Implementation detail

NimBLE takes the advertising interval **when advertising starts**, so changing the interval means
stopping and restarting:

```c
static void update_advertising(void) {
    const bool wanted = !s_connected;
    const uint16_t interval = (s_radio_busy || s_preparing) ? ADV_INTERVAL_SLOW : ADV_INTERVAL;
    if (wanted == s_advertising && interval == s_adv_interval) return;   // nothing to do
    ...
}
```

Two flags drive it: `s_radio_busy` (the radio needs the air now) and `s_preparing` (it will need it
shortly). The early return matters — the function is called on every burst start and stop, and an
unconditional log line printed *"advertising is off (a phone is connected)"* seven times in a row
before the guard was added.

## Publishing

```c
void ble_alert_publish(uint8_t cot_id, bool crying, uint16_t confidence_pct,
                       uint32_t record);
void ble_alert_publish_deaf(uint8_t cot_id, uint32_t record);
void ble_alert_publish_state(const ble_state_packet_t *state);
```

`record` is the cry log's number for the event, handed out when the episode *starts* so the wrist
can show it while the cry is still running. It is what distinguishes a new event from a repeated
notification of the same one, and it is the join between the three surfaces: the buzz, the panel
and the dashboard's record all name the same number (Chapter 12). The packet field is sixteen bits,
so the number wraps at 65,536 — about three years of nights — while the dashboard keeps the whole
thirty-two. When the log could not be opened, the hub passes 0 and counts its own events, so the
wrist still shows a number that rises. Notifications are sent only when a client is connected and
subscribed; the value is also readable, so a client that attaches mid-cry gets the current state
rather than waiting for the next edge.

State is published **whenever it changes and at least once a second** while a link is up. That
guarantee is what lets the wearable be entirely push-driven — it never issues a blocking read.

## The console shortcut that made this testable

`alert <cot>` on the hub's serial console calls the same `ble_alert_publish()` the detection logic
uses. A successful `alert 1` therefore proves the GATT server, the notification, the wearable's
callback and the display — **independently of the model and the radio**.

That separation is what allowed the haptic fault to be localised: the alert arrived, the callback
fired, the log printed, and the motor did not move. Without a way to inject an alert, that diagnosis
would have required making a noise and hoping.

## The host-side test clients

| Tool | What it does |
|---|---|
| `firmware/tools/ble_alert_test.py` | connects as a BLE client, subscribes to both characteristics, prints every packet — this is what produced the `ALERT {'cot': 1, ...}` lines quoted throughout |
| `firmware/tools/serve_alert_page.py` | a local web page showing the live alert state, for a demonstration without the wearable |

## Coexistence

`CONFIG_ESP_COEX_SW_COEXIST_ENABLE=y` — software coexistence arbitrates airtime between ESP-NOW and
BLE on the one radio. Without it the two stacks fight and the burst loses. With it, and with the
advertising policy above, the measured result is **286/286 fragments with CRC-32 MATCH while a BLE
client is connected** — which is the exact configuration that failed before this work.