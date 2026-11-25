"""A host-side preview of the hub's display.

This script is the design loop for the panel: it draws the screen the
firmware draws, on the host, in a second, so the layout can be looked at
and changed without flashing the board.

It reads three things out of the firmware, so the preview cannot quietly
drift away from what the hardware shows:

  * firmware/hub_infer/components/hub_display/font5x7.h  - the glyphs
  * firmware/hub_infer/components/hub_display/hub_display.c - the palette
    and the layout constants
  * the page layouts below, which mirror the drawing code in hub_display.c
    one for one.  When the firmware's layout changes, change it here too.

Run:  python research/ui_mock.py     ->  research/out/ui_*.png
"""
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DISPLAY_DIR = ROOT / "firmware" / "hub_infer" / "components" / "hub_display"
OUT = ROOT / "research" / "out"

W, H = 320, 240

# The crying colour as the panel reads it.  The framebuffer sends C_ALERT,
# a rose, but this glass lifts the blue channel hardest (Chapter 14), and
# on the panel the alert reads purple; the owner reads it purple too, so
# the preview draws what the panel looks like, not what the frame holds.
PURPLE = (167, 139, 250)


# ---------------------------------------------------------------- the font
def load_font() -> dict[str, list[int]]:
    """The 5x7 glyphs, as columns of seven rows.

    The data is Adafruit's glcdfont, in which **bit 0 is the top row**
    and the glyphs use rows 0..6.  Adafruit_GFX::drawChar reads the
    bytes the same way - `for (j = 0; j < 8; j++, line >>= 1) if (line
    & 1)` - so bit 0 is the first row drawn.  Reading bit 7 as the top
    row instead turns every glyph upside down, which is what the first
    photograph of the panel showed.
    """
    txt = (DISPLAY_DIR / "font5x7.h").read_text(encoding="utf-8")
    body = txt.split("s_font5x7[][5] = {", 1)[1].split("};", 1)[0]
    out: dict[str, list[int]] = {}
    for i, row in enumerate(re.findall(r"\{([^}]*)\}", body)):
        vals = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{2})", row)]
        out[chr(0x20 + i)] = vals
    return out


FONT = load_font()
FONT_H = 7


def text_width(s: str, scale: int = 1) -> int:
    if not s:
        return 0
    return len(s) * 6 * scale - scale


def draw_text(d: ImageDraw.ImageDraw, x: int, y: int, s: str, colour, scale: int = 1):
    cursor = x
    for ch in s:
        glyph = FONT.get(ch, FONT["?"])
        for col in range(5):
            bits = glyph[col]
            for row in range(FONT_H):
                if bits & (1 << row):
                    d.rectangle(
                        [cursor + col * scale, y + row * scale,
                         cursor + col * scale + scale - 1, y + row * scale + scale - 1],
                        fill=colour)
        cursor += 6 * scale
    return cursor


def draw_text_centre(d, y: int, s: str, colour, scale: int = 1):
    draw_text(d, (W - text_width(s, scale)) // 2, y, s, colour, scale)


# ------------------------------------------------------------ the palette
def load_palette() -> dict[str, tuple]:
    """The colours, read out of the firmware so the two cannot drift."""
    txt = (DISPLAY_DIR / "hub_display.c").read_text(encoding="utf-8")
    out = {}
    for name, r, g, b in re.findall(
            r"#define\s+(C_\w+)\s+DISPLAY_RGB\((\d+),\s*(\d+),\s*(\d+)\)", txt):
        out[name] = (int(r), int(g), int(b))
    if not out:
        raise SystemExit("no palette found in hub_display.c")
    return out


def load_layout() -> dict[str, int]:
    txt = (DISPLAY_DIR / "hub_display.c").read_text(encoding="utf-8")
    out = {}
    for name, value in re.findall(r"#define\s+(\w+)\s+(\d+)\b", txt):
        out[name] = int(value)
    return out


def blend(a, b, t):
    """The firmware blends in RGB565; this is close enough to preview."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ---------------------------------------------------------------- drawing
def fill(d, x, y, w, h, colour):
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=colour)


def rect(d, x, y, w, h, colour):
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=colour)


def round_fill(d, x, y, w, h, r, colour):
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, fill=colour)


def round_rect(d, x, y, w, h, r, colour):
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, outline=colour)


def draw_pill(d, x, y, label, colour):
    fill(d, x, y + 2, 6, 6, colour)
    draw_text(d, x + 10, y, label, colour, 1)


def draw_wifi(d, cx, base_y, colour):
    """The wireless mark, mirroring draw_wifi_glyph() in hub_display.c."""
    fill(d, cx - 1, base_y - 2, 3, 3, colour)
    for rout in (8, 13):
        for band in range(2):
            r = rout - band
            a = 40
            while a <= 140:
                rad = math.radians(a)
                fx = r * math.cos(rad)
                fy = r * math.sin(rad)
                x = cx + int(fx + (0.5 if fx >= 0 else -0.5))
                y = base_y - int(fy + 0.5)
                fill(d, x, y, 1, 1, colour)
                a += 2


def rssi_bars(rssi: int) -> int:
    """How many bars a telemetry RSSI is worth, mirroring rssi_bars()."""
    if rssi == 0:
        return 0
    if rssi >= -60:
        return 4
    if rssi >= -70:
        return 3
    if rssi >= -80:
        return 2
    if rssi >= -90:
        return 1
    return 0


def signal_bars(d, x, y, bars, C):
    """Four vertical bars, bottom aligned, mirroring draw_signal_bars().

    The filled bars take their colour from the link quality: green from
    -70 dBm up, amber below it, so a weak link shows without a number."""
    col = C["C_GREEN"] if bars >= 3 else C["C_AMBER"]
    for i in range(4):
        h = 4 + i * 3
        fill(d, x + i * 5, y - h, 3, h, col if i < bars else C["C_SURFACE_HI"])


def level_bar(d, x, y, w, h, level, trigger, crying, known, C):
    """The level bar and its notch, mirroring draw_level_bar().

    Full scale is LEVEL_BAR_FULL (0.25, not 1.0) and the scale is
    square-rooted, so the quiet end of the range -- the part where the
    trigger sits -- is not squashed into nothing.  Green below the
    trigger, amber over it, the crying colour while the hub is
    announcing.  The notch marks where this cot's own trigger sits."""
    full = 0.25
    fill(d, x, y, w, h, C["C_SURFACE_HI"] if known else C["C_SURFACE"])
    v = min(max(level, 0.0), full)
    frac = math.sqrt(v / full)
    if crying:
        col = C["C_ALERT"]
    elif trigger > 0 and level >= trigger:
        col = C["C_AMBER"]
    else:
        col = C["C_GREEN"]
    fill_w = int(frac * (w - 2) + 0.5)
    if fill_w > 0:
        fill(d, x + 1, y + 1, fill_w, h - 2, col)
    if known and trigger > 0:
        t = min(trigger, full)
        nx = x + 1 + int(math.sqrt(t / full) * (w - 2) + 0.5)
        if x < nx < x + w - 1:
            fill(d, nx, y, 1, h, C["C_TEXT"])
    rect(d, x, y, w, h,
         C["C_BORDER"] if known else blend(C["C_BORDER"], C["C_BG"], 0.45))


# ---------------------------------------------------------------- the pages
def dashboard(path: Path, cots, linked, crying, cot_id, confidence, rms,
              clients, ble_ready, uptime_s, wifi_up=True):
    """The dashboard, mirroring draw_dashboard() in hub_display.c.

    Two full-width cards, one reading per row: the name and state on top,
    the level bar with its notch and the RMS beside it in the middle, the
    signal bars and the LINK dBm along the bottom.  There is no battery
    line: the battery SOC was withdrawn at D-83 and the firmware draws
    nothing about it."""
    C = load_palette()
    C["C_ALERT"] = PURPLE          # the on-glass alert colour; see PURPLE above
    L = load_layout()

    header_h = L.get("HEADER_H", 30)
    banner_x, banner_y = L.get("BANNER_X", 10), L.get("BANNER_Y", 40)
    banner_w, banner_h = L.get("BANNER_W", 300), L.get("BANNER_H", 44)
    card_x, card_w = L.get("CARD_X", 10), L.get("CARD_W", 300)
    card_y0, card_h = L.get("CARD_Y0", 88), L.get("CARD_H", 64)
    card_step = L.get("CARD_STEP", 70)
    foot_y = L.get("FOOT_Y", 230)

    img = Image.new("RGB", (W, H), C["C_BG"])
    d = ImageDraw.Draw(img)

    # ---- the header ----
    fill(d, 0, 0, W, header_h, C["C_HEADER"])
    draw_text(d, 12, 8, "CRYNET", C["C_ACCENT"], 2)
    draw_text(d, 90, 12, "S3 HUB", C["C_DIM"], 1)
    # the wireless mark is drawn only while the hub is on the network:
    # a mark here means the records are on their way, and there is no
    # second state to learn (D-100, D-103).
    if wifi_up:
        draw_wifi(d, 160, 21, C["C_GREEN"])
    draw_pill(d, 196, 11, "NODE",
              C["C_GREEN"] if linked else C["C_AMBER"])
    wearable_col = (C["C_GREEN"] if clients > 0
                    else C["C_AMBER"] if ble_ready else C["C_DIM"])
    draw_pill(d, 258, 11, "WEARABLE", wearable_col)
    fill(d, 0, header_h, W, 2, C["C_ACCENT_DIM"])

    # ---- the banner: what the system is doing ----
    banner_col = C["C_DIM"]
    banner = "SEARCHING FOR THE COTS"
    if crying:
        banner, banner_col = "CRY DETECTED", C["C_ALERT"]
    elif linked:
        banner, banner_col = "LISTENING", C["C_ACCENT"]
    round_fill(d, banner_x, banner_y, banner_w, banner_h, 8,
               blend(C["C_SURFACE"], banner_col, 0.12))
    round_rect(d, banner_x, banner_y, banner_w, banner_h, 8,
               blend(C["C_BORDER"], banner_col, 0.85 if crying else 0.25))
    fill(d, banner_x + 3, banner_y + 10, 3, banner_h - 20, banner_col)
    draw_text(d, banner_x + 16, banner_y + 9, banner, banner_col, 2)

    if crying:
        right = f"COT {cot_id}  {confidence}%"
    elif linked:
        right = f"COT {cot_id}  RMS {rms:.3f}"
    else:
        right = "--"
    draw_text(d, banner_x + banner_w - 12 - text_width(right), banner_y + 26,
              right, C["C_DIM"], 1)
    if crying and clients == 0:
        draw_text(d, banner_x + 16, banner_y + 26, "ALERT NOT DELIVERED",
                  C["C_AMBER"], 1)

    # ---- a card for every cot ----
    for i, cot in enumerate(cots):
        y = card_y0 + i * card_step
        known = cot["online"]
        accent = (C["C_ALERT"] if cot["crying"]
                  else C["C_ACCENT"] if known else C["C_BORDER"])
        fill_col = (C["C_ALERT"] if cot["crying"]
                    else C["C_BORDER"] if known else C["C_ACCENT"])
        round_fill(d, card_x, y, card_w, card_h, 6,
                   blend(C["C_SURFACE"], fill_col,
                         0.16 if cot["crying"] else 0.05))
        round_rect(d, card_x, y, card_w, card_h, 6,
                   accent if (known or cot["crying"])
                   else blend(C["C_BORDER"], C["C_BG"], 0.45))
        draw_text(d, card_x + 14, y + 8, f"COT {i + 1}",
                  C["C_TEXT"] if known else C["C_DIM"], 2)
        if cot["crying"]:
            state, state_col = f"CRY {cot['conf']}%", C["C_ALERT"]
        elif known:
            state, state_col = "ONLINE", C["C_GREEN"]
        else:
            state, state_col = "OFFLINE", C["C_DIM"]
        draw_text(d, card_x + card_w - 14 - text_width(state), y + 11,
                  state, state_col, 1)
        # middle row: the bar with its notch, and the RMS number beside it
        rms_s = f"RMS {cot['rms']:.3f}"
        rms_w = text_width(rms_s)
        level_bar(d, card_x + 14, y + 26, card_w - 28 - rms_w - 6, 8,
                  cot["rms"] if known else 0.0,
                  cot["trigger"] if known else 0.0,
                  cot["crying"], known, C)
        draw_text(d, card_x + card_w - 14 - rms_w, y + 26, rms_s,
                  C["C_TEXT"] if known else C["C_DIM"], 1)
        # bottom row: the radio link -- signal bars and the RSSI, or "--"
        bars = rssi_bars(cot["rssi"]) if known else 0
        signal_bars(d, card_x + 14, y + 58, bars, C)
        if not known or cot["rssi"] == 0:
            link = "LINK --"
        else:
            link = f"LINK {cot['rssi']} dBm"
        draw_text(d, card_x + 14 + 4 * 5 + 4, y + 51, link, C["C_DIM"], 1)

    # ---- the footer ----
    # The firmware counts the cots that are *answering*, not the cards
    # on the screen: a card for a quiet cot says OFFLINE, so a
    # "3 cots linked" above two OFFLINE cards would be a lie.
    count = sum(1 for cot in cots if cot["online"])
    label = ("no cots linked" if count == 0
             else f"{count} cot{'' if count == 1 else 's'} linked")
    draw_text(d, 12, foot_y, label, C["C_DIM"], 1)
    up = f"up {uptime_s // 60}:{uptime_s % 60:02d}"
    draw_text(d, W - 12 - text_width(up), foot_y, up, C["C_DIM"], 1)

    img.save(path)
    return path


def title_card(path: Path, frame: int = 6):
    """The splash's title card, mirroring draw_title_face() in hub_display.c.

    What the device is, who built it, and the number it is registered
    under: the three things a panel has to say to the person standing in
    front of it."""
    C = load_palette()
    img = Image.new("RGB", (W, H), C["C_BG"])
    d = ImageDraw.Draw(img)

    # a quiet accent band across the top, so the card has a top edge
    fill(d, 0, 0, W, 3, C["C_ACCENT_DIM"])
    fill(d, 0, 0, 60, 3, C["C_ACCENT"])

    draw_text_centre(d, 22, "AMAZING'S CRYNET", C["C_ACCENT"], 2)
    draw_text_centre(d, 44, "A MULTI-NODE INFANT CRY DETECTION SYSTEM",
                     C["C_DIM"], 1)

    # the full project title, set across three lines in the dim colour
    draw_text_centre(d, 74, "DESIGN AND CONSTRUCTION OF A", C["C_DIM"], 1)
    draw_text_centre(d, 86, "MULTI-NODE INFANT CRY DETECTION", C["C_DIM"], 1)
    draw_text_centre(d, 98, "SYSTEM WITH WEARABLE CAREGIVER ALERT", C["C_DIM"], 1)

    # a rule, then the name and the id number
    fill(d, 60, 120, 200, 1, C["C_BORDER"])
    pulse = 0.5 + 0.5 * math.sin(frame * 0.09)
    draw_text_centre(d, 136, "AMAZING AYOMIKUN ADELOWO",
                     blend(C["C_TEXT"], C["C_ACCENT"], 0.10 + 0.20 * pulse), 2)
    draw_text_centre(d, 170, "22/05/04/0029", C["C_DIM"], 1)

    # what this device is in the project
    draw_text_centre(d, 206, "ESP32-S3 HUB  -  TWO COT NODES", C["C_DIM"], 1)

    # a waveform along the bottom edge, tying the card to the boot face
    t = frame * 0.18
    for i in range(48):
        p = t + i * 0.42
        a = 0.5 + 0.5 * math.sin(p * 1.7)
        b = 0.5 + 0.5 * math.sin(p * 0.53 + 1.7)
        bh = int(6 * (0.18 + 0.82 * a * b))
        fill(d, i * 7, H - 1 - bh, 4, bh, C["C_ACCENT_DIM"])

    img.save(path)
    return path


def colour_check(path: Path):
    """The colour check, mirroring draw_colour_check() in hub_display.c."""
    C = load_palette()
    L = load_layout()
    header_h = L.get("HEADER_H", 30)

    img = Image.new("RGB", (W, H), C["C_BG"])
    d = ImageDraw.Draw(img)

    fill(d, 0, 0, W, header_h, C["C_HEADER"])
    draw_text(d, 12, 8, "COLOUR CHECK", C["C_TEXT"], 2)
    fill(d, 0, header_h, W, 2, C["C_ACCENT_DIM"])

    swatches = [
        ("BLACK", (0, 0, 0)),
        ("WHITE", (255, 255, 255)),
        ("TEAL", C["C_ACCENT"]),
        ("NAVY", (12, 20, 32)),
        ("GREEN", C["C_GREEN"]),
        ("AMBER", C["C_AMBER"]),
        ("ROSE", C["C_ALERT"]),
        ("GREY", C["C_DIM"]),
    ]
    cols, w, h, gap = 4, 74, 56, 6
    x0 = (W - (cols * w + (cols - 1) * gap)) // 2
    for i, (name, colour) in enumerate(swatches):
        cx = x0 + (i % cols) * (w + gap)
        cy = 40 + (i // cols) * (h + 24)
        fill(d, cx, cy, w, h, colour)
        rect(d, cx, cy, w, h, C["C_BORDER"])
        draw_text(d, cx + (w - text_width(name, 1)) // 2, cy + h + 5,
                  name, C["C_DIM"], 1)

    # the dark ramp
    ramp = [(0, 0, 0), (2, 4, 4), (4, 8, 8), (7, 15, 16), (12, 26, 28),
            (24, 52, 56)]
    rw = (W - 8) // len(ramp)
    for i, colour in enumerate(ramp):
        fill(d, 4 + i * rw, 190, rw, 14, colour)
    rect(d, 3, 189, rw * len(ramp) + 2, 16, C["C_BORDER"])
    draw_text(d, 4, 206, "the dark ramp", C["C_DIM"], 1)

    foot = "backlight 55%  -  press BOOT to go back"
    draw_text_centre(d, H - 14, foot, C["C_DIM"], 1)

    img.save(path)
    return path


COTS_QUIET = [
    {"online": True, "crying": False, "rms": 0.012, "trigger": 0.030,
     "rssi": -58, "conf": 0},
    {"online": True, "crying": False, "rms": 0.041, "trigger": 0.030,
     "rssi": -72, "conf": 0},
]

COTS_CRYING = [
    {"online": True, "crying": True, "rms": 0.284, "trigger": 0.030,
     "rssi": -58, "conf": 97},
    {"online": True, "crying": False, "rms": 0.141, "trigger": 0.030,
     "rssi": -63, "conf": 0},
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [
        dashboard(OUT / "ui_dashboard.png", COTS_QUIET, True, False, 1, 0,
                  0.012, 1, True, 12 * 60 + 4),
        dashboard(OUT / "ui_dashboard_alert.png", COTS_CRYING, True, True,
                  1, 97, 0.284, 1, True, 12 * 60 + 4),
        dashboard(OUT / "ui_dashboard_alert_nophone.png", COTS_CRYING, True,
                  True, 1, 97, 0.284, 0, True, 12 * 60 + 4),
        dashboard(OUT / "ui_dashboard_nowifi.png", COTS_QUIET, True, False, 1,
                  0, 0.012, 1, True, 12 * 60 + 4, wifi_up=False),
        title_card(OUT / "ui_splash.png"),
        colour_check(OUT / "ui_colour_check.png"),
    ]
    for p in paths:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
