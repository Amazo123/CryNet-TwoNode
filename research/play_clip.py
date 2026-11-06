#!/usr/bin/env python3
"""Play a cry clip on the bench, over and over, while the capture runs.

The node freezes a window about half a second after the sound stops, and
the hub's verdict follows about two seconds after that, so a clip that is
played once can be missed by a freeze that landed on the room's own noise.
The clip is therefore played several times, with a gap long enough for
the previous verdict to arrive.

Usage:
    python research/play_clip.py --clip research/out/demo_kit/session4_clip_0012.wav \\
        --repeats 5 --gap 8
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--gap", type=float, default=8.0,
                    help="seconds between plays (default 8)")
    args = ap.parse_args()

    clip = Path(args.clip).resolve()
    if not clip.exists():
        print(f"no such clip: {clip}", file=sys.stderr)
        return 1

    import winsound

    with wave.open(str(clip), "rb") as w:
        seconds = w.getnframes() / float(w.getframerate())
    print(f"{clip.name}: {seconds:.1f} s, {args.repeats} plays, "
          f"{args.gap:.0f} s apart", flush=True)

    for i in range(args.repeats):
        t0 = time.time()
        winsound.PlaySound(str(clip), winsound.SND_FILENAME)
        print(f"play {i + 1}/{args.repeats} done at t+{time.time() - t0:.1f} s",
              flush=True)
        # the gap is measured from the end of the clip
        rest = args.gap - (time.time() - t0)
        if rest > 0:
            time.sleep(rest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
