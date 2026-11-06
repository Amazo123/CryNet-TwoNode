"""Page 3 - main hub complete wiring."""

from diagram_lib import Page

W, H = 1000, 575


def build():
    p = Page(W, H, "3 / Main hub - complete wiring (x1)",
             "ESP32-S3-DevKitC-1 N16R8 + 2.8\" ILI9341 (backlight switched by a "
             "2N7002) + LX-LCBST + switch + battery-sense divider + 2 LEDs")

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
    # bottom row: GPIO1 = ADC, GPIO4 = backlight gate, GPIO17 = SOC, GPIO2 = BLE
    for name, x in (("GPIO1", 415), ("GPIO4", 462), ("GPIO17", 510),
                    ("GPIO2", 558)):
        p.label(x, 347, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=board)

    # --------------------------------------------------------------- TFT --
    tft = p.box(690, 55, 180, 270, "2.8\" ILI9341", cls="mod")
    for name, y in (("VCC", 105), ("GND", 145), ("CS", 185), ("SDI", 220),
                    ("CLK", 255), ("DC", 290), ("RST", 325)):
        p.label(698, y + 5, name, size=12.5, cls="pin", mono=True, owner=tft)
    # the panel's backlight anode, now switched by the MOSFET
    p.label(864, 195, "LED", size=12.5, cls="pin", anchor="end", mono=True,
            owner=tft)
    p.label(864, 176, "backlight", size=10.5, cls="small", anchor="end",
            owner=tft)

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
    p.wire([(585, 145), (690, 145)], color="black")
    p.wire([(585, 185), (690, 185)], color="blue")
    p.wire([(585, 220), (690, 220)], color="green")
    p.wire([(585, 255), (690, 255)], color="orange")
    p.wire([(585, 290), (690, 290)], color="purple")
    p.wire([(585, 325), (690, 325)], color="teal")
    p.wire([(870, 145), (895, 145)], color="black")
    p.ground(895, 145, dir="right")

    # ------------------------------------------- backlight MOSFET switch --
    # The panel's LED pin is the backlight anode.  It is switched by an
    # N-channel MOSFET so the MCU pin never sources the backlight current:
    # 3V3 -> drain, source -> TFT LED, gate = GPIO4 through 100 ohm with a
    # 100 k pull-down, so the panel stays dark while the chip is in reset.
    p.wire([(870, 195), (880, 195), (880, 215), (960, 215), (960, 225)],
           color="red")
    mos = p.box(920, 225, 72, 70, None, cls="part")
    p.label(956, 258, "2N7002", size=11.5, cls="small", anchor="middle",
            mono=True, owner=mos)
    p.label(948, 232, "S", size=12.5, cls="pin", anchor="end", mono=True,
            owner=mos)
    p.label(948, 290, "D", size=12.5, cls="pin", anchor="end", mono=True,
            owner=mos)
    p.label(905, 250, "G", size=12.5, cls="pin", anchor="middle", mono=True,
            owner=mos)
    # drain to the hub's 3.3 V rail - the same net as the TFT's VCC
    p.wire([(960, 295), (960, 330)], color="red")
    p.label(966, 334, "3V3", size=11, cls="small", mono=True, color="#c43e39")
    # gate: GPIO4 -> 100 ohm -> the gate node, with the 100 k pull-down to
    # ground at that node, so the backlight is off during reset.
    p.wire([(920, 262), (900, 262), (900, 478), (550, 478)], color="grey")
    p.part(500, 465, 50, 26, "100 Ω")
    p.wire([(500, 478), (462, 478), (462, 355)], color="grey")
    p.dot(575, 478)
    p.wire([(575, 478), (575, 500)], color="grey")
    p.vpart(563, 500, 24, 28, "100 kΩ", anchor="end", label_dx=-4)
    p.label(559, 537, "gate pull-down", size=11, cls="small", anchor="end")
    p.wire([(575, 528), (575, 540)], color="grey")
    p.ground(575, 540)

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

    # the note about the backlight, clear of every wire
    p.label(600, 495, "Backlight is now PWM-dimmable (GPIO4 + LEDC);", size=12,
            cls="note")
    p.label(600, 512, "a sleep mode only needs the PWM at 0.", size=12,
            cls="note")

    notes = (
        '<div class="ok">Verified on the live system: the TFT signal pins '
        '(CS 10, MOSI 11, SCK 12, DC 13, RST 14, VCC 3V3, GND) and the '
        'GPIO4 backlight, which the firmware already drives with LEDC PWM '
        '(hub_display.c: PIN_BL 4, ili9341_backlight_set). Because the '
        'backlight now runs through the 2N7002, it is PWM-dimmable, and a '
        'future sleep mode only has to set the PWM to 0 to switch the panel '
        'off.</div>'
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
            "module. The 2N7002 gate pull-down keeps the backlight off "
            "during reset. Every &#9169; symbol is the same net: the "
            "module's VO-.")
    return p, notes, foot
