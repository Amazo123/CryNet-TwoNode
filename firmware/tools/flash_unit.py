#!/usr/bin/env python3
"""Flash a CryNet unit from the prebuilt images in firmware/prebuilt/.

This is the offline path.  It needs exactly one thing on the machine: the
`esptool` executable.  No Arduino core, no PlatformIO, no compiler, no
network -- so a new hub, a new cot node or a new wearable can be brought
up on a laptop that has never seen this project before.

The images are written region by region, exactly where the partition table
says they go, and **NVS is never written**.  That matters: the node's id
lives in NVS, so this keeps the id that is already on the board (and on a
brand new board leaves it untouched, ready to be set with `id <n>`).

    python firmware/tools/flash_unit.py --role hub     --port COM32
    python firmware/tools/flash_unit.py --role node    --port COM31
    python firmware/tools/flash_unit.py --role wearable --port COM30

    python firmware/tools/flash_unit.py --check
    python firmware/tools/flash_unit.py --list
    python firmware/tools/flash_unit.py --role node --port COM31 --backup

If you change the firmware, rebuild the images with `make_prebuilt.py`
(or the compiler commands in FLASHING.md) and run `--check` again: it
compares the SHA-256 of every image against firmware/prebuilt/SHA256SUMS.

Usage:
    python firmware/tools/flash_unit.py --role hub --port COM32 [--backup]
    python firmware/tools/flash_unit.py --role node --port COM31 [--log 20]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREBUILT = ROOT / "firmware" / "prebuilt"

# role -> the chip it is, and the images to write, in the order they go.
# (file under firmware/prebuilt/<role>/, offset in flash)
ROLES = {
    "hub": {
        "chip": "esp32s3",
        "baud": 921600,
        "flash_size": 0x1000000,       # 16 MB
        "images": [
            ("bootloader.bin", 0x0),
            ("partitions.bin", 0x8000),
            ("firmware.bin", 0x10000),
        ],
    },
    "node": {
        "chip": "esp32c3",
        "baud": 921600,
        "flash_size": 0x400000,         # 4 MB
        "images": [
            ("bootloader.bin", 0x0),
            ("partitions.bin", 0x8000),
            ("boot_app0.bin", 0xe000),
            ("app.bin", 0x10000),
        ],
    },
    "wearable": {
        "chip": "esp32c3",
        "baud": 921600,
        "flash_size": 0x400000,         # 4 MB
        "images": [
            ("bootloader.bin", 0x0),
            ("partitions.bin", 0x8000),
            ("boot_app0.bin", 0xe000),
            ("app.bin", 0x10000),
        ],
    },
}


def find_esptool() -> str | None:
    """The esptool to use: PlatformIO's copy first, then PATH."""
    env = os.environ.get("ESPTOOL")
    if env and Path(env).exists():
        return env
    candidates = [
        Path.home() / ".platformio" / "packages" / "tool-esptool" / "esptool.exe",
        Path.home() / ".platformio" / "packages" / "tool-esptool" / "esptool",
        Path.home() / ".platformio" / "packages" / "tool-esptool-py" / "esptool.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    for name in ("esptool", "esptool.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sums_path() -> Path:
    return PREBUILT / "SHA256SUMS"


def read_sums() -> dict[str, str]:
    """The expected hashes, keyed by the path as written in SHA256SUMS."""
    p = sums_path()
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[1].strip().lstrip("*")] = parts[0].lower()
    return out


def role_dir(role: str) -> Path:
    return PREBUILT / role


def role_images(role: str) -> list[tuple[Path, int]]:
    spec = ROLES[role]
    out = []
    for name, offset in spec["images"]:
        out.append((role_dir(role) / name, offset))
    return out


def check(role: str | None) -> int:
    """Everything the offline path needs, and nothing else."""
    print("== toolchain ==")
    esptool = find_esptool()
    if esptool:
        print(f"  esptool     OK   {esptool}")
    else:
        print("  esptool     MISSING  (looked in ~/.platformio/packages/"
              "tool-esptool and on PATH; set ESPTOOL to override)")
    try:
        import serial  # noqa: F401
        print("  pyserial    OK")
    except ImportError:
        print("  pyserial    MISSING  (pip install pyserial)")

    roles = [role] if role else list(ROLES)
    print("\n== prebuilt images ==")
    expected = read_sums()
    missing = False
    for r in roles:
        print(f"  {r}:")
        for path, offset in role_images(r):
            if not path.is_file():
                print(f"    MISSING  {path.relative_to(ROOT)}")
                missing = True
                continue
            digest = sha256(path)
            want = expected.get(str(path.relative_to(PREBUILT)).replace("\\", "/"))
            if want is None:
                state = "no hash on file"
            elif want == digest:
                state = "hash OK"
            else:
                state = "HASH MISMATCH"
                missing = True
            print(f"    {offset:#08x}  {path.name:<16} {path.stat().st_size:>9} B"
                  f"  {digest[:16]}...  {state}")
    if not expected:
        print("\n  (no SHA256SUMS file -- the images are unverified)")
    return 1 if missing else 0


def list_ports() -> int:
    try:
        import serial.tools.list_ports as list_ports
    except ImportError:
        print("pyserial is not installed: pip install pyserial", file=sys.stderr)
        return 1
    found = False
    for p in list_ports.comports():
        found = True
        print(f"{p.device:<8} {p.description:<40} vid={p.vid} pid={p.pid}")
    if not found:
        print("no serial ports found")
    return 0


def backup(esptool: str, role: str, port: str) -> int:
    spec = ROLES[role]
    dest = Path(os.environ.get("TEMP", ".")) / f"crynet_backup_{role}_{port}.bin"
    cmd = [esptool, "--chip", spec["chip"], "--port", port,
           "read-flash", "0x0", hex(spec["flash_size"]), str(dest)]
    print("backing up:", " ".join(cmd))
    if subprocess.run(cmd).returncode != 0:
        print("the backup failed; not flashing anything", file=sys.stderr)
        return 1
    print(f"backup written to {dest}")
    return 0


def capture_log(port: str, seconds: float) -> None:
    """Reset the board over RTS/EN and print what it says at boot."""
    try:
        import serial
    except ImportError:
        print("pyserial is not installed: cannot read the boot log", file=sys.stderr)
        return
    print(f"\nListening on {port} for {seconds:.0f} s ...")
    try:
        ser = serial.Serial(port, 115200, timeout=0.2)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot open {port}: {exc}", file=sys.stderr)
        return
    with ser:
        ser.dtr = False
        ser.rts = True          # pulse EN so the boot log is captured
        time.sleep(0.15)
        ser.rts = False
        deadline = time.time() + seconds
        while time.time() < deadline:
            chunk = ser.read(4096)
            if chunk:
                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                sys.stdout.flush()
    print("\n--- done ---")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", choices=sorted(ROLES),
                    help="which unit to flash")
    ap.add_argument("--port", help="the unit's serial port, e.g. COM32")
    ap.add_argument("--baud", type=int, default=None, help="flashing baud")
    ap.add_argument("--backup", action="store_true",
                    help="read the whole flash to a file before writing")
    ap.add_argument("--log", type=float, default=0.0, metavar="SECONDS",
                    help="read the boot log for this long after flashing")
    ap.add_argument("--check", action="store_true",
                    help="check the toolchain and the prebuilt images, flash nothing")
    ap.add_argument("--list", action="store_true",
                    help="list the serial ports and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the esptool command and flash nothing")
    args = ap.parse_args()

    if args.list:
        return list_ports()
    if args.check:
        return check(args.role)
    if not args.role or not args.port:
        ap.error("--role and --port are both required to flash "
                 "(a COM number is not an identity -- check the ports with --list)")

    esptool = find_esptool()
    if esptool is None:
        print("esptool not found (looked in ~/.platformio/packages/tool-esptool "
              "and on PATH; set ESPTOOL to override)", file=sys.stderr)
        return 1

    spec = ROLES[args.role]
    images = role_images(args.role)
    for path, _ in images:
        if not path.is_file():
            print(f"missing image {path} -- run --check for the details",
                  file=sys.stderr)
            return 1

    rc = check(args.role)
    print()
    if rc != 0:
        print("the prebuilt images did not check out; not flashing anything",
              file=sys.stderr)
        return 1

    if args.backup:
        rc = backup(esptool, args.role, args.port)
        if rc != 0:
            return rc

    baud = args.baud or spec["baud"]
    cmd = [esptool, "--chip", spec["chip"], "--port", args.port,
           "--baud", str(baud), "write-flash"]
    for path, offset in images:
        cmd += [hex(offset), str(path)]

    print("flashing the", args.role, "on", args.port)
    for path, offset in images:
        print(f"   {offset:#08x}  {path.name}")
    if args.dry_run:
        print("\ndry run -- the command that would run is:\n")
        print("  " + " ".join(cmd))
        return 0
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("the flash failed", file=sys.stderr)
        return result.returncode
    print("\nflash OK")
    if args.log > 0:
        time.sleep(1.0)
        capture_log(args.port, args.log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
