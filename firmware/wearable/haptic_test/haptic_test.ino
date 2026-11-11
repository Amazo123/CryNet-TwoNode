/*
 * Haptic motor bench test -- the wearable's motor, on a breadboard.
 *
 * What it does: drives the BC547 low-side switch on GPIO7 exactly the
 * way the real wearable firmware does (D-77), so the motor runs for
 * 3 seconds, stops for 2 seconds, and repeats until the board is
 * unplugged.  Watch the motor, or watch the serial log at 115200 baud.
 *
 * Wiring (from SYSTEM_WIRING.md 5.3 / the page 5 diagram):
 *
 *   3V3 ---[22 ohm in the motor's + lead]--- motor --- collector  BC547
 *                                                     |
 *   GPIO7 ---[2.2 k]--- base                          emitter --- GND
 *                                                      |
 *                        1N5819 across the motor, cathode UP to the + net
 *                        100 k from base to emitter
 *
 * The motor's + leg must come from the 3V3 pin, the BC547's emitter to
 * GND, and the flyback diode's striped end (cathode) towards the + net.
 * A backwards diode does not just make the motor quiet -- it shorts the
 * motor and pushes the whole supply current through the BC547.
 *
 * This sketch replaces the wearable firmware on the board.  Put the real
 * one back afterwards with:
 *
 *   python firmware/tools/flash_node.py --port COM30 --sketch wearable
 *
 * (or flash the built image from firmware/prebuilt/wearable/).
 */

#include <Arduino.h>

/* The BC547 haptic switch (D-77): GPIO7 -> 2.2 k -> base.  HIGH turns the
 * transistor on and the motor spins; LOW lets it stop. */
static const uint8_t PIN_MOTOR = 7;

/* The cycle the owner asked for: three seconds on, two seconds off. */
static const uint32_t ON_MS  = 3000;
static const uint32_t OFF_MS = 2000;

void setup()
{
    /* The transistor must be off before anything else happens here: the
     * 100 k base-emitter pulldown holds it off at reset, and this makes
     * sure the motor never twitches while the sketch starts. */
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, LOW);

    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && millis() - t0 < 2000) {
        delay(10);
    }

    Serial.println();
    Serial.println("[haptic-test] GPIO7 drives the BC547 low-side switch.");
    Serial.println("[haptic-test] motor ON for 3 s, OFF for 2 s, forever.");
    Serial.println("[haptic-test] ctrl-c stops the log; the board keeps going.");
}

void loop()
{
    digitalWrite(PIN_MOTOR, HIGH);
    Serial.println("[haptic-test] motor ON");
    delay(ON_MS);

    digitalWrite(PIN_MOTOR, LOW);
    Serial.println("[haptic-test] motor OFF");
    delay(OFF_MS);
}
