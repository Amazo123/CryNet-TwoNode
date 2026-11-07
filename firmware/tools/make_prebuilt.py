#!/usr/bin/env python3
"""Rebuild the prebuilt flash images in firmware/prebuilt/ from the source.

You only need this when you change the firmware.  Flashing a unit never
needs it -- the images are in the repository, so `flash_unit.py` works on
a machine that has never compiled anything.

What it does, per role:

  hub       PlatformIO / ESP-IDF build of firmware/hub_infer
            (needs the vendored esp-tflite-micro and esp-nn components --
             `bash firmware/tools/fetch_deps.sh` once, which needs network)

  node      arduino-cli compile of firmware/node/node_crynet
  wearable  arduino-cli compile of firmware/wearable/wearable_crynet
            (needs the ESP32 core, already installed)

It then writes firmware/prebuilt/SHA256SUMS, which `flash_unit.py --check`
verifies before every flash, and firmware/prebuilt/BUILD_INFO.json, which
records which source each unit was built from -- that is what
`check_prebuilt.py` uses to prove the shipped images are still up to date.

    python firmware/tools/make_prebuilt.py                # everything
    python firmware/tools/make_prebuilt.py --role node
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prebuilt_lib  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PREBUILT = ROOT / "firmware" / "prebuilt"
BUILD = ROOT / "firmware" / ".build"

FQBN = "esp32:esp32:weact_studio_esp32c3"

SKETCHES = {
    "node": ("node", "node_crynet"),
    "wearable": ("wearable", "wearable_crynet"),
}


def find_arduino_cli() -> str | None:
    env = os.environ.get("ARDUINO_CLI")
    if env and Path(env).exists():
        return env
    found = shutil.which("arduino-cli") or shutil.which("arduino-cli.exe")
    if found:
        return found
    for c in [Path.home() / "AppData/Local/Programs/Arduino IDE/resources/app/"
                             "lib/backend/resources/arduino-cli.exe",
              Path("/Applications/Arduino IDE.app/Contents/Resources/app/lib/"
                   "backend/resources/arduino-cli")]:
        if c.exists():
            return str(c)
    return None


def find_platformio() -> str | None:
    env = os.environ.get("PLATFORMIO")
    if env and Path(env).exists():
        return env
    found = shutil.which("platformio") or shutil.which("platformio.exe")
    if found:
        return found
    for c in [Path.home() / ".platformio/penv/Scripts/platformio.exe",
              Path.home() / ".platformio/penv/bin/platformio"]:
        if c.exists():
            return str(c)
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_hub() -> int:
    pio = find_platformio()
    if pio is None:
        print("platformio not found (looked on PATH and in "
              "~/.platformio/penv/Scripts)", file=sys.stderr)
        return 1
    project = ROOT / "firmware" / "hub_infer"
    for dep in ("esp-tflite-micro", "esp-nn"):
        if not (project / "components" / dep).is_dir():
            print(f"missing components/{dep} -- run "
                  f"`bash firmware/tools/fetch_deps.sh` once (needs network)",
                  file=sys.stderr)
            return 1
    print("building the hub with PlatformIO (this takes a few minutes) ...")
    rc = subprocess.run([pio, "run"], cwd=project).returncode
    if rc != 0:
        return rc
    built = project / ".pio" / "build" / "esp32s3"
    out = PREBUILT / "hub"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("bootloader.bin", "partitions.bin", "firmware.bin"):
        src = built / name
        if not src.is_file():
            print(f"the build did not produce {name}", file=sys.stderr)
            return 1
        shutil.copy2(src, out / name)
        print(f"  {name}")
    return 0


def build_sketch(role: str) -> int:
    cli = find_arduino_cli()
    if cli is None:
        print("arduino-cli not found (install the Arduino IDE, or set "
              "ARDUINO_CLI to the binary)", file=sys.stderr)
        return 1
    folder, name = SKETCHES[role]
    sketch = ROOT / "firmware" / folder / name
    if not (sketch / f"{name}.ino").is_file():
        print(f"missing {sketch / (name + '.ino')}", file=sys.stderr)
        return 1
    build_path = BUILD / role
    build_path.mkdir(parents=True, exist_ok=True)
    # -j 1: the parallel build runs out of memory on a 16 GB machine.
    print(f"building the {role} with arduino-cli ...")
    cmd = [cli, "compile", "-j", "1", "--fqbn", FQBN,
           "--build-path", str(build_path), str(sketch)]
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        return rc
    out = PREBUILT / role
    out.mkdir(parents=True, exist_ok=True)
    wanted = {
        "bootloader.bin": build_path / f"{name}.ino.bootloader.bin",
        "partitions.bin": build_path / f"{name}.ino.partitions.bin",
        "boot_app0.bin": build_path / "boot_app0.bin",
        "app.bin": build_path / f"{name}.ino.bin",
    }
    for out_name, src in wanted.items():
        if not src.is_file():
            print(f"the build did not produce {src.name}", file=sys.stderr)
            return 1
        shutil.copy2(src, out / out_name)
        print(f"  {out_name}")
    return 0


def tool_versions() -> dict[str, str]:
    """What built these images, so the record says."""
    versions: dict[str, str] = {}
    pio = find_platformio()
    if pio:
        try:
            out = subprocess.run([pio, "--version"], capture_output=True,
                                 timeout=60, check=False)
            if out.returncode == 0:
                versions["platformio"] = out.stdout.decode().strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            pass
    cli = find_arduino_cli()
    if cli:
        try:
            out = subprocess.run([cli, "version"], capture_output=True,
                                 timeout=60, check=False)
            if out.returncode == 0:
                versions["arduino-cli"] = out.stdout.decode().strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            pass
    versions["fqbn"] = FQBN
    return versions


def write_sums() -> None:
    lines = [
        "# SHA-256 of the prebuilt flash images.",
        "# Verify them with: python firmware/tools/flash_unit.py --check",
        "",
    ]
    for path in sorted(PREBUILT.rglob("*.bin")):
        rel = path.relative_to(PREBUILT).as_posix()
        lines.append(f"{sha256(path)}  {rel}")
    (PREBUILT / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    print(f"wrote {PREBUILT / 'SHA256SUMS'}")


def write_build_info() -> None:
    """Record which source each unit was built from.

    All three units are recorded, not only the ones just built: a partial
    rebuild must not drop the record of the others.
    """
    path = prebuilt_lib.write_build_info(tools=tool_versions())
    print(f"wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", choices=["hub", "node", "wearable"],
                    help="build only this one (default: all three)")
    args = ap.parse_args()

    roles = [args.role] if args.role else ["hub", "node", "wearable"]
    for role in roles:
        print(f"== {role} ==")
        rc = build_hub() if role == "hub" else build_sketch(role)
        if rc != 0:
            return rc
        print()

    write_sums()
    write_build_info()
    return 0


if __name__ == "__main__":
    sys.exit(main())
