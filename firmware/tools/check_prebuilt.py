#!/usr/bin/env python3
"""Prove that the offline flash images still match the firmware source.

The images in `firmware/prebuilt/` are what a unit is flashed with, offline,
with nothing but `esptool`.  Nothing forces them to stay in step with the
source -- a `.ino` can be edited and committed while the `.bin` files stay
old -- and the result would be a board running code that is not in the
repository.  This is the check that catches it.

Two things are checked:

  1. the images match `firmware/prebuilt/SHA256SUMS` (they are intact);
  2. the source that produced them is still the source in the tree
     (they are up to date).

The second one works from the record that `make_prebuilt.py` wrote:
`firmware/prebuilt/BUILD_INFO.json` holds, for each unit, the hash of
every source file that went into it and the rules used to find those
files.  The check recomputes them and compares.  It is the same on every
machine -- text files are hashed with their line endings normalised, so a
clone that checked out CRLF gives the same answer as one that did not.

    python firmware/tools/check_prebuilt.py        # check
    python firmware/tools/check_prebuilt.py --quiet

Exit code 0 = everything is in step, 1 = something is not.

If it says the images are stale, rebuild them and commit the result:

    python firmware/tools/make_prebuilt.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prebuilt_lib import (  # noqa: E402
    BUILD_INFO,
    PREBUILT,
    ROOT,
    file_hashes,
    fingerprint,
    image_hashes,
    read_build_info,
    sha256_file,
)

ROLES = ("hub", "node", "wearable")


def read_sums() -> dict[str, str]:
    """The expected hashes, keyed by the path as written in SHA256SUMS."""
    sums = PREBUILT / "SHA256SUMS"
    if not sums.is_file():
        return {}
    out: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        out[parts[1].strip().replace("\\", "/")] = parts[0].strip().lower()
    return out


def check_images(quiet: bool) -> list[str]:
    """Every image on disk matches SHA256SUMS, and vice versa."""
    problems: list[str] = []
    expected = read_sums()
    if not expected:
        return ["SHA256SUMS is missing or empty - the images cannot be verified"]

    on_disk = {p.relative_to(PREBUILT).as_posix() for p in PREBUILT.rglob("*.bin")}
    for rel in sorted(set(expected) - on_disk):
        problems.append(f"missing image: {rel}")
    for rel in sorted(on_disk - set(expected)):
        problems.append(f"image on disk but not in SHA256SUMS: {rel}")

    for rel, want in sorted(expected.items()):
        path = PREBUILT / rel
        if not path.is_file():
            continue
        got = sha256_file(path)
        if got != want:
            problems.append(f"damaged image: {rel}\n"
                            f"    expected {want}\n"
                            f"    got      {got}")
    if not problems and not quiet:
        print(f"  images: {len(expected)} files, all match SHA256SUMS")
    return problems


def check_source(quiet: bool) -> list[str]:
    """Each unit's source is the source its images were built from."""
    problems: list[str] = []
    info = read_build_info()
    if not info:
        return ["BUILD_INFO.json is missing - the images do not say which "
                "source they came from.\n"
                "    rebuild them:  python firmware/tools/make_prebuilt.py"]

    rules = info.get("rules")
    recorded = info.get("roles", {})
    for role in ROLES:
        entry = recorded.get(role)
        if not isinstance(entry, dict):
            problems.append(f"{role}: BUILD_INFO.json has no record of this unit")
            continue

        # The source may not be here.  The prebuilt folder is meant to be
        # copyable on its own -- onto a laptop with just esptool on it --
        # and then there is nothing to compare against.  That is not a
        # fault; it just means this check cannot be made.
        roots = [ROOT / r for r in (entry.get("roots") or [])]
        if not roots or not all(r.is_dir() for r in roots):
            if not quiet:
                print(f"  {role:<9} source not here - freshness not checked")
            continue

        want = entry.get("source_fingerprint")
        hashes = file_hashes(role, rules)
        got = fingerprint(hashes)
        if want != got:
            # name the files that moved, so the message says what to look at
            old = entry.get("files") or {}
            added = sorted(set(hashes) - set(old))
            removed = sorted(set(old) - set(hashes))
            changed = sorted(rel for rel in set(old) & set(hashes)
                             if old[rel] != hashes[rel])
            detail = []
            for rel in changed:
                detail.append(f"      changed  {rel}")
            for rel in added:
                detail.append(f"      added    {rel}")
            for rel in removed:
                detail.append(f"      removed  {rel}")
            problems.append(
                f"{role}: the source has changed since these images were built\n"
                f"    built from {str(want)[:16]}... over {len(old)} files\n"
                f"    source now  {got[:16]}... over {len(hashes)} files\n"
                + ("\n".join(detail) + "\n" if detail else "")
                + "    rebuild:     python firmware/tools/make_prebuilt.py")
            continue

        # the recorded image hashes must still be the images on disk
        for name, h in (entry.get("images") or {}).items():
            path = PREBUILT / role / name
            if not path.is_file():
                problems.append(f"{role}: {name} is gone")
            elif sha256_file(path) != h:
                problems.append(f"{role}: {name} has changed since it was built")
        if not quiet:
            print(f"  {role:<9} source fingerprint {got[:16]}... over "
                  f"{len(hashes)} files - up to date")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true",
                    help="only print problems")
    args = ap.parse_args()

    if not args.quiet:
        print("== the offline images vs the source ==")

    problems = check_images(args.quiet) + check_source(args.quiet)

    if problems:
        print()
        print("NOT IN STEP")
        for p in problems:
            print(f"  - {p}")
        print()
        print("Fix it by rebuilding the images and committing them:")
        print("    python firmware/tools/make_prebuilt.py")
        return 1

    if not args.quiet:
        print()
        print(f"OK  the offline images are up to date with the source "
              f"({BUILD_INFO.relative_to(ROOT)} records the build)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
