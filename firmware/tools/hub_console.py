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

Two things about the board make this fiddly, and the tool handles both.

**The board may reboot when the port opens.**  The USB-serial bridge holds
its enable line, so opening the port can reset the hub -- and a command
written into a board that is still booting is a command thrown away,
which looks exactly like a command that was ignored.  So the tool waits
for the console's own banner ("the console is listening") before it
types anything.

**But the banner only appears on a boot.**  If the hub is already
running, it printed the banner before the port was opened and the tool
will never see it.  In that case the tool waits for the board to show
signs of life instead, and then it knows a command landed by the echo
the console prints for every command it receives ("console: << net").
If a command is not echoed, it is sent again -- which is what makes this
safe on a board that was still booting: a command typed too early is
simply echoed late, and only one of them is ever run.

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

# The console echoes every command it receives.
ECHO = "console: <<"


def list_serial_ports() -> int:
    ports = list(list_ports.comports())
    if not ports:
        print("no serial ports found")
        return 0
    for p in ports:
        print(f"{p.device:<10} {p.description}")
    return 0


def read_for(port, seconds: float, sink=None):
    """Read the port for a while, returning (text, saw_ready)."""
    end = time.time() + seconds
    text = ""
    ready = False
    while time.time() < end:
        line = port.readline()
        if not line:
            continue
        chunk = line.decode("utf-8", "replace")
        text += chunk
        if sink is not None:
            sink.write(chunk)
            sink.flush()
        if READY in chunk:
            ready = True
    return text, ready


def send_and_wait_echo(port, command: str, settle: float) -> bool:
    """Send a command and wait for the console to echo it.

    Returns True when the echo was seen.  The command is sent again if
    it was not: on a board that is still booting, the first attempt is
    swallowed and the second lands.
    """
    for attempt in range(3):
        port.write((command + "\n").encode("ascii", "replace"))
        port.flush()
        end = time.time() + settle
        while time.time() < end:
            line = port.readline()
            if not line:
                continue
            text = line.decode("utf-8", "replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            if ECHO in text and command in text:
                return True
    return False


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
        # The board may be booting now.  Wait for the console to say it
        # is ready, so that nothing is typed into a board that is not
        # listening yet.
        deadline = time.time() + args.wait
        ready = False
        alive = False
        while time.time() < deadline:
            line = port.readline()
            if not line:
                continue
            text = line.decode("utf-8", "replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            if READY in text:
                ready = True
                break
            alive = True   # the board is talking, so it is past the boot

        if not ready:
            if not alive:
                print(f"\n[hub-console] the console did not come up on "
                      f"{args.port} within {args.wait:.0f}s", file=sys.stderr)
                return 1
            # The board was already running: its banner was printed
            # before the port opened.  It is alive, so it is listening.
            print("\n[hub-console] the board was already running; "
                  "sending the commands now", file=sys.stderr)

        for command in args.send:
            time.sleep(0.3)
            print(f"> {command}")
            if not send_and_wait_echo(port, command, args.settle):
                print(f"\n[hub-console] {args.port} did not echo "
                      f"{command!r}; it may not have taken it", file=sys.stderr)
                return 1
            # Listen while the board answers, but not for ever: a busy
            # board prints something every second or two, so "until it
            # goes quiet" would never end.
            end = time.time() + 1.0
            hard_end = time.time() + args.settle + 5.0
            while time.time() < end and time.time() < hard_end:
                line = port.readline()
                if line:
                    sys.stdout.write(line.decode("utf-8", "replace"))
                    sys.stdout.flush()
                    end = time.time() + 1.0   # more is coming

    return 0


if __name__ == "__main__":
    sys.exit(main())
