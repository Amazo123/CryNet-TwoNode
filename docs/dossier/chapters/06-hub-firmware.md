# Chapter 6 — The hub firmware

## Layout

The hub is an ESP-IDF application built through PlatformIO, with ten first-party components. It is
not an Arduino sketch: the BLE stack (NimBLE), the coexistence configuration and the PSRAM allocator
all need `sdkconfig`, and Arduino's prebuilt ESP32 core does not expose it.

```
firmware/hub_infer/
  platformio.ini
  src/
    main.c            boot, probes, init order, then the main loop
    link_stage.c/.h   reassembly, verdicts, arbitration, liveness  (1,824 lines)
    console.c/.h      the serial command interface
    probes.c/.h       the four self-test windows
  components/
    crynet_dsp/       the frozen front end
    crynet_infer/     the TFLM interpreter wrapper (C++ in an extern "C" shell)
    crynet_model/     the embedded INT8 array + generated tables
    crynet_proto/     the wire format, shared with the node by construction
    node_link/        ESP-NOW receive/transmit
    ble_alert/        NimBLE GATT server
    hub_display/      ILI9341 driver + the panel UI
    crynet_log/       the cry log, on the hub's own flash   (Chapter 12)
    crynet_clock/     the wall clock, and honesty about not having it
    crynet_net/       Wi-Fi, the uploader, and the presence report
    esp-tflite-micro/ vendored third party
    esp-nn/           vendored third party, SIMD kernels
```

Vendoring TFLM and ESP-NN inside `components/` is deliberate: the PlatformIO registry versions did not
match the ESP-IDF 6.1 API, and a build that fetches a moving dependency is not a build that can be
reproduced in a year. `firmware/tools/fetch_deps.sh` and `patch_deps.py` record exactly what was
fetched and what had to be patched.

## Boot, in order

`app_main()` does eight things, and the order of six of them is load-bearing.

### 1. Report the platform

Chip revision and core count, PSRAM present/absent and its size, free internal heap, flash size,
model size, the model's own threshold, the announce threshold, the silence gate, and the input
quantisation scale and zero-point. Every one of these is a number a defence might be asked for, and
the firmware prints them at every boot rather than leaving them in a document.

One ESP-IDF 6.x migration detail lives here: `esp_flash_get_size()` now takes a chip handle (`NULL` =
default chip) and writes through an out-parameter, where 5.x returned it directly. And one honesty
rule (D-106): the banner is the identity check, so the firmware version it prints is stamped at
configure time — an earlier build inherited a stale stamp and described a new build as an old one,
which is how a real stack overflow went undiagnosed for a night (see **The stacks**, below).

### 2. Initialise NVS

The Bluetooth stack keeps its bonding keys in NVS, so the store must exist before the host starts.
The standard recovery is implemented: on `ESP_ERR_NVS_NO_FREE_PAGES` or
`ESP_ERR_NVS_NEW_VERSION_FOUND`, erase and re-init.

### 3. Bring up the front end and the interpreter

`crynet_dsp_init()` allocates the 5.4 KB scratch in internal SRAM. `crynet_infer_create()` allocates
the 262,144-byte arena in PSRAM and reports how much of it the model actually uses (108,328 B).
Either failure aborts the boot with a specific error — there is no point running a monitor whose
model cannot load.

### 4. Run the four probes — and gate everything on them

This is the design decision that most distinguishes this firmware. **The hub does not start its
radio, its Bluetooth server, its display or its console unless the self-test passes.**

The probe buffers (90 KB in total: PCM, float features, INT8 features) are allocated in **PSRAM**,
falling back to internal SRAM if PSRAM is absent. They are pointers, not file-scope arrays, precisely
so they can be freed:

> They are only needed while the probes run, but as file-scope statics they would sit in internal RAM
> for the life of the program — and the Bluetooth stack needs that RAM far more than the probes do
> (NimBLE's store configuration was failing to allocate on a board whose radio worked perfectly).

For each probe:

1. Generate the PCM synthetically and check its **CRC-32 against the host's expected value**. If the
   generator itself has drifted, the test says so instead of comparing against the wrong reference.
2. Compute features; time the front end and the quantisation separately.
3. Compare the INT8 features to the host reference: **worst per-byte delta must be ≤ 1 LSB, and at
   most 1 % of the 5,184 features may differ at all.** Both conditions, not just the max — a single
   large error and a thousand small ones are different failures.
4. Run inference; time it; print `P(no_cry)` and `P(cry)`.
5. Apply **the same decision rule the live path uses** — silence gate plus `CRYNET_CLEAR_CRY`, not the
   model's own threshold. The comment records why: the boot banner used to say `ALERT` for the noise
   probe, a window the running hub would have refused, so the boot report and the system contradicted
   each other.

Then the buffers are freed and the free internal heap is printed again.

### 5. Memory, clock and log

Before any radio comes up, the hub opens its record: `crynet_clock_init()`, then `crynet_log_init()`,
which mounts the six-megabyte SPIFFS partition that had been reserved from the first build and never
used, and restores the clock from the last time the log saved. The hub's own start is written as a
`boot` record — a gap in the cry history means either a quiet night or a hub that was off, and only
the boot records tell them apart. A flash that will not mount is a **warning, not a stop**: the
monitoring is the product, the record is a benefit.

### 6. Radio, then Wi-Fi, then Bluetooth, then display

The order is stated in the source and it was learned the hard way:

> NimBLE's pools and the Wi-Fi driver's buffers come out of the same internal RAM, and when BLE
> claimed its memory first the Wi-Fi driver ran out mid-init and the ESP-NOW link never started. The
> radio takes what it needs while the heap is whole, and BLE lives on what is left.

Measured free internal heap through the sequence:

| Point | Free internal heap |
|---|---|
| Boot | 298,763 B |
| After the probes (buffers freed) | 290,791 B |
| Radio up | 215,155 B |
| Bluetooth up | **149,271 B** |

*(That ladder was measured before the Wi-Fi stage joined the boot; the current sequence — clock and
log, radio, uploader, Bluetooth — prints its own free-heap lines on the banner at every start, and
the Wi-Fi driver's buffers come out of the same internal RAM as NimBLE's pools, which is exactly why
both of them initialise before Bluetooth.)*

The uploader shares the radio with ESP-NOW, so `crynet_net_start()` runs here too, its interface
created while the internal heap is still whole. With no network configured it starts nothing and
costs nothing.

The display comes last of the subsystems because its 153,600-byte framebuffer goes to PSRAM and its
driver needs only a small internal allocation.

### 7. Console last

`console_start()` is deliberately last, "so that every command it accepts can be carried out: the
radio is up, the Bluetooth server is up, and a test alert has somewhere to go."

### 8. `link_stage_run()`

The main loop, which never returns.

## Graceful degradation

Each of the five optional subsystems is started with a warning, not an abort:

```c
if (!crynet_log_init())        ESP_LOGW(TAG, "the cry log could not be opened; "
                                         "the hub carries on without a record");
if (!link_stage_radio_start()) ESP_LOGW(TAG, "the radio could not be started; the hub carries on without it");
if (!crynet_net_start())       ESP_LOGW(TAG, "the uploader could not be started; "
                                         "cries are still recorded in the hub's flash");
if (!ble_alert_start())        ESP_LOGW(TAG, "the Bluetooth alert server could not be started; ...");
if (!hub_display_start())      ESP_LOGW(TAG, "the display could not be started; ...");
```

The reasoning is stated in the code: *"a dead display does not stop the monitoring, it only stops the
showing."* For a device whose job is to wake a caregiver, failing loudly and continuing is better than
refusing to boot. The **probes** are the exception, because a hub whose model is wrong is worse than
no hub.

## The console

`console.c` is 444 lines: a 5,120-byte task at priority 3 reading lines from the same UART the log
is written to. It grew with the record and the network, and its word list is the system's second
control panel:

| Command | Effect |
|---|---|
| `help` | list the commands |
| `status` | cots, liveness, crying mask, deaf mask, heap, counters |
| `alert <cot>` | inject a test alert for that cot, all the way to BLE |
| `clear` | clear the alert state |
| `history [n]` | the last n cry-log records, newest first |
| `log` | how much is recorded and how much is unsent |
| `log clear` | throw the log away (the record numbers carry on) |
| `net` | the network: state, batches, failures, last error |
| `net set <url>` | where the records are posted |
| `net ssid <s> <p>` | which Wi-Fi to join |
| `net name <n>` | this hub's name on the dashboard |
| `net token <t>` | the dashboard's shared secret (NVS, never compiled in) |
| `upload` | send the unsent records now |
| `logtest` | prove, on this chip, that out-of-order records are not lost |

All of the configuration words write NVS, so they survive a reflash; nothing about the network is
compiled into the image, and the token is not a tracked file (D-103).

`alert <cot>` is the reason the BLE path can be tested without making a noise. It exercises the real
publish path — the same `ble_alert_publish()` the detection logic calls — so a successful `alert 1`
proves the GATT server, the notification and the wearable's callback, independently of the model.
That separation is what allowed the haptic fault to be localised to hardware (Chapter 14).

Two parsing rules were paid for in lost words: an exact match guards `log` because a prefix match
would swallow `logtest` and print the log instead of running the proof (D-98); and `net` is matched
with the same care, because the network's words all begin with it.

## `link_stage.c` — the state machine

1,642 lines, the largest file in the project. Its constants are the system's timing behaviour:

| Constant | Value | Meaning |
|---|---|---|
| `BURST_TIMEOUT_MS` | 15000 | abandon a burst that never completes |
| `BURST_FAIL_LIMIT` | 3 | consecutive failures before backing off a node |
| `BURST_BACKOFF_MS` | 60000 | how long to leave a failing node alone |
| `RECOOLDOWN_MS` | 1500 | minimum gap between verdicts on one node |
| `CRY_HOLD_MS` | 8000 | how long a confirmed cry stays on the panel |
| `FRAG_STALL_MS` | 100 | silence before asking for a resend |
| `FRAG_STALL_MS_MAX` | 1500 | adaptive upper bound on that silence |
| `FRAG_SETTLE_MS_MAX` | 3000 | how long to let a burst settle before judging it |
| `RESEND_MIN_FLIGHT_MS` | 250 | minimum gap between resend rounds |
| `RESEND_MAX_ROUNDS` | 10 | then give up on the window |
| `FRAG_PER_FRAGMENT_MS` | 4 | the pacing the hub asks the node for |
| `PREPARE_QUIET_MS` | 3000 | quiet period before a node is considered idle |
| `COT_SWITCH_MARGIN` | 1.5 | loudness ratio needed to steal the primary label |
| `COT_SWITCH_DWELL_MS` | 1500 | how long that ratio must hold |
| `NODE_LIVE_TIMEOUT_US` | 2 s | open-radio silence before "offline" |
| `NODE_LIVE_MAX_US` | 20 s | hard cap regardless of deafness discounts |

### Liveness, and why it is display-only

`node_live()` decides whether a cot's card says ONLINE or OFFLINE. It is **not** consulted anywhere in
the detection or announcement path. A cot that is momentarily marked offline can still have its
window classified and can still raise an alert.

The subtlety is `radio_deaf_now_us()`. While the hub is receiving a burst it is deliberately deaf to
other traffic, and while it is advertising BLE it may miss frames. Counting that self-inflicted
silence against a node would make every cot flicker offline whenever another cot speaks. So the
liveness clock **discounts burst deafness** — `s_radio_deaf` is set only by `burst_started()`, not by
BLE airtime — and is capped at 20 s so a genuinely dead node still goes offline eventually.

This is exactly the "node 1 went offline for a split second" observation from the bench: cosmetic,
panel-only, and by design.

### The arbitration

The hub keeps a per-cot record: last RMS, last verdict, `cry_run` (consecutive cry verdicts), the
cry hold expiry, and the switch dwell timer. The primary label goes to the loudest crying cot; another
cot takes it only if it is **1.5× louder for 1500 ms continuously**. Without that hysteresis the label
oscillates between two cots hearing the same cry, which with two cots a metre apart is the normal
case rather than an edge case.

### The heartbeat, and the two RSSI readings

`link_stage_run()` sends a heartbeat once a second, on its own clock:

```c
if ((probe_now - last_heartbeat_us) > 1000000) {
    last_heartbeat_us = probe_now;
    node_link_send_heartbeat(nl);
}
```

`node_link_send_heartbeat()` builds a **twelve-byte** frame of type 4 addressed to the broadcast MAC.
It asks for nothing. Its entire purpose is to give each cot a frame whose RSSI it can measure, so the
node's own link bar is a live reading rather than a stale one from the last pull.

The framing is the trap. `crynet_proto_build()` originally gave the twelve-byte payload-less layout
only to a REQUEST; a HEARTBEAT fell through to the full fourteen-byte header and came out **sixteen
bytes**. The parser on the far end treats a heartbeat like a request — any length other than
`CRYNET_PROTO_REQUEST_BYTES` is a bad frame — so **every heartbeat would have been rejected as
malformed**, and the node's link bar would have sat dark on a hub that was in fact answering. The fix
is one condition:

```c
if (type == CRYNET_PROTO_TYPE_REQUEST ||
    type == CRYNET_PROTO_TYPE_HEARTBEAT) {
```

A host test now holds both rules — `research/test_heartbeat_framing.py` compiles the real
`crynet_proto.c` and checks that a heartbeat is exactly twelve bytes, that it round-trips as type 4,
that the other frame types are unchanged, and that the two-cot id rule hears 1 and 2 while ignoring
0, 3 and 255. **The test was checked against the bug it was written for:** reverting the one-line fix
makes it fail with `a heartbeat is 16 bytes, not 12`.

In the other direction, `slot->tel_rssi` — which the link layer had always measured and never
exposed — now travels out through `node_link_poll_telemetry()` and `node_link_last_telemetry()` into
`link_stage_cot_t.rssi`, and from there into the display state and the console. The console's `status`
prints it beside each cot's other numbers:

```
cot 2: rms 0.0230  level 0.0090  window 0.0000 (filling)  confidence 0%  link -43 dBm
```

`link --` when there is no reading, because `0` is the sentinel for "never heard", not a dBm value.

### Deafness

A node whose radio is transmitting but whose microphone produces nothing — or whose windows are all
refused as clipped — is marked in `deaf_mask` and reported as `alert_type = 3`. A monitor that cannot
hear is a different failure from a room that is quiet, and the system distinguishes them.

## `crynet_infer.cpp` — the interpreter wrapper

247 lines of C++ behind an `extern "C"` interface, so the rest of the firmware stays C.

- The arena is allocated with `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)`.
- `MicroMutableOpResolver<6>` registers **only six operators** — `CONV_2D`, `DEPTHWISE_CONV_2D`,
  `MAX_POOL_2D`, `MEAN`, `FULLY_CONNECTED`, `SOFTMAX` — rather than `AllOpsResolver`. Every unused
  kernel registered is flash the linker cannot drop. (The deployed `conv_cnn` uses five of the six;
  depthwise is registered so `sep_cnn` can be deployed without a firmware change.)
- ESP-NN provides the SIMD implementations of those kernels for the Xtensa LX7's vector unit; that is
  what turns a multi-second reference-kernel inference into **101.8 ms**.
- Output dequantisation: `(q − zero_point) × scale`, then softmax over the two logits.
- Errors are captured as a string retrievable with `crynet_infer_error()`, so a failure prints a
  reason rather than a status code.

## Build configuration

Two files carry the configuration, and the split matters: `platformio.ini` holds the board and the
build flags, `sdkconfig.defaults` holds everything ESP-IDF owns.

**`platformio.ini`** — `platform = espressif32 @ 8.0.0`, `board = esp32-s3-devkitc-1`,
`framework = espidf`, `board_build.flash_mode = qio`, `board_upload.flash_size = 16MB`,
`board_build.partitions = partitions_16mb.csv`, and the build flags `-DBOARD_HAS_PSRAM`,
`-DCORE_DEBUG_LEVEL=3`, `-DCRYNET_LINK_PROMISCUOUS=1`.

Three comments in that file are hard-won knowledge and worth memorising:

- **Do not pin `framework-espidf` with a `platform_packages` URL.** PlatformIO 6.2 installs a
  URL-specified framework by treating the archive as an npm package: it reads the wrong
  `package.json` out of the tree and leaves `packages/framework-espidf` holding only a test-fixture
  package, so CMake then fails with *"include could not find requested file:
  .../tools/cmake/project.cmake"*. The framework is installed manually and pinned by
  `packages/framework-espidf/.piopm`.
- **`board_build.esp-idf.overwrite_managed_components = no`** — the IDF component manager downloads
  `espressif/esp-nn` into `managed_components`, and PlatformIO otherwise wipes it on every configure.
- **The optimisation level is set the ESP-IDF way**, in `sdkconfig.defaults`
  (`CONFIG_COMPILER_OPTIMIZATION_PERF`). The Arduino-style `-DCOMPILER_OPTIMIZATION_PERF` macro does
  nothing here.

The promiscuous flag is **off by default in the code** and currently **on in this ini**: it brings
back the air counters, which count how many frames carrying the CryNet magic the radio hears against
how many the ESP-NOW layer hands up. Those counters are what settle whether a fragment that never
arrived was lost in the air or dropped by the hub's own receive path — the distinction that closed the
airtime investigation (Chapter 9).

**`sdkconfig.defaults`** — the settings that make this board work:

| Setting | Value | Why |
|---|---|---|
| `CONFIG_ESPTOOLPY_FLASHMODE` | **"dio"** | see below — the effective mode is DIO even though the QIO choice symbol is set |
| `CONFIG_SPIRAM_MODE_OCT` / `SPEED_80M` | y | the N16R8's **octal** PSRAM; quad mode would not see it |
| `CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL` | 4096 | allocations ≤ 4 KB stay internal automatically — the DSP scratch benefits |
| `CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP` | y | Wi-Fi/LwIP buffers may go to PSRAM, relieving internal heap |
| `CONFIG_COMPILER_OPTIMIZATION_PERF` | y | **-O2**, with assertions still enabled. ESP-IDF defaults to `-Og`, and the FFT and the convnet are compute-bound |
| `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240` | y | the platform default here is 160 MHz; the DevKitC-1's LX7 runs at 240 |
| `CONFIG_FREERTOS_HZ` | 1000 | 1 ms tick, so the burst timers mean what they say |
| `CONFIG_BT_NIMBLE_ENABLED` | y | NimBLE, **not** Bluedroid: the smaller stack, because the Wi-Fi radio and the internal heap are already busy |
| `CONFIG_BT_NIMBLE_ROLE_PERIPHERAL` / `BROADCASTER` | y | the hub is a server only |
| `CONFIG_BT_NIMBLE_ROLE_CENTRAL` / `OBSERVER` | n | compiled out — the hub never scans or connects |
| `CONFIG_BT_NIMBLE_MAX_CONNECTIONS` | 1 | one caregiver device |
| `CONFIG_BT_NIMBLE_ATT_PREFERRED_MTU` | 247 | comfortably above the 8-byte state packet |
| **`CONFIG_ESP_COEX_SW_COEXIST_ENABLE`** | **y** | software coexistence arbitrates airtime between ESP-NOW and BLE on the one radio |
| `CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM` / `DYNAMIC` | 32 / 64 | a cot sends a 286-fragment burst as fast as the radio allows; the hub needs receive buffers that can hold one. Affordable now that the probe buffers live in PSRAM |
| `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE` (+ `_DEFAULT_FULL`) | y | root certificates, so an `https://` dashboard can prove who it is; about 60 KB of flash, read only when a connection is actually made |
| `CONFIG_LWIP_SNTP_MAX_SERVERS` | 3 | lwIP's default room is one; two time servers are configured, so one being unreachable is not a clock lost |
| `CONFIG_ESP_WIFI_NVS_ENABLED` | **n** | the station keeps its config in RAM: the cot link owns the radio's channel, and nothing about the network should be written to flash on every boot |

### The stacks (D-107)

The last firmware reliability finding is not a setting anyone would guess at. The whole live system
runs in ESP-IDF's `main` task — `app_main()` never returns — but that task's stack was left at the
**3,584-byte default sized for an `app_main` that returns**, and the hub died mid-run with a stack
overflow that presented as random restarts. The restarts had first been diagnosed as power-class
resets (D-106) on the strength of a clean-power soak; the very next capture caught the real cause.
The main task now has **16,384 bytes**, every task's stack is sized for what actually runs on it
(console 5,120 · `crynet_net` 8,192 · display 4,096), and the same soak that once exonerated the
power supply now runs silent: zero restarts, zero cot flap, presence posts on the exact 30-second
cadence. The lesson is recorded in the decision itself: *a soak proves the configuration that ran
during the soak.*

### The flash-mode subtlety (D-47)

`sdkconfig.esp32s3` carries `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y` **and**
`CONFIG_ESPTOOLPY_FLASHMODE="dio"`. The string is what esptool acts on, so **the images are written
DIO** and both `bootloader.bin` and `firmware.bin` carry flash-mode byte `0x02`.

The reason: a combined image built with QIO makes the chip **watchdog-reset in a loop**
(`rst:0x7 TG0WDT_SYS_RST` repeating, no application output). The ROM cannot read this board's flash in
QIO before the bootloader has configured its own timing. **The bootloader switches the chip to QIO by
itself once it is running**, so nothing is lost — DIO costs nothing at this workload.

`firmware/tools/flash_hub.py --merged` therefore passes `--flash-mode dio` explicitly when it combines
the three images.

Build result: **RAM 14.3 % (46,788 B), flash 77.2 % (1,619,615 B)** of the 2 MB application slot.
(The 13.0 % / 63.6 % quoted in earlier editions predates the cry log, the clock and the Wi-Fi stage;
the 12.9 % / 61.9 % quoted in ones older than that predates the two-cot link fields, the RSSI
plumbing and the heartbeat. Each figure was true when it was printed, which is why the banner, not
this document, is the identity check.)
