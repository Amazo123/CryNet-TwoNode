/*
 * CryNet — the hub's display.  See include/hub_display.h.
 *
 * The public API is deliberately dumb: hub_display_update() just copies
 * the newest state under a spinlock, and a low-priority task on the
 * other core redraws whatever changed.  Only this task ever touches the
 * panel, so the driver needs no locking of its own.
 *
 * The screen has three faces.
 *
 *   * A splash, in two acts.  First the boot: a waveform that moves,
 *     the name, the boot steps.  Then the title card: the project's
 *     own title, the name of the person who built it and the number it
 *     is registered under.  A final-year project is judged partly on
 *     what it is and who did it, and a device that says so on its own
 *     screen answers the examiner before they ask.
 *
 *   * The dashboard.  The hub's own state at the top (cot link,
 *     bluetooth, uptime), a banner that says what the system is doing,
 *     and a card for every cot: its name, whether it is online, and its
 *     level.
 *
 *   * Two more faces, summoned with the BOOT button: the help page,
 *     which explains what each number on a card means, and the colour
 *     check, a grid of the palette's swatches.  The colour check exists
 *     because a photograph of a glowing panel in a dark room is not a
 *     colour measurement — the camera opens up, the highlights clip and
 *     the white balance drifts — so the swatches are how the panel's
 *     own colours are judged.
 *
 * The palette is a calm near-black teal with a teal accent.  Red is
 * kept for one thing only — a confirmed cry — because a panel that is
 * red all the time stops meaning anything.
 *
 * Everything is composed in a framebuffer (320x240 RGB565, in PSRAM)
 * and pushed to the panel in one transfer, so a frame is never torn.
 */

#include "hub_display.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "driver/gpio.h"

#include "font5x7.h"
#include "ili9341.h"

static const char *TAG = "hub_display";

/* The panel hangs on the pins the legacy firmware used: CS 10, MOSI 11,
 * SCK 12, DC 13, RST 14, backlight 4. */
#define PIN_MOSI 11
#define PIN_SCLK 12
#define PIN_CS   10
#define PIN_DC   13
#define PIN_RST  14
#define PIN_BL   4

/* The BOOT button on the devkit is GPIO0, and it is active low.  It
 * opens and closes the colour check. */
#define PIN_BUTTON 0

/* This panel is "landscape-first": the upright landscape setting is
 * MADCTL_MY with a 320x240 framebuffer, which is what the legacy
 * firmware used (Adafruit's rotation 2, with its 240 px clipping
 * overridden).  Rotation 1 (MADCTL_MV) turns the whole picture a
 * quarter turn on this glass, which is what happened the first time. */
#define ROTATION_LANDSCAPE 2

#define FB_W 320
#define FB_H 240

/* ---- the palette -------------------------------------------------------- */
/* A dark, calm scheme: a near-black teal background, a teal accent,
 * green for a cot that is fine, amber for a cot that is loud, and rose
 * — not fire-engine red — for a confirmed cry.
 *
 * The neutrals are darker and teal-tinted rather than navy, and that is
 * a measured change.  The colour-check page (the BOOT button) put a
 * (12,20,32) navy on the glass and a (0,0,0) black next to it, and the
 * navy came back as a **saturated blue while the black stayed black**:
 * this panel lifts the dark end, and it lifts the blue channel most of
 * all, so the *less* blue the screen asks for, the less blue it gets.
 * A background that asks for 32 blue reads as a bright blue; one that
 * asks for 16 reads as a dark one.  The theme is unchanged in what it
 * says - teal for the system, green for fine, amber for loud, rose for
 * a cry - but the screen now reads teal instead of blue.
 *
 * The level itself was picked off the glass, not out of a chart: shown
 * the dark ramp, the reader chose its third step - (4,8,8) - as the teal
 * the screen should be, and the whole neutral family moved down one step
 * of the same ramp with it.  On the glass that made the cards sit at the
 * same value as the background - the panel lifts the dark end until a
 * two-step gap reads as one - so the background has dropped another step:
 * the cards keep (7,15,16) and the ground under them is now (2,4,4).
 *
 * The header strip is its own colour for the same reason, one edge at a
 * time: the backlight's LEDs run along the top of the glass and lift
 * that strip blue, so a header painted the same (7,15,16) as the cards
 * photographed blue while the cards photographed teal.  (7,20,15) asks
 * for five steps of green above blue, which the lift spends on its way
 * in; what the reader sees is the teal the cards show. */
#define C_BG         DISPLAY_RGB(2, 4, 4)
#define C_SURFACE    DISPLAY_RGB(7, 15, 16)
#define C_SURFACE_HI DISPLAY_RGB(12, 26, 28)
#define C_HEADER     DISPLAY_RGB(7, 20, 15)
/* The border is a UI component, so it has to clear 3:1 against the
 * card it sits on — the first choice (40,57,76) measured 1.40:1 and
 * was effectively invisible. */
#define C_BORDER     DISPLAY_RGB(78, 116, 112)
#define C_TEXT       DISPLAY_RGB(228, 240, 236)
#define C_DIM        DISPLAY_RGB(122, 150, 146)
#define C_ACCENT     DISPLAY_RGB(45, 212, 191)
#define C_ACCENT_DIM DISPLAY_RGB(22, 124, 112)
#define C_BLUE       DISPLAY_RGB(96, 165, 250)
#define C_GREEN      DISPLAY_RGB(52, 211, 153)
#define C_AMBER      DISPLAY_RGB(251, 191, 36)
#define C_ALERT      DISPLAY_RGB(251, 113, 133)

/* ---- the layout --------------------------------------------------------- */
#define HEADER_H     30
#define BANNER_X     10
#define BANNER_Y     40
#define BANNER_W     300
#define BANNER_H     44
#define CARD_X       10
#define CARD_W       300
/* Two cot cards, taller now: each carries the cot's name and state,
 * an RMS bar with its number, and a bottom row with the radio link
 * (a small signal bar plus the RSSI) and the battery.  88 + 2*70 puts
 * the last card's bottom edge at 222, leaving room for the footer at
 * 230. */
#define CARD_H       64
#define CARD_Y0      88
#define CARD_STEP    70
#define FOOT_Y       230

/* The splash: how long it runs, how long each fade takes, and how fast
 * it animates.
 *
 * The splash runs in two acts.  The first is the boot: the waveform, the
 * name, the boot steps and a progress bar.  The second is the title
 * card: the project this device is, the person who built it, and the
 * number it is registered under.  A final-year project is judged partly
 * on what it is and who did it, and a device that says so on its own
 * screen answers the examiner before they ask.
 *
 * The timeline, in milliseconds from the start of the splash:
 *
 *   0 .. BOOT_MS           the boot face
 *   BOOT_MS .. +FADE_MS    the boot face fading out
 *   +FADE_MS .. SPLASH_MS  the title card
 *   SPLASH_MS .. +FADE_MS  the whole splash fading out
 *   .. +2*FADE_MS          the dashboard fading in
 */
#define SPLASH_MS    5600
#define BOOT_MS      2400
#define TITLE_MS     (SPLASH_MS - BOOT_MS - FADE_MS)
#define FADE_MS      600
#define SPLASH_TICK  100        /* ms between frames: ten a second */

/* The backlight, as a percentage.  Full brightness glares in a dark
 * room, and a glare is what makes a colour look like the wrong colour:
 * the photograph of the panel came out blue because the panel was
 * brighter than the room and the camera's white balance went with it.
 * 55 % is the level that keeps a dark navy background dark and lets
 * the teal read as teal; it can be changed at run time. */
#define BACKLIGHT_DEFAULT  55

static ili9341_t s_dev;
static uint16_t *s_fb;          /* 320 x 240 RGB565, in PSRAM */

static hub_display_state_t s_state;   /* guarded by s_lock */
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_version;   /* bumped on every update */

/* The backlight's brightness, and which of the panel's three faces is
 * up.  Both are read by the display task and written by the API. */
static volatile uint8_t s_brightness = BACKLIGHT_DEFAULT;
/* 0 = the dashboard, 1 = the help page, 2 = the colour check. */
static volatile int s_face = 0;

/* The region of the panel that has changed and still has to be pushed. */
static int s_dirty_x0, s_dirty_y0, s_dirty_x1, s_dirty_y1;

/* ------------------------------------------------------------------ */
/* The framebuffer                                                      */
/* ------------------------------------------------------------------ */

static void mark_dirty(int x, int y, int w, int h)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (s_dirty_x1 < s_dirty_x0) {
        s_dirty_x0 = x; s_dirty_y0 = y;
        s_dirty_x1 = x + w - 1; s_dirty_y1 = y + h - 1;
        return;
    }
    if (x < s_dirty_x0) { s_dirty_x0 = x; }
    if (y < s_dirty_y0) { s_dirty_y0 = y; }
    if (x + w - 1 > s_dirty_x1) { s_dirty_x1 = x + w - 1; }
    if (y + h - 1 > s_dirty_y1) { s_dirty_y1 = y + h - 1; }
}

static inline void fb_px(int x, int y, uint16_t c)
{
    if ((unsigned)x >= FB_W || (unsigned)y >= FB_H) {
        return;
    }
    s_fb[(size_t)y * FB_W + x] = c;
}

static void fb_fill(int x, int y, int w, int h, uint16_t c)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > FB_W) { w = FB_W - x; }
    if (y + h > FB_H) { h = FB_H - y; }
    for (int j = 0; j < h; j++) {
        uint16_t *row = &s_fb[(size_t)(y + j) * FB_W + x];
        for (int i = 0; i < w; i++) {
            row[i] = c;
        }
    }
    mark_dirty(x, y, w, h);
}

static void fb_hline(int x, int y, int w, uint16_t c)
{
    fb_fill(x, y, w, 1, c);
}

static void fb_vline(int x, int y, int h, uint16_t c)
{
    fb_fill(x, y, 1, h, c);
}

static void fb_rect(int x, int y, int w, int h, uint16_t c)
{
    fb_hline(x, y, w, c);
    fb_hline(x, y + h - 1, w, c);
    fb_vline(x, y, h, c);
    fb_vline(x + w - 1, y, h, c);
}

/* Blend two colours.  t = 0 gives a, t = 1 gives b. */
static uint16_t blend(uint16_t a, uint16_t b, float t)
{
    if (t <= 0.0f) { return a; }
    if (t >= 1.0f) { return b; }
    const int ar = (a >> 11) & 0x1F, ag = (a >> 5) & 0x3F, ab = a & 0x1F;
    const int br = (b >> 11) & 0x1F, bg = (b >> 5) & 0x3F, bb = b & 0x1F;
    const int f = (int)(t * 256.0f);
    const int r = (ar * (256 - f) + br * f) >> 8;
    const int g = (ag * (256 - f) + bg * f) >> 8;
    const int bl = (ab * (256 - f) + bb * f) >> 8;
    return (uint16_t)(((r & 0x1F) << 11) | ((g & 0x3F) << 5) | (bl & 0x1F));
}

/* A filled rectangle with rounded corners. */
static void fb_round_fill(int x, int y, int w, int h, int r, uint16_t c)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (r <= 0) {
        fb_fill(x, y, w, h, c);
        return;
    }
    if (r > w / 2) { r = w / 2; }
    if (r > h / 2) { r = h / 2; }
    fb_fill(x + r, y, w - 2 * r, h, c);
    fb_fill(x, y + r, r, h - 2 * r, c);
    fb_fill(x + w - r, y + r, r, h - 2 * r, c);

    /* The four corner discs.  Each disc is centred on the point the
     * straight edges stop at, and its quarter is walked *towards its
     * own corner* (sx, sy).  An earlier version walked every disc
     * inward from its centre, which painted all four arcs on the
     * inside of the shape; the bottom-right one only looked right
     * because its inward quadrant happened to end at the shape's own
     * edge. */
    const int cx[4] = { x + r, x + w - 1 - r, x + r, x + w - 1 - r };
    const int cy[4] = { y + r, y + r, y + h - 1 - r, y + h - 1 - r };
    const int sx[4] = { -1, 1, -1, 1 };
    const int sy[4] = { -1, -1, 1, 1 };
    for (int k = 0; k < 4; k++) {
        for (int dx = 0; dx <= r; dx++) {
            for (int dy = 0; dy <= r; dy++) {
                if (dx * dx + dy * dy > r * r) {
                    continue;
                }
                fb_px(cx[k] + sx[k] * dx, cy[k] + sy[k] * dy, c);
            }
        }
    }
    mark_dirty(x, y, w, h);
}

/* An outlined rectangle with rounded corners. */
static void fb_round_rect(int x, int y, int w, int h, int r, uint16_t c)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (r <= 0) {
        fb_rect(x, y, w, h, c);
        return;
    }
    if (r > w / 2) { r = w / 2; }
    if (r > h / 2) { r = h / 2; }
    fb_hline(x + r, y, w - 2 * r, c);
    fb_hline(x + r, y + h - 1, w - 2 * r, c);
    fb_vline(x, y + r, h - 2 * r, c);
    fb_vline(x + w - 1, y + r, h - 2 * r, c);

    /* The corner arcs - the same discs as fb_round_fill, but only the
     * pixels a ring's width from the arc itself, and walked towards
     * their own corners (see the note there). */
    const int cx[4] = { x + r, x + w - 1 - r, x + r, x + w - 1 - r };
    const int cy[4] = { y + r, y + r, y + h - 1 - r, y + h - 1 - r };
    const int sx[4] = { -1, 1, -1, 1 };
    const int sy[4] = { -1, -1, 1, 1 };
    for (int k = 0; k < 4; k++) {
        for (int dx = 0; dx <= r; dx++) {
            for (int dy = 0; dy <= r; dy++) {
                const int d2 = dx * dx + dy * dy;
                if (d2 > r * r || d2 < (r - 1) * (r - 1)) {
                    continue;
                }
                fb_px(cx[k] + sx[k] * dx, cy[k] + sy[k] * dy, c);
            }
        }
    }
    mark_dirty(x, y, w, h);
}

/* Fade the whole framebuffer towards one colour.  t = 0 leaves it
 * alone, t = 1 washes it out completely. */
static void fb_fade(uint16_t towards, float t)
{
    if (t <= 0.0f) {
        return;
    }
    if (t > 1.0f) { t = 1.0f; }
    const int f = (int)(t * 256.0f);
    const uint16_t tr = (towards >> 11) & 0x1F;
    const uint16_t tg = (towards >> 5) & 0x3F;
    const uint16_t tb = towards & 0x1F;
    for (size_t i = 0; i < (size_t)FB_W * FB_H; i++) {
        const uint16_t v = s_fb[i];
        const int vr = (v >> 11) & 0x1F, vg = (v >> 5) & 0x3F, vb = v & 0x1F;
        const int r = (vr * (256 - f) + tr * f) >> 8;
        const int g = (vg * (256 - f) + tg * f) >> 8;
        const int b = (vb * (256 - f) + tb * f) >> 8;
        s_fb[i] = (uint16_t)(((r & 0x1F) << 11) | ((g & 0x3F) << 5) | (b & 0x1F));
    }
    mark_dirty(0, 0, FB_W, FB_H);
}

/* ------------------------------------------------------------------ */
/* Text                                                                 */
/* ------------------------------------------------------------------ */

static int fb_text_w(const char *text, uint8_t scale)
{
    if (scale == 0) { scale = 1; }
    const int n = (int)strlen(text);
    if (n == 0) { return 0; }
    return n * (FONT5X7_WIDTH + 1) * scale - scale;
}

static void fb_text(int x, int y, const char *text, uint16_t c, uint8_t scale)
{
    if (scale == 0) { scale = 1; }
    int cursor = x;
    for (const char *p = text; *p; p++) {
        unsigned char ch = (unsigned char)*p;
        if (ch < FONT5X7_FIRST || ch > FONT5X7_LAST) {
            ch = '?';
        }
        const uint8_t *glyph = s_font5x7[ch - FONT5X7_FIRST];
        for (int col = 0; col < FONT5X7_WIDTH; col++) {
            const uint8_t bits = glyph[col];
            if (!bits) { continue; }
            for (int row = 0; row < FONT5X7_HEIGHT; row++) {
                if (bits & (1 << row)) {
                    fb_fill(cursor + col * scale, y + row * scale,
                            scale, scale, c);
                }
            }
        }
        cursor += (FONT5X7_WIDTH + 1) * scale;
    }
}

static void fb_text_centre(int y, const char *text, uint16_t c, uint8_t scale)
{
    fb_text((FB_W - fb_text_w(text, scale)) / 2, y, text, c, scale);
}

/* ------------------------------------------------------------------ */
/* The splash                                                           */
/* ------------------------------------------------------------------ */

#define WAVE_BARS 36
#define WAVE_STEP 7
#define WAVE_X0   ((FB_W - (WAVE_BARS * WAVE_STEP - 3)) / 2)
#define WAVE_Y    84
#define WAVE_MAX  26

/* A scrolling waveform: the shape of sound arriving at the mic. */
static void draw_waveform(int frame)
{
    const float t = (float)frame * 0.18f;
    for (int i = 0; i < WAVE_BARS; i++) {
        const float p = t + i * 0.42f;
        const float a = 0.5f + 0.5f * sinf(p * 1.7f);
        const float b = 0.5f + 0.5f * sinf(p * 0.53f + 1.7f);
        const float h = (float)WAVE_MAX * (0.18f + 0.82f * a * b);
        const int bh = (int)h;
        const int x = WAVE_X0 + i * WAVE_STEP;
        fb_fill(x, WAVE_Y - bh, 4, bh, C_ACCENT);
        fb_fill(x, WAVE_Y + 1, 4, bh, C_ACCENT_DIM);
    }
}

static const char *const s_boot_steps[] = {
    "starting the display",
    "the classifier is loaded",
    "the radio is listening",
    "bluetooth is advertising",
    "searching for the cots",
};

/* The boot face: the waveform, the name, and what the hub is doing as it
 * comes up. */
static void draw_boot_face(int64_t elapsed_ms, int frame)
{
    fb_fill(0, 0, FB_W, FB_H, C_BG);

    draw_waveform(frame);

    /* The name, breathing a little. */
    const float pulse = 0.5f + 0.5f * sinf((float)frame * 0.12f);
    fb_text_centre(126, "CRYNET", blend(C_TEXT, C_ACCENT, 0.25f + 0.35f * pulse), 4);
    fb_text_centre(164, "INFANT CRY MONITOR", C_DIM, 1);

    /* The boot steps and a progress bar that fills as they go. */
    int step = (int)(elapsed_ms / (BOOT_MS / 5));
    if (step > 4) { step = 4; }
    fb_text_centre(190, s_boot_steps[step], C_ACCENT, 1);

    const int bar_x = 90, bar_w = 140, bar_y = 206;
    const float prog = (float)elapsed_ms / (float)BOOT_MS;
    int filled = (int)(bar_w * (prog > 1.0f ? 1.0f : prog));
    fb_fill(bar_x, bar_y, bar_w, 6, C_SURFACE_HI);
    if (filled > 0) {
        fb_fill(bar_x, bar_y, filled, 6, C_ACCENT);
    }
    fb_rect(bar_x - 1, bar_y - 1, bar_w + 2, 8, C_BORDER);

    fb_text_centre(222, "esp32-s3 hub", C_DIM, 1);
}

/* The title card.
 *
 * This is the project's own face, and it carries three things: what the
 * device is, who built it, and the number it is registered under.  The
 * font is upper case only, so the name is set the way it would be set on
 * a certificate, and the id number is given room to be read.
 *
 * The full project title is long — eighty characters — and the panel is
 * 320 pixels wide, which is fifty-three characters at the small size.
 * So it is set across three lines, and the last word of the second line
 * hangs a little short, which is what a title does.
 */
static void draw_title_face(int64_t elapsed_ms, int frame)
{
    fb_fill(0, 0, FB_W, FB_H, C_BG);

    /* A quiet accent band across the top, so the card has a top edge. */
    fb_fill(0, 0, FB_W, 3, C_ACCENT_DIM);
    fb_fill(0, 0, 60, 3, C_ACCENT);

    fb_text_centre(22, "CRYNET", C_ACCENT, 2);
    fb_text_centre(44, "A MULTI-NODE INFANT CRY DETECTION SYSTEM",
                   C_DIM, 1);

    /* The title, in three lines, in the dim colour so it reads as the
     * caption rather than as the headline. */
    fb_text_centre(74, "DESIGN AND CONSTRUCTION OF A", C_DIM, 1);
    fb_text_centre(86, "MULTI-NODE INFANT CRY DETECTION", C_DIM, 1);
    fb_text_centre(98, "SYSTEM WITH WEARABLE CAREGIVER ALERT", C_DIM, 1);

    /* A rule, then the name and the id number.  These are the two
     * things a panel has to say if the person standing in front of it
     * is the person who built it. */
    fb_fill(60, 120, 200, 1, C_BORDER);

    /* The name, breathing gently like the wordmark does on the boot
     * face — the same hand, so the two faces belong together. */
    const float pulse = 0.5f + 0.5f * sinf((float)frame * 0.09f);
    fb_text_centre(136, "AMAZING AYOMIKUN ADELOWO",
                   blend(C_TEXT, C_ACCENT, 0.10f + 0.20f * pulse), 2);

    fb_text_centre(170, "22/05/04/0029", C_DIM, 1);

    /* The last line: what this device is in the project, so the panel
     * names its own role as well as its owner. */
    fb_text_centre(206, "ESP32-S3 HUB  -  TWO COT NODES", C_DIM, 1);

    /* A waveform along the bottom edge, tying the card to the boot
     * face: the same bars, moving. */
    const float t = (float)frame * 0.18f;
    for (int i = 0; i < 48; i++) {
        const float p = t + i * 0.42f;
        const float a = 0.5f + 0.5f * sinf(p * 1.7f);
        const float b = 0.5f + 0.5f * sinf(p * 0.53f + 1.7f);
        const int bh = (int)(6.0f * (0.18f + 0.82f * a * b));
        fb_fill(i * 7, FB_H - 1 - bh, 4, bh, C_ACCENT_DIM);
    }
}

/* The splash, whichever act of it is running now. */
static void draw_splash(int64_t elapsed_ms, int frame)
{
    if (elapsed_ms < BOOT_MS) {
        draw_boot_face(elapsed_ms, frame);
        return;
    }
    if (elapsed_ms < BOOT_MS + FADE_MS) {
        /* The boot face dissolving into the title card. */
        draw_boot_face(elapsed_ms, frame);
        fb_fade(C_BG, (float)(elapsed_ms - BOOT_MS) / (float)FADE_MS);
        return;
    }
    draw_title_face(elapsed_ms, frame);
}

/* ------------------------------------------------------------------ */
/* The dashboard                                                        */
/* ------------------------------------------------------------------ */

/* A pill with the colour chosen by the caller: the NODE pill has two
 * states, and the WEARABLE pill has three — attached, waiting to be
 * attached, and the Bluetooth stack itself down. */
static void draw_pill_col(int x, int y, const char *label, uint16_t col)
{
    fb_fill(x, y + 2, 6, 6, col);
    fb_text(x + 10, y, label, col, 1);
}

/* The full-scale of the level bar: the RMS that fills it.
 *
 * The bar used to be scaled against 1.0, which is the RMS of a signal
 * that is clipping, and a cry does not clip: the loudest genuine cry
 * measured on the bench carried an RMS of 0.18, and the quietest one
 * the system has to catch carried 0.010.  Against a full scale of 1.0
 * even a cry filled a third of the bar, so the bar never said anything
 * and the number beside it was the only thing worth reading.
 *
 * 0.25 is the full scale now: a scream fills most of the bar, a cry at
 * one metre fills about two thirds, and a quiet room shows a sliver.
 * The scale is square-rooted, so the quiet end of the range is not
 * squashed into nothing -- the interesting part of this bar is the
 * bottom fifth of the scale, where the trigger sits. */
#define LEVEL_BAR_FULL 0.25f

/* Where the cot's own trigger sits on the bar: the level it sends
 * audio over.  This is the number the notch marks, and it is the one
 * the "level" in the project's vocabulary means: the threshold, not
 * the loudness.  The loudness is the RMS. */
static void draw_level_bar(int x, int y, int w, int h, float level,
                           float trigger, bool crying, bool known)
{
    /* An empty bar in a full-strength frame reads as "active" - part of
     * why the no-signal cards looked busier than the live ones - so a
     * dead card's track and frame are washed towards the background. */
    fb_fill(x, y, w, h, known ? C_SURFACE_HI : C_SURFACE);

    float v = level;
    if (v < 0.0f) { v = 0.0f; }
    if (v > LEVEL_BAR_FULL) { v = LEVEL_BAR_FULL; }
    const float frac = sqrtf(v / LEVEL_BAR_FULL);

    /* The colour says whether the cot is over its own trigger: a cot
     * below it is only being listened to, a cot over it is sending
     * audio to the hub. */
    uint16_t col = C_GREEN;
    if (crying) {
        col = C_ALERT;
    } else if (trigger > 0.0f && level >= trigger) {
        col = C_AMBER;
    }

    const int fill_w = (int)(frac * (float)(w - 2) + 0.5f);
    if (fill_w > 0) {
        fb_fill(x + 1, y + 1, fill_w, h - 2, col);
    }

    /* The notch: where this cot's trigger sits.  It is what turns the
     * bar from "a number in colour" into a picture of the decision the
     * cot is about to make -- the bar crosses the notch, the cot sends
     * its audio, and the hub gets to judge it. */
    if (known && trigger > 0.0f) {
        float t = trigger;
        if (t > LEVEL_BAR_FULL) { t = LEVEL_BAR_FULL; }
        const int nx = x + 1 + (int)(sqrtf(t / LEVEL_BAR_FULL) *
                                     (float)(w - 2) + 0.5f);
        if (nx > x && nx < x + w - 1) {
            fb_fill(nx, y, 1, h, C_TEXT);
        }
    }

    fb_rect(x, y, w, h, known ? C_BORDER : blend(C_BORDER, C_BG, 0.45f));
}

/* The battery percentage, read off the cell voltage.
 *
 * This is a resting-voltage curve for an ordinary Li-Po, not a
 * measurement of this project's cell -- none has been profiled yet
 * (SYSTEM_WIRING.md 7 says percentages must come from the actual cell,
 * not nominal voltages).  It is shown with a tilde, and it only has to
 * separate "fine" from "charge soon"; when the real cell has been
 * measured through a discharge, this table gets replaced with its
 * curve. */
static const uint16_t BAT_CURVE[][2] = {
    /* millivolts, percent */
    { 4200, 100 }, { 4050,  90 }, { 3900,  65 }, { 3800,  40 },
    { 3700,  20 }, { 3550,   8 }, { 3450,   3 }, { 3300,   0 },
};

static uint8_t battery_percent(uint16_t mv)
{
    if (mv >= BAT_CURVE[0][0]) {
        return 100;
    }
    for (size_t i = 1; i < sizeof BAT_CURVE / sizeof BAT_CURVE[0]; i++) {
        if (mv >= BAT_CURVE[i][0]) {
            const uint32_t span = BAT_CURVE[i - 1][0] - BAT_CURVE[i][0];
            const uint32_t up = mv - BAT_CURVE[i][0];
            const uint32_t pct = BAT_CURVE[i][1] +
                (up * (uint32_t)(BAT_CURVE[i - 1][1] - BAT_CURVE[i][1])) / span;
            return (uint8_t)(pct > 100u ? 100u : pct);
        }
    }
    return 0;
}

/* How many bars a telemetry RSSI is worth.  2.4 GHz links in a house:
 * anything above -60 dBm is a strong link, below -90 is barely there. */
static int rssi_bars(int8_t rssi)
{
    if (rssi == 0) {
        return 0;
    }
    if (rssi >= -60) { return 4; }
    if (rssi >= -70) { return 3; }
    if (rssi >= -80) { return 2; }
    if (rssi >= -90) { return 1; }
    return 0;
}

/* A small signal-strength glyph: four vertical bars, bottom aligned,
 * filled up to `bars`.  Drawn at the bottom-left of a cot card.
 *
 * The filled bars are coloured by how good the link is, not just by
 * being filled: a cot the hub can barely hear is an amber bar rather
 * than a green one, so the caregiver sees a weak link without reading
 * a number.  A cot that is not answering at all has no bars and the
 * card says OFFLINE, so nothing here has to carry that. */
static void draw_signal_bars(int x, int y, int bars)
{
    const uint16_t col = (bars >= 3) ? C_GREEN : C_AMBER;
    for (int i = 0; i < 4; i++) {
        const int h = 4 + i * 3;
        fb_fill(x + i * 5, y - h, 3, h, (i < bars) ? col : C_SURFACE_HI);
    }
}

/* The battery, right-aligned on the bottom row of a cot card. */
static void draw_battery(int x, int y, int w, const hub_display_node_t *n)
{
    char bat[40];
    uint16_t col;
    switch (n->battery_band) {
    case HUB_BAT_NORMAL:
        snprintf(bat, sizeof bat, "BAT ~%u%%", (unsigned)battery_percent(n->battery_mv));
        col = C_GREEN;
        break;
    case HUB_BAT_LOW:
        snprintf(bat, sizeof bat, "BAT LOW");
        col = C_AMBER;
        break;
    case HUB_BAT_CRITICAL:
        snprintf(bat, sizeof bat, "BAT CRIT");
        col = C_ALERT;
        break;
    default:            /* HUB_BAT_NONE: no reading, no claim */
        return;
    }
    fb_text(x + w - fb_text_w(bat, 1), y, bat, col, 1);
}

static void draw_dashboard(const hub_display_state_t *st)
{
    fb_fill(0, 0, FB_W, FB_H, C_BG);

    /* ---- the header ---- */
    fb_fill(0, 0, FB_W, HEADER_H, C_HEADER);
    fb_text(12, 8, "CRYNET", C_ACCENT, 2);
    fb_text(90, 12, "S3 HUB", C_DIM, 1);
    /* The cot link: green while at least one cot is answering, amber
     * once every card has gone quiet.  Amber, not the dim grey the
     * first version used, so both pills read the same way — green is
     * working, amber is waiting, and there is one rule to learn. */
    draw_pill_col(196, 11, "NODE", st->linked ? C_GREEN : C_AMBER);
    /* The caregiver's device — the wearable, which uses the same GATT
     * service — is the other half of the system, so its state belongs
     * on the panel: green when one is connected and subscribed, amber
     * when the stack is up but nobody has attached yet, dim when
     * Bluetooth itself is down. */
    const uint16_t wearable_col = (st->ble_clients > 0) ? C_GREEN
                                : (st->ble_ready ? C_AMBER : C_DIM);
    draw_pill_col(258, 11, "WEARABLE", wearable_col);
    fb_fill(0, HEADER_H, FB_W, 2, C_ACCENT_DIM);

    /* ---- the banner: what the system is doing ---- */
    uint16_t banner_col = C_DIM;
    const char *banner = "SEARCHING FOR THE COTS";
    if (st->crying) {
        banner = "CRY DETECTED";
        banner_col = C_ALERT;
    } else if (st->linked) {
        banner = "LISTENING";
        banner_col = C_ACCENT;
    }
    fb_round_fill(BANNER_X, BANNER_Y, BANNER_W, BANNER_H, 8,
                  blend(C_SURFACE, banner_col, 0.12f));
    fb_round_rect(BANNER_X, BANNER_Y, BANNER_W, BANNER_H, 8,
                  blend(C_BORDER, banner_col, st->crying ? 0.85f : 0.25f));
    /* A short bar of the state colour down the left edge. */
    fb_fill(BANNER_X + 3, BANNER_Y + 10, 3, BANNER_H - 20, banner_col);
    fb_text(BANNER_X + 16, BANNER_Y + 9, banner, banner_col, 2);

    char right[24];
    if (st->crying) {
        snprintf(right, sizeof right, "COT %u  %u%%", st->cot_id,
                 st->confidence);
    } else if (st->linked) {
        /* The banner's number is the loudness of the room at the cot
         * the hub is listening to.
         *
         * It used to be labelled LEVEL, which was wrong twice over:
         * the number is an RMS, and "level" already means the trigger
         * threshold everywhere else in this project — the console
         * prints "rms" and "level" as two different numbers, and the
         * word on the panel meant the third thing again.  One word,
         * one number: the panel says RMS, and the help page says what
         * an RMS is. */
        snprintf(right, sizeof right, "COT %u  RMS %.3f", st->cot_id,
                 (double)st->rms);
    } else {
        snprintf(right, sizeof right, "--");
    }
    fb_text(BANNER_X + BANNER_W - 12 - fb_text_w(right, 1), BANNER_Y + 26,
            right, C_DIM, 1);

    /* A cry that nobody is attached to hear goes nowhere, and the
     * caregiver has to know that before they go looking for their
     * phone. */
    if (st->crying && st->ble_clients == 0) {
        fb_text(BANNER_X + 16, BANNER_Y + 26, "ALERT NOT DELIVERED",
                C_AMBER, 1);
    }

    /* ---- a card for every cot ---- */
    const int count = st->node_count > HUB_DISPLAY_MAX_NODES
                    ? HUB_DISPLAY_MAX_NODES : st->node_count;
    unsigned online = 0;
    for (int i = 0; i < count; i++) {
        const int y = CARD_Y0 + i * CARD_STEP;
        const hub_display_node_t *n = &st->nodes[i];
        const bool known = n->online;
        const uint16_t accent = n->crying ? C_ALERT
                             : (known ? C_ACCENT : C_BORDER);
        /* The fills are the one thing swapped by hand.  The reader saw
         * the accent-washed fill as faint and the border-washed one as
         * the denser, more active surface - the opposite of what the
         * accent wash was meant to say - so a live card wears the
         * border-washed fill and a dead card the faint accent wash. */
        const uint16_t fill_col = n->crying ? C_ALERT
                                : (known ? C_BORDER : C_ACCENT);

        if (known) {
            online++;
        }

        fb_round_fill(CARD_X, y, CARD_W, CARD_H, 6,
                      blend(C_SURFACE, fill_col, n->crying ? 0.16f : 0.05f));
        /* The outline is the state, at full strength: a cot that is
         * answering gets the vibrant teal - rose, when it cries - and a
         * cot that has gone quiet gets the border washed towards the
         * background.  The first version had this backwards in effect:
         * the online outline was a 45 % blend while the no-signal cards
         * carried the plain border, so the dead cards read as the
         * livelier ones from the chair. */
        fb_round_rect(CARD_X, y, CARD_W, CARD_H, 6,
                      known || n->crying ? accent
                                         : blend(C_BORDER, C_BG, 0.45f));

        char name[8];
        snprintf(name, sizeof name, "COT %u", (unsigned)(i + 1));
        fb_text(CARD_X + 14, y + 8, name, known ? C_TEXT : C_DIM, 2);

        const char *state;
        uint16_t state_col;
        if (n->crying) {
            snprintf(right, sizeof right, "CRY %u%%", (unsigned)n->confidence);
            state = right;
            state_col = C_ALERT;
        } else if (n->deaf) {
            /* It is transmitting and the hub still cannot get its
             * audio, so it cannot announce a cry.  It is not being
             * watched, and the card has to say so. */
            state = "DEAF";
            state_col = C_ALERT;
        } else if (known) {
            state = "ONLINE";
            state_col = C_GREEN;
        } else {
            state = "OFFLINE";
            state_col = C_DIM;
        }
        fb_text(CARD_X + CARD_W - 14 - fb_text_w(state, 1), y + 11, state,
                state_col, 1);

        /* The RMS bar sits in the middle of the card, with its number
         * beside it.  The number used to share the bottom row with the
         * battery, which put three readings on one line and made the
         * card hard to read at a glance in a dark room; the bar and its
         * number are a pair, and the link and the battery are another
         * pair, and each pair has a row of its own.
         *
         * The bar carries a notch at the cot's own trigger: the level
         * it sends audio over.  A cot under its notch is only being
         * listened to; a cot over it is shipping its audio to the hub
         * for the model to judge.  The number beside the bar is the
         * RMS itself — how loud the room is, right now — so the reader
         * can compare the two without guessing. */
        char rms[16];
        snprintf(rms, sizeof rms, "RMS %.3f", (double)(known ? n->rms : 0.0f));
        const int rms_w = fb_text_w(rms, 1);
        draw_level_bar(CARD_X + 14, y + 26, CARD_W - 28 - rms_w - 6, 8,
                       known ? n->rms : 0.0f, known ? n->trigger : 0.0f,
                       n->crying, known);
        fb_text(CARD_X + CARD_W - 14 - rms_w, y + 26, rms,
                known ? C_TEXT : C_DIM, 1);

        /* Bottom row: the radio link on the left -- a small network bar
         * and the RSSI, or "--" when there is no reading -- and the
         * battery on the right. */
        const int bars = known ? rssi_bars(n->rssi) : 0;
        draw_signal_bars(CARD_X + 14, y + 58, bars);
        char link[24];
        if (!known || n->rssi == 0) {
            snprintf(link, sizeof link, "LINK --");
        } else {
            snprintf(link, sizeof link, "LINK %d dBm", (int)n->rssi);
        }
        fb_text(CARD_X + 14 + 4 * 5 + 4, y + 51, link, C_DIM, 1);
        if (known) {
            draw_battery(CARD_X + 14, y + 51, CARD_W - 28, n);
        }
    }

    /* ---- the footer ----
     * The footer counts the cots that are actually answering, not the
     * cards on the screen.  A card for a cot that has gone quiet reads
     * NO SIGNAL, so "3 cots linked" printed above two NO SIGNAL cards
     * would be a lie — and the panel is the one place the caregiver is
     * certain to look. */
    char foot[40];
    if (online == 0) {
        snprintf(foot, sizeof foot, "no cots linked");
    } else {
        snprintf(foot, sizeof foot, "%u cot%s linked", online,
                 online == 1 ? "" : "s");
    }
    fb_text(12, FOOT_Y, foot, C_DIM, 1);

    char up[24];
    const uint32_t up_s = st->uptime_s;
    snprintf(up, sizeof up, "up %u:%02u", (unsigned)(up_s / 60),
             (unsigned)(up_s % 60));
    fb_text(FB_W - 12 - fb_text_w(up, 1), FOOT_Y, up, C_DIM, 1);
}

/* ------------------------------------------------------------------ */
/* The colour check                                                      */
/* ------------------------------------------------------------------ */

/* The palette, as swatches.
 *
 * A photograph of the panel cannot settle whether a colour is right:
 * the camera opens up for a glowing screen in a dark room, the
 * highlights clip, and the white balance drifts with what it sees.  The
 * first photograph of this panel came out with every colour exchanged
 * and the second came out blue, and neither could be trusted without
 * the swatches below to say what the panel was actually asked to draw.
 *
 * The grid is ordered so that the answers are unambiguous: black and
 * white at the ends of the first row, the accent in the middle, and
 * the alert colour last, where a red that is really a swapped blue
 * cannot hide.  Under it is a ramp of the darks, which is where this
 * panel does something unusual: a (12,20,32) navy comes back as a
 * saturated blue while a (0,0,0) black stays black, so the ramp says
 * in one row how far up the dark end the glass lifts. */
static void draw_colour_check(void)
{
    fb_fill(0, 0, FB_W, FB_H, C_BG);

    fb_fill(0, 0, FB_W, HEADER_H, C_HEADER);
    fb_text(12, 8, "COLOUR CHECK", C_TEXT, 2);
    fb_fill(0, HEADER_H, FB_W, 2, C_ACCENT_DIM);

    static const struct {
        const char *name;
        uint16_t colour;
    } swatches[] = {
        {"BLACK",  DISPLAY_RGB(0, 0, 0)},
        {"WHITE",  DISPLAY_RGB(255, 255, 255)},
        {"TEAL",   C_ACCENT},
        {"NAVY",   DISPLAY_RGB(12, 20, 32)},
        {"GREEN",  C_GREEN},
        {"AMBER",  C_AMBER},
        {"ROSE",   C_ALERT},
        {"GREY",   C_DIM},
    };
    const int n = (int)(sizeof swatches / sizeof swatches[0]);
    const int cols = 4;
    const int w = 74, h = 56, gap = 6;
    const int x0 = (FB_W - (cols * w + (cols - 1) * gap)) / 2;

    for (int i = 0; i < n; i++) {
        const int cx = x0 + (i % cols) * (w + gap);
        const int cy = 40 + (i / cols) * (h + 24);
        fb_fill(cx, cy, w, h, swatches[i].colour);
        fb_rect(cx, cy, w, h, C_BORDER);
        fb_text(cx + (w - fb_text_w(swatches[i].name, 1)) / 2, cy + h + 5,
                swatches[i].name, C_DIM, 1);
    }

    /* The dark ramp: the same hue, six steps.  The step that reads
     * brightest is the one the panel is lifting, and how it lifts is
     * the panel's own curve rather than the camera's. */
    static const uint16_t ramp[] = {
        DISPLAY_RGB(0, 0, 0),   DISPLAY_RGB(2, 4, 4),
        DISPLAY_RGB(4, 8, 8),   DISPLAY_RGB(7, 15, 16),
        DISPLAY_RGB(12, 26, 28), DISPLAY_RGB(24, 52, 56),
    };
    const int steps = (int)(sizeof ramp / sizeof ramp[0]);
    const int rw = (FB_W - 8) / steps;
    for (int i = 0; i < steps; i++) {
        fb_fill(4 + i * rw, 190, rw, 14, ramp[i]);
    }
    fb_rect(3, 189, rw * steps + 2, 16, C_BORDER);
    fb_text(4, 206, "the dark ramp", C_DIM, 1);

    char foot[48];
    snprintf(foot, sizeof foot, "backlight %u%%  -  press BOOT to go back",
             (unsigned)s_brightness);
    fb_text_centre(FB_H - 14, foot, C_DIM, 1);
}

/* ------------------------------------------------------------------ */
/* The help page                                                       */
/* ------------------------------------------------------------------ */

/* What the numbers on the dashboard mean.
 *
 * The question is the obvious one: the panel says RMS 0.023 next to a
 * bar, and a bar with a notch in it, and LINK -43 dBm, and none of
 * those words explain themselves.  A caregiver standing in front of
 * the panel at three in the morning cannot go and look up what an RMS
 * is, so the panel says it.
 *
 * It is reached from the dashboard with the BOOT button, next to the
 * colour check: the two pages are both for the person looking at the
 * panel, and neither is the running state.
 */
static void draw_help(void)
{
    fb_fill(0, 0, FB_W, FB_H, C_BG);

    fb_fill(0, 0, FB_W, HEADER_H, C_HEADER);
    fb_text(12, 8, "READING THE PANEL", C_TEXT, 2);
    fb_fill(0, HEADER_H, FB_W, 2, C_ACCENT_DIM);

    /* The body is set in the small font with a line every ten pixels:
     * twenty lines fit, and the wording is short because a caregiver
     * reads this once and then remembers it. */
    static const char *const lines[] = {
        "RMS 0.023   how loud the room is right now,",
        "            out of 1.0.  A quiet room is",
        "            near 0.005, a cry at one metre",
        "            is about 0.03 to 0.05.",
        "",
        "THE NOTCH    the level that cot sends audio",
        "            over.  Below it the cot only",
        "            listens; above it the hub gets",
        "            the audio and the model judges.",
        "            The bar turns amber there.",
        "",
        "LINK -43dBm  how strong the radio link to that",
        "            cot is.  -60 and better is strong,",
        "            -90 and worse is barely there.",
        "            The bars are the same number.",
        "",
        "BAT 87%      that cot's battery.",
        "CONF 98%     how sure the model was.",
    };
    const int n = (int)(sizeof lines / sizeof lines[0]);
    for (int i = 0; i < n; i++) {
        const uint16_t col = (lines[i][0] == '\0') ? C_BG
                           : (i < 4 ? C_TEXT : C_DIM);
        fb_text(12, 42 + i * 10, lines[i], col, 1);
    }

    fb_text_centre(FB_H - 14, "press BOOT to go back", C_DIM, 1);
}

/* ------------------------------------------------------------------ */
/* The task                                                             */
/* ------------------------------------------------------------------ */

static void flush_dirty(void)
{
    if (s_dirty_x1 < s_dirty_x0) {
        return;
    }
    const int x = s_dirty_x0, y = s_dirty_y0;
    const int w = s_dirty_x1 - s_dirty_x0 + 1;
    const int h = s_dirty_y1 - s_dirty_y0 + 1;
    s_dirty_x0 = FB_W; s_dirty_y0 = FB_H;
    s_dirty_x1 = -1; s_dirty_y1 = -1;
    ili9341_blit(&s_dev, x, y, w, h, &s_fb[(size_t)y * FB_W + x], FB_W);
}

static void display_task(void *arg)
{
    const TickType_t t0 = xTaskGetTickCount();
    uint32_t seen = 0;
    int frame = 0;
    TickType_t last_dash = 0;
    int button = 1;

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(SPLASH_TICK));

        /* The BOOT button cycles the panel through its three faces:
         * the dashboard, the page that explains the numbers on it, and
         * the colour check.  It is active low, so the press is the edge
         * from high to low. */
        const int pressed = gpio_get_level(PIN_BUTTON);
        if (button == 1 && pressed == 0) {
            s_face = (s_face + 1) % 3;
            ESP_LOGI(TAG, "the button was pressed: %s",
                     s_face == 0 ? "the dashboard"
                       : s_face == 1 ? "the help page" : "the colour check");
        }
        button = pressed;

        hub_display_state_t st;
        uint32_t version;
        portENTER_CRITICAL(&s_lock);
        st = s_state;
        version = s_version;
        portEXIT_CRITICAL(&s_lock);

        const TickType_t now = xTaskGetTickCount();
        const int64_t ms = (int64_t)(now - t0) * portTICK_PERIOD_MS;

        if (ms < SPLASH_MS) {
            draw_splash(ms, frame++);
            flush_dirty();
        } else if (ms < SPLASH_MS + FADE_MS) {
            draw_splash(ms, frame++);
            fb_fade(C_BG, (float)(ms - SPLASH_MS) / (float)FADE_MS);
            flush_dirty();
        } else if (ms < SPLASH_MS + 2 * FADE_MS) {
            draw_dashboard(&st);
            fb_fade(C_BG, 1.0f - (float)(ms - SPLASH_MS - FADE_MS) /
                            (float)FADE_MS);
            flush_dirty();
        } else if (s_face == 1) {
            draw_help();
            flush_dirty();
        } else if (s_face == 2) {
            draw_colour_check();
            flush_dirty();
        } else if (version != seen ||
                   ((now - last_dash) * portTICK_PERIOD_MS) > 1000) {
            seen = version;
            last_dash = now;
            draw_dashboard(&st);
            flush_dirty();
        }
    }
}

bool hub_display_start(void)
{
    if (!ili9341_init(&s_dev, PIN_MOSI, PIN_SCLK, PIN_CS, PIN_DC, PIN_RST,
                      PIN_BL, ROTATION_LANDSCAPE)) {
        return false;
    }

    /* The framebuffer.  320 x 240 RGB565 is 150 KB, which is more than
     * the hub has to spare in internal RAM, so it lives in PSRAM. */
    s_fb = heap_caps_malloc((size_t)FB_W * FB_H * sizeof(uint16_t),
                             MALLOC_CAP_SPIRAM);
    if (s_fb == NULL) {
        ESP_LOGE(TAG, "there is no room for the framebuffer");
        return false;
    }
    memset(s_fb, 0, (size_t)FB_W * FB_H * sizeof(uint16_t));

    s_dirty_x0 = FB_W; s_dirty_y0 = FB_H;
    s_dirty_x1 = -1; s_dirty_y1 = -1;

    /* The BOOT button, which opens the colour check.  It is pulled up
     * here: if the board has no button on it the pin simply stays
     * high, and the dashboard carries on as before. */
    gpio_config_t button = {
        .pin_bit_mask = 1ULL << PIN_BUTTON,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&button);

    /* The backlight, at the level that does not glare. */
    ili9341_backlight_set(&s_dev, s_brightness);

    /* Core 1: the link loop and both radio stacks run on core 0, and a
     * 30 ms SPI burst must not delay a window analysis. */
    if (xTaskCreatePinnedToCore(display_task, "hubdisp", 4096, NULL,
                                3, NULL, 1) != pdPASS) {
        return false;
    }
    ESP_LOGI(TAG, "the display is up: %d x %d", FB_W, FB_H);
    return true;
}

void hub_display_update(const hub_display_state_t *state)
{
    portENTER_CRITICAL(&s_lock);
    s_state = *state;
    s_version++;
    portEXIT_CRITICAL(&s_lock);
}

void hub_display_set_brightness(uint8_t percent)
{
    if (percent > 100) {
        percent = 100;
    }
    s_brightness = percent;
    ili9341_backlight_set(&s_dev, percent);
    ESP_LOGI(TAG, "the backlight is at %u%%", (unsigned)percent);
}

uint8_t hub_display_brightness(void)
{
    return s_brightness;
}
