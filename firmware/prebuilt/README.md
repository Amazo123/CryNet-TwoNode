# Prebuilt flash images

The built firmware for all three units, so a board can be flashed **offline** with
`esptool` alone — no Arduino core, no PlatformIO, no compiler, no network.

`FLASHING.md` is the procedure. The short version:

```powershell
python firmware/tools/flash_unit.py --check                                 # verify
python firmware/tools/flash_unit.py --role hub     --port COM32 --log 25    # the hub, first
python firmware/tools/flash_unit.py --role node    --port COM31 --log 15
python firmware/tools/flash_unit.py --role wearable --port COM30 --log 15
```

## What is in here

| Folder | Chip | Files (offset in flash) |
|---|---|---|
| `hub/` | ESP32-S3 | `bootloader.bin` (0x0), `partitions.bin` (0x8000), `firmware.bin` (0x10000) |
| `node/` | ESP32-C3 | `bootloader.bin` (0x0), `partitions.bin` (0x8000), `boot_app0.bin` (0xe000), `app.bin` (0x10000) |
| `wearable/` | ESP32-C3 | the same four |

`SHA256SUMS` holds the SHA-256 of every image. `flash_unit.py --check` compares the
files against it and refuses to flash if anything does not match.

`BUILD_INFO.json` holds the record of what each image was built from: for every unit,
the SHA-256 of every source file that went into it. `check_prebuilt.py` recomputes
those and compares, so a sketch that was edited while the `.bin` files stayed old is
caught before anyone flashes it.

## Keeping them up to date

```powershell
python firmware/tools/check_prebuilt.py     # are the images current with the source?
python firmware/tools/make_prebuilt.py      # rebuild them and refresh the record
```

`flash.bat` runs the same check (in PowerShell, so it needs no Python) before it
writes anything, and refuses to flash an image that is stale or damaged. GitHub runs
it on every push: `.github/workflows/prebuilt-check.yml` rebuilds all three units and
fails if the result differs from what is committed.

## Two rules that matter

**Write the regions, not one merged file.** A merged image fills the gaps between the
regions with `0xFF`, and writing that would **erase NVS** — which is where a node
keeps its id. The offsets above skip NVS on purpose (`0x9000`–`0xE000` on the C3
boards, `0x9000`–`0xF000` on the hub), so a reflash keeps the id.

**The hub images are DIO.** The ROM on the S3 cannot read the flash in QIO before the
bootloader has set up its own timing; a QIO image makes the chip watchdog-reset in a
loop right after power-on. The bootloader header in `hub/bootloader.bin` says DIO.

## Rebuilding them

```powershell
python firmware/tools/make_prebuilt.py
```

That compiles all three from source, rewrites `SHA256SUMS` and writes `BUILD_INFO.json`.
It needs the Arduino core 3.3.12 and, for the hub, the vendored `esp-tflite-micro` and
`esp-nn` components (`bash firmware/tools/fetch_deps.sh`, once, with network).

The hub build is reproducible: rebuilding it produced a `firmware.bin` byte-identical
to the one flashed to the bench units on 2026-11-07.
