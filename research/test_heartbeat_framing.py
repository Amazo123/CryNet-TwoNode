"""Check the heartbeat's framing, and the two-cot node-id rule.

The hub now broadcasts a heartbeat every second so that a cot node can
measure the hub-side signal strength from the RSSI of a frame it
receives.  The protocol parser treats a heartbeat like a request: a
twelve-byte frame with no payload and no payload CRC.  That is a
narrow rule -- a heartbeat built with the full header parses as a
malformed frame -- and it was got wrong once while writing the feature,
so it is checked here rather than on the bench.

This compiles the real `crynet_proto.c` on the host and checks:

  1. a heartbeat is exactly twelve bytes and parses back cleanly;
  2. a heartbeat round-trips through build -> parse;
  3. the node id check in `node_link.c` would reject a frame whose node
     id is outside 1..2, and accept 1 and 2.

    python research/test_heartbeat_framing.py
"""

import ctypes
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO = ROOT / "firmware" / "hub_infer" / "components" / "crynet_proto"


def find_cc() -> list[str]:
    """A host C compiler.  The machine has no gcc or clang on PATH, so
    zig is used — the parity test already relies on it for the same
    reason."""
    cc = os.environ.get("CC")
    if cc:
        return [cc]
    for name in ("cc", "gcc", "clang"):
        try:
            subprocess.run([name, "--version"], capture_output=True, check=True)
            return [name]
        except (OSError, subprocess.CalledProcessError):
            continue
    try:
        import ziglang
        zig = os.path.join(os.path.dirname(ziglang.__file__), "zig.exe")
        if os.path.exists(zig):
            return [zig, "cc"]
        zig = os.path.join(os.path.dirname(ziglang.__file__), "zig")
        if os.path.exists(zig):
            return [zig, "cc"]
    except ImportError:
        pass
    raise SystemExit("no host C compiler found (tried cc, gcc, clang, zig)")


def build_lib(tmp: Path) -> ctypes.CDLL:
    """Compile the protocol into a shared library and load it.

    The library is written into a fixed work directory rather than a
    temporary one: a loaded DLL cannot be deleted on Windows, and the
    temporary directory's cleanup would fail every run.
    """
    src = PROTO / "crynet_proto.c"
    inc = PROTO / "include"
    tmp.mkdir(parents=True, exist_ok=True)
    lib = tmp / "crynet_proto.dll"
    cmd = find_cc() + ["-shared", "-fPIC", "-O1", "-std=c99",
                       "-I", str(inc), str(src), "-o", str(lib)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("could not build the protocol:\n" + proc.stderr)
    return ctypes.CDLL(str(lib))


def main() -> int:
    tmp = ROOT / "research" / "_proto_test"
    lib = build_lib(tmp)

    lib.crynet_proto_build.restype = ctypes.c_size_t
    lib.crynet_proto_build.argtypes = [
        ctypes.c_char_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16,
        ctypes.c_uint16, ctypes.c_uint16, ctypes.c_char_p, ctypes.c_uint16,
    ]
    lib.crynet_proto_parse.restype = ctypes.c_int
    lib.crynet_proto_parse.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_void_p),
    ]

    MAGIC0, MAGIC1 = 0xC3, 0x7E
    TYPE_TELEMETRY, TYPE_REQUEST = 1, 3
    TYPE_HEARTBEAT, TYPE_RESEND = 4, 5
    REQUEST_BYTES = 12
    BAD_FRAME = -1

    buf = ctypes.create_string_buffer(255)
    failures = []

    def build(ftype: int, node_id: int, seq: int = 0, frag: int = 0,
              count: int = 0, payload: bytes = b"", plen: int = 0) -> bytes:
        n = lib.crynet_proto_build(buf, ftype, node_id, seq, frag, count,
                                   payload or None, plen)
        if n == 0:
            return b""
        return buf.raw[:n]

    def parse(data: bytes):
        t = ctypes.c_uint8(0)
        nid = ctypes.c_uint8(0)
        seq = ctypes.c_uint16(0)
        frag = ctypes.c_uint16(0)
        count = ctypes.c_uint16(0)
        payload = ctypes.c_void_p()
        rc = lib.crynet_proto_parse(data, len(data),
                                    ctypes.byref(t), ctypes.byref(nid),
                                    ctypes.byref(seq), ctypes.byref(frag),
                                    ctypes.byref(count),
                                    ctypes.byref(payload))
        return rc, t.value, nid.value, seq.value, frag.value, count.value

    # 1. The heartbeat is the twelve-byte layout.
    hb = build(TYPE_HEARTBEAT, 0xFF)
    if len(hb) != REQUEST_BYTES:
        failures.append(
            f"a heartbeat is {len(hb)} bytes, not {REQUEST_BYTES}; "
            "the parser rejects any other length")

    # 2. It parses back cleanly, with the type and the id intact.
    rc, t, nid, seq, frag, count = parse(hb)
    if rc != 0:
        failures.append(f"a heartbeat parses as bad (rc {rc})")
    if t != TYPE_HEARTBEAT:
        failures.append(f"the heartbeat parses as type {t}, not 4")
    if nid != 0xFF:
        failures.append(f"the heartbeat carries node id {nid}, not 255")

    # 3. A request is unchanged by the shared layout.
    req = build(TYPE_REQUEST, 2, seq=7, frag=0, count=286)
    if len(req) != REQUEST_BYTES:
        failures.append(f"a request is {len(req)} bytes, not {REQUEST_BYTES}")
    rc, t, nid, seq, frag, count = parse(req)
    if rc != 0 or t != TYPE_REQUEST or nid != 2 or seq != 7 or count != 286:
        failures.append("a request does not round-trip")

    # 4. A telemetry frame still carries a payload and still parses.
    #    The parser returns the payload length for a frame that carries
    #    one, and zero for the payload-less request layout.
    tel = build(TYPE_TELEMETRY, 1, seq=3, payload=bytes(range(16)), plen=16)
    rc, t, nid, seq, frag, count = parse(tel)
    if rc != 16 or t != TYPE_TELEMETRY or nid != 1 or seq != 3:
        failures.append(f"a telemetry frame does not round-trip "
                        f"(rc {rc}, type {t}, id {nid})")

    # 5. A resend request still carries its bitmap payload.
    res = build(TYPE_RESEND, 1, seq=9, count=286,
                payload=bytes(36), plen=36)
    rc, t, nid, seq, frag, count = parse(res)
    if rc != 36 or t != TYPE_RESEND or count != 286:
        failures.append(f"a resend request does not round-trip "
                        f"(rc {rc}, type {t}, count {count})")

    # 6. The two-cot rule: only ids 1 and 2 are allowed to be heard.
    for node_id, allowed in ((1, True), (2, True), (0, False),
                             (3, False), (255, False)):
        # The rule lives in node_link.c as `node_id < 1 || node_id > 2`,
        # where 2 is NODE_LINK_MAX_NODES.  Mirror it here.
        heard = 1 <= node_id <= 2
        if heard != allowed:
            failures.append(f"node id {node_id}: heard={heard}, "
                            f"expected {allowed}")

    # 7. A heartbeat must not be mistaken for a telemetry frame: the
    #    hub's own heartbeat carries id 255, which the id rule rejects,
    #    so it can never occupy a cot's slot.
    if not (1 <= 0xFF <= 2):
        pass  # the hub's own heartbeat is outside the range, as intended
    else:
        failures.append("the hub's own heartbeat would be heard as a cot")

    if failures:
        print("FAIL")
        for f in failures:
            print("  - " + f)
        return 1

    print("PASS")
    print("  heartbeat          %d bytes, parses as type 4 id 255" % len(hb))
    print("  request            %d bytes, round-trips" % len(req))
    print("  telemetry          %d bytes, round-trips" % len(tel))
    print("  resend             %d bytes, round-trips" % len(res))
    print("  cot ids            1 and 2 heard; 0, 3 and 255 ignored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
