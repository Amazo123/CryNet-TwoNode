"""Page 3 - main hub complete wiring."""

from diagram_lib import Page

W, H = 1000, 490


def build():
    p = Page(W, H, "3 / Main hub - complete wiring (x1)",
             "ESP32-S3-DevKitC-1 N16R8 + 2.8\" ILI9341 (backlight on 3V3, "
             "always on) + LX-LCBST + switch + battery-sense divider + 2 LEDs")

    # ---------------------------------------------------------- LX-LCBST --
    mod = p.box(25, 55, 175, 245, "LX-LCBST-TC-001", cls="proposed",
                sub=["charger + protection + boost", "USB-C = charge input",
                     "cell on B+ / B-"])
    for name, y in (("VO+", 124), ("VO-", 169), ("B+", 229), ("B-", 274)):
        p.label(192, y, name, size=12.5, cls="pin", anchor="end", mono=True,
                owner=mod)

    # ------------------------------------------------------------ switch --
    sw = p.box(245, 100, 75, 40, None, cls="proposed")
    p.label(255, 118, "SPST", size=12, cls="small", owner=sw)
    p.label(255, 133, ">= 1 A", size=10.5, cls="small", owner=sw)

    # ------------------------------------------------------------- board --
    board = p.box(390, 45, 195, 310, "ESP32-S3 hub", cls="board",
                  sub=["avoid GPIO0/3/45/46 - 35..37"])
    p.label(398, 124, "5V", size=12.5, cls="pin", mono=True, owner=board)
    p.label(398, 324, "GND", size=12.5, cls="pin", mono=True, owner=board)
    for name, y in (("3V3", 105), ("GND", 145), ("GPIO10", 185), ("GPIO11", 220),
                    ("GPIO12", 255), ("GPIO13", 290), ("GPIO14", 325)):
        p.label(577, y + 5, name, size=12.5, cls="pin", anchor="end", mono=True,
                owner=board)
    # bottom row: GPIO1 = ADC, GPIO17 = SOC LED, GPIO2 = BLE LED
    for name, x in (("GPIO1", 420), ("GPIO17", 510), ("GPIO2", 558)):
        p.label(x, 347, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=board)

    # --------------------------------------------------------------- TFT --
    tft = p.box(690, 55, 180, 292, "2.8\" ILI9341", cls="mod")
    for name, y in (("VCC", 105), ("LED", 125), ("GND", 145), ("CS", 185),
                    ("SDI", 220), ("CLK", 255), ("DC", 290), ("RST", 325)):
        p.label(698, y + 5, name, size=12.5, cls="pin", mono=True, owner=tft)

    # ------------------------------------------------------- power chain --
    p.wire([(200, 120), (245, 120)], color="red")
    p.label(204, 133, "5.1 V", size=11, cls="small", color="#c43e39")
    p.wire([(320, 120), (390, 120)], color="red")
    p.label(330, 111, "5 V", size=11, cls="small", color="#c43e39")
    p.wire([(200, 165), (225, 165)], color="black")
    p.ground(225, 165, dir="right")
    p.wire([(200, 274), (225, 274)], color="black")
    p.ground(225, 274, dir="right")
    p.wire([(390, 320), (355, 320)], color="black")
    p.ground(355, 320, dir="left")

    # ------------------------------------------------- battery sense ------
    # the sense tap lands on GPIO1 (ADC1_CH0) at the bottom of the board
    p.battery_sense(200, 225, 420, 355)

    # ------------------------------------------------------------- TFT ---
    p.wire([(585, 105), (690, 105)], color="red")
    p.label(600, 96, "3.3 V", size=11, cls="small", color="#c43e39")
    # the backlight anode branches off that same 3.3 V net
    p.dot(640, 105)
    p.wire([(640, 105), (640, 125), (690, 125)], color="red")
    p.wire([(585, 145), (690, 145)], color="black")
    p.wire([(585, 185), (690, 185)], color="blue")
    p.wire([(585, 220), (690, 220)], color="green")
    p.wire([(585, 255), (690, 255)], color="orange")
    p.wire([(585, 290), (690, 290)], color="purple")
    p.wire([(585, 325), (690, 325)], color="teal")
    p.wire([(870, 145), (895, 145)], color="black")
    p.ground(895, 145, dir="right")

    # the note about the backlight, in the clear space under the panel
    p.label(596, 366, "Backlight: LED pin on 3.3 V - always on, no dimming.",
            size=12, cls="note")

    # ------------------------------------------------------------ LEDs ---
    # GPIO2 = blue BLE-status LED
    p.wire([(558, 355), (558, 395), (650, 395)], color="blue")
    p.part(650, 382, 72, 26, "1 kΩ")
    p.wire([(722, 395), (740, 395)], color="blue")
    p.part(740, 382, 70, 26, "BLUE LED")
    p.wire([(810, 395), (830, 395)], color="blue")
    p.ground(830, 395, dir="right")
    p.label(856, 399, "BLE", size=11, cls="small")

    # GPIO17 = amber SOC LED
    p.wire([(510, 355), (510, 440), (650, 440)], color="orange")
    p.part(650, 427, 72, 26, "1 kΩ")
    p.wire([(722, 440), (740, 440)], color="orange")
    p.part(740, 427, 70, 26, "AMBER LED")
    p.wire([(810, 440), (830, 440)], color="orange")
    p.ground(830, 440, dir="right")
    p.label(856, 444, "SOC", size=11, cls="small")

    notes = (
        '<div class="ok">Verified on the live system: the TFT signal pins '
        '(CS 10, MOSI 11, SCK 12, DC 13, RST 14, VCC 3V3, GND). The panel\'s '
        'LED (backlight) pin is tied to the same 3.3 V net as the panel\'s '
        'VCC pin, so the backlight is permanently on: the glass cannot be '
        'dimmed and the display has no sleep mode. The hub firmware still '
        'drives GPIO4 as a backlight output (hub_display.c: PIN_BL 4, '
        'ili9341_backlight_set), so GPIO4 is left unconnected and the '
        'brightness control on the panel has no effect on the glass.</div>'
        '<div class="warning">Plan only - the hub firmware does none of '
        'this yet: it has no analogReadMilliVolts at all and drives no LED. '
        'So the GPIO1 divider (ADC1_CH0), the GPIO2 blue BLE LED and the '
        'GPIO17 amber SOC LED are wiring plans, not working circuits. '
        '(BAT_CURVE / battery_band_advance in hub_display.c describe the '
        'NODES\' reported cell voltage, not the hub\'s own cell.) The hub\'s '
        'peak current with TFT + radios is unmeasured - confirm the LX-LCBST '
        'holds 5.1 V during bursts before trusting it here.</div>'
    )
    foot = ("GPIO35-37 are the Octal PSRAM bus - never wire them. The TFT "
            "signal wiring is the recorded working one for the existing "
            "module. The backlight is on 3.3 V and GPIO4 is not used. Every "
            "&#9169; symbol is the same net: the module's VO-.")
    return p, notes, foot
