#!/usr/bin/env python3
"""Talk to the CryNet hub's serial console.

The hub listens for one-line commands at 115200 baud and prints its state
in reply:

    help          the list of commands
    status        the cots and what they are hearing
    alert <cot>   publish a test alert for that cot
    clear         take the test alert back
    history [n]   the last n records, newest first
    log           how much is recorded and how much is unsent
    log clear     throw the log away
    net           the network and what it has sent
    net set <url> where to post the records
    net ssid <s> <p>  which Wi-Fi to join
    net name <name>   this hub's name on the dashboard
    net token <t>     the dashboard's shared secret
    upload        send the unsent records now
    logtest       prove, on this chip, that out-of-order records are not lost

Opening the port resets the board -- the USB-serial bridge holds its
enable line -- so the board is booting for a few seconds every time this
runs.  That is why the tool waits for the console to announce itself
before sending anything: a command written into a booting board is a
command thrown away, which looks exactly like a command that was ignored.

Usage:
    python firmware/tools/hub_console.py --port COM32 --send status
    python firmware/tools/hub_console.py --port COM32 --send log --send history 5
    python firmware/tools/hub_console.py --port COM32 --send "net set https://x/api/v1/events"
    python firmware/tools/hub_console.py --list
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


# The console says this when it is ready for commands.
READY = "the console is listening"


def list_serial_ports() -> int:
    ports = list(list_ports.comports())
    if not ports:
        print("no serial ports found")
        return 0
    for p in ports:
        print(f"{p.device:<10} {p.description}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM32", help="the hub's serial port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--send", action="append", default=[],
                    help="a console command to send (repeatable)")
    ap.add_argument("--settle", type=float, default=2.5,
                    help="seconds to listen after each command")
    ap.add_argument("--wait", type=float, default=20.0,
                    help="seconds to wait for the console to come up")
    ap.add_argument("--list", action="store_true", help="list the serial ports")
    args = ap.parse_args()

    if args.list:
        return list_serial_ports()

    try:
        port = serial.Serial(args.port, args.baud, timeout=0.2)
    except serial.SerialException as exc:
        print(f"cannot open {args.port}: {exc}", file=sys.stderr)
        return 1

    with port:
        # The board is booting.  Wait for the console to say it is ready,
        # so that nothing is typed into a board that is not listening.
        deadline = time.time() + args.wait
        ready = False
        while time.time() < deadline:
            line = port.readline()
            if line:
                text = line.decode("utf-8", "replace")
                sys.stdout.write(text)
                sys.stdout.flush()
                if READY in text:
                    ready = True
                    break
        if not ready:
            print(f"\n[hub-console] the console did not come up on "
                  f"{args.port} within {args.wait:.0f}s", file=sys.stderr)
            return 1

        for command in args.send:
            time.sleep(0.3)
            print(f"> {command}")
            port.write((command + "\n").encode("ascii", "replace"))
            port.flush()
            # Listen until the board goes quiet for a moment.
            end = time.time() + args.settle
            while time.time() < end:
                line = port.readline()
                if line:
                    sys.stdout.write(line.decode("utf-8", "replace"))
                    sys.stdout.flush()
                    end = time.time() + 1.0   # more is coming

    return 0


if __name__ == "__main__":
    sys.exit(main())
