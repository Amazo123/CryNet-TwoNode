"""The rules that decide what goes into each prebuilt image.

`firmware/prebuilt/BUILD_INFO.json` is written when the images are built.
It records, for each unit:

  * which source files went into it, and the SHA-256 of each one,
  * the rules used to find those files, so the same question can be asked
    later by another tool (the PowerShell check, or CI) without this
    module;
  * the SHA-256 of every image that was produced.

The rules are written into the file on purpose.  A check that has to know
the rules must be able to read them from somewhere, and reading them from
the record it is checking is the only way to be sure the two agree.

Everything here is deliberately machine-independent:

  * only files that belong to the unit are included (no build output);
  * text files are hashed with their line endings normalised to LF, so a
    clone that checked out CRLF gives the same answer as one that did not;
  * binary files are hashed as they are.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREBUILT = ROOT / "firmware" / "prebuilt"
BUILD_INFO = PREBUILT / "BUILD_INFO.json"

# Where the build was made and by what.  Kept out of BUILD_INFO.json on
# purpose: that file must be the same on every machine, so that CI can
# rebuild and compare it byte for byte.  This one is local only and is
# not committed.
BUILD_STATE = PREBUILT / ".build-state.json"

# role -> (directories that hold its source, extra files it also depends on)
ROLE_SOURCES: dict[str, tuple[list[Path], list[Path]]] = {
    # The hub is ESP-IDF.  The two vendored components (esp-tflite-micro,
    # esp-nn) are not in the repository -- they are pinned by revision in
    # fetch_deps.sh, so that file is part of the hub's fingerprint.
    "hub": (
        [ROOT / "firmware" / "hub_infer"],
        [ROOT / "firmware" / "tools" / "fetch_deps.sh",
         ROOT / "firmware" / "tools" / "patch_deps.py"],
    ),
    "node": (
        [ROOT / "firmware" / "node" / "node_crynet"],
        [],
    ),
    "wearable": (
        [ROOT / "firmware" / "wearable" / "wearable_crynet"],
        [],
    ),
}

# The rules, in a form that another tool can read straight out of the
# record.  Keep them here and in one place.
RULES: dict[str, object] = {
    # Directories that hold build output or vendored clones, not source.
    "exclude_dirs": [
        ".pio", "build", "managed_components", ".git", "__pycache__",
        "esp-tflite-micro", "esp-nn",
    ],
    # Files the IDEs write into the tree.  They are git-ignored, so a git
    # checkout never sees them; but a copy unpacked from a zip does, and
    # they must not change the answer.
    "exclude_names": [
        "c_cpp_properties.json", "launch.json", "ipch",
    ],
    # Name patterns to skip ...
    "exclude_globs": [
        "sdkconfig*", ".browse.c_cpp.db*",
    ],
    # ... except these, which are part of the build.
    "keep_globs": [
        "sdkconfig.defaults",
    ],
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalise(data: bytes) -> bytes:
    """Line-ending-normalise text; leave binary alone."""
    if b"\x00" in data:
        return data
    return data.replace(b"\r\n", b"\n")


def file_hash(path: Path) -> str:
    """The hash of a source file, the same on every machine."""
    return sha256_bytes(normalise(path.read_bytes()))


def _git_tracked(paths: list[Path]) -> set[str] | None:
    """The tracked files under `paths`, as repo-relative POSIX paths.

    Returns None when git cannot answer (not a repository, git missing),
    so the caller falls back to walking the tree.
    """
    rels = []
    for p in paths:
        try:
            rels.append(p.relative_to(ROOT).as_posix())
        except ValueError:
            return None
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", *rels],
            capture_output=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    files = {n for n in out.stdout.decode("utf-8", "replace").split("\0") if n}
    return files or None


def _excluded(path: Path, base: Path, rules: dict) -> bool:
    rel_parts = path.relative_to(base).parts
    if any(part in rules["exclude_dirs"] for part in rel_parts[:-1]):
        return True
    name = path.name
    if name in rules["exclude_names"]:
        return True
    for pattern in rules["exclude_globs"]:
        if fnmatch.fnmatch(name, pattern):
            for keep in rules["keep_globs"]:
                if fnmatch.fnmatch(name, keep):
                    return False
            return True
    return False


def source_files(role: str, rules: dict | None = None) -> list[str]:
    """The repo-relative files that make up a unit, sorted."""
    rules = rules or RULES
    dirs, extras = ROLE_SOURCES[role]
    tracked = _git_tracked(dirs)
    found: set[str] = set()

    for base in dirs:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if _excluded(path, base, rules):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if tracked is not None and rel not in tracked:
                continue
            found.add(rel)

    for extra in extras:
        if extra.is_file():
            found.add(extra.relative_to(ROOT).as_posix())

    return sorted(found)


def file_hashes(role: str, rules: dict | None = None) -> dict[str, str]:
    """The hash of every source file of a unit, keyed by repo-relative path."""
    return {rel: file_hash(ROOT / rel)
            for rel in source_files(role, rules)}


def fingerprint(hashes: dict[str, str]) -> str:
    """One hash for a whole unit's source."""
    h = hashlib.sha256()
    for rel, digest in sorted(hashes.items()):
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(digest.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def git_state() -> dict[str, str]:
    """Which commit the working tree is at, and whether it is dirty."""
    state: dict[str, str] = {"commit": "unknown", "branch": "unknown", "dirty": "?"}
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, timeout=30, check=False)
        if out.returncode == 0:
            state["commit"] = out.stdout.decode().strip()
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, timeout=30, check=False)
        if out.returncode == 0:
            state["branch"] = out.stdout.decode().strip()
        out = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain",
                              "--", "firmware"],
                             capture_output=True, timeout=60, check=False)
        if out.returncode == 0:
            state["dirty"] = "yes" if out.stdout.strip() else "no"
    except (OSError, subprocess.SubprocessError):
        pass
    return state


def image_hashes(role: str) -> dict[str, str]:
    """Hash of every built image of a unit, keyed by file name."""
    folder = PREBUILT / role
    if not folder.is_dir():
        return {}
    return {p.name: sha256_file(p) for p in sorted(folder.glob("*.bin"))}


def write_build_info(roles: list[str] | None = None,
                     tools: dict[str, str] | None = None) -> Path:
    """Write BUILD_INFO.json for the units that were just built.

    All three units are recorded, not only the ones just built: a partial
    rebuild must not drop the record of the others.

    BUILD_INFO.json holds nothing that varies from machine to machine, so
    that CI can rebuild and compare it byte for byte.  Where the build
    happened and with which tools goes in .build-state.json, which is
    local only.
    """
    roles = sorted(roles or ROLE_SOURCES)
    per_role: dict[str, object] = {}
    for role in roles:
        hashes = file_hashes(role)
        per_role[role] = {
            "roots": [p.relative_to(ROOT).as_posix() for p in ROLE_SOURCES[role][0]],
            "extras": [p.relative_to(ROOT).as_posix() for p in ROLE_SOURCES[role][1]],
            "files": hashes,
            "source_fingerprint": fingerprint(hashes),
            "images": image_hashes(role),
        }
    info: dict[str, object] = {
        "schema": 2,
        "rules": RULES,
        "roles": per_role,
    }
    BUILD_INFO.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")

    state = {
        "git": git_state(),
        "tools": tools or {},
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    BUILD_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return BUILD_INFO


def read_build_info() -> dict:
    if not BUILD_INFO.is_file():
        return {}
    try:
        return json.loads(BUILD_INFO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
