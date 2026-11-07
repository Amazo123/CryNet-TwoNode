#!/usr/bin/env python3
"""Watch what a board says over its USB serial port.

This is the CryNet equivalent of the "Serial Monitor" in the Arduino IDE,
so that you can check a board's boot log without having the IDE installed.

It resets the board over RTS/EN and then prints everything the board says,
at 115200 baud, until you press Ctrl+C.

Usage:
    python firmware/tools/serial_monitor.py --port COM31
    python firmware/tools/serial_monitor.py --port COM31 --no-reset
    python firmware/tools/serial_monitor.py --list
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError:  # pragma: no cover
    print("pyserial is not installed: pip install pyserial", file=sys.stderr)
    sys.exit(1)


def show_ports() -> int:
    ports = list(list_ports.comports())
    if not ports:
        print("no serial ports found")
        return 0
    for p in ports:
        print(f"{p.device:<8} {p.description}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="the port to watch, e.g. COM31")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after this long (0 = until Ctrl+C)")
    ap.add_argument("--no-reset", action="store_true",
                    help="do not reset the board first")
    ap.add_argument("--list", action="store_true", help="list the ports and exit")
    args = ap.parse_args()

    if args.list:
        return show_ports()
    if not args.port:
        ap.error("--port is required (use --list to see them)")

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.2)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot open {args.port}: {exc}", file=sys.stderr)
        return 1

    print(f"watching {args.port} at {args.baud} baud -- Ctrl+C to stop")
    deadline = time.time() + args.seconds if args.seconds else None
    with ser:
        if not args.no_reset:
            time.sleep(0.3)
            ser.reset_input_buffer()
            # On an ESP32 the RTS line drives EN, so pulsing it resets the
            # board; DTR drives GPIO0 and is left alone.
            ser.dtr = False
            ser.rts = True
            time.sleep(0.15)
            ser.rts = False
        try:
            while deadline is None or time.time() < deadline:
                chunk = ser.read(4096)
                if chunk:
                    sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
        except KeyboardInterrupt:
            print("\n--- stopped ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
