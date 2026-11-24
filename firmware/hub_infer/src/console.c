/*
 * CryNet hub — the bench console.
 *
 * The hub has always logged to its UART; this gives it a way to answer
 * as well.  The commands are few and none of them changes how the
 * system behaves:
 *
 *   help         what the console understands
 *   status       the cots: their level, the window they have, their state
 *   alert <cot>  publish a test alert for that cot, as if it had heard
 *                a cry.  The caregiver's phone buzzes; the wearable
 *                shows "a cry on cot N at 100%"
 *   clear        take the test alert back
 *
 * and, for the record the hub keeps and the dashboard it feeds:
 *
 *   history [n]  the last n records, newest first (10 by default)
 *   log          how many records the hub holds and how many are unsent
 *   log clear    throw the log away; the record numbers carry on
 *   net          the network: whether it is up, and what it has sent
 *   net set <url>    where to post, e.g.
 *                    net set http://192.168.1.50:8787/api/v1/events
 *   net ssid <s> <p> which Wi-Fi to join
 *   net name <name>  the name the dashboard shows for this hub
 *   net token <t>    the shared secret, if the dashboard wants one
 *   upload       try to send the unsent records now
 *
 * None of the network commands changes what the hub does with a cry.
 * With no Wi-Fi and no address the hub records to its own flash and
 * tells the wrist, exactly as it did before the dashboard existed.
 *
 * Why it exists: the last unproven link in the system was the
 * Bluetooth one.  The hub published "a cry on cot 1 at 100%" and the
 * wearable was not attached to see it, so the whole path -- publisher,
 * link, client, display -- was untested.  With this command it can be
 * tested at any time, in any room, without a sound.
 *
 * The console reads the same UART the hub logs to, so a command and
 * the log share the port.  That is why the reader is on its own task
 * and why it only ever reads whole lines: a line of log arriving while
 * a command is being typed is discarded, and a command is only acted
 * on when a newline ends it.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "driver/uart.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "console.h"
#include "crynet_clock.h"
#include "crynet_log.h"
#include "crynet_net.h"
#include "link_stage.h"

static const char *TAG = "console";

/* The longest command the console accepts, and the longest line it
 * will hold while it waits for the newline.  A dashboard address can be
 * a hundred and sixty characters, so the line has to carry one whole. */
#define CONSOLE_LINE_MAX 200

/* The cots the status command reports. */
#define CONSOLE_MAX_COTS 8

static void print_help(void)
{
    ESP_LOGI(TAG, "commands:");
    ESP_LOGI(TAG, "  help          this list");
    ESP_LOGI(TAG, "  status        the cots and what they are hearing");
    ESP_LOGI(TAG, "  alert <cot>   publish a test alert for that cot");
    ESP_LOGI(TAG, "  clear         take the test alert back");
    ESP_LOGI(TAG, "  history [n]   the last n records, newest first");
    ESP_LOGI(TAG, "  log           how much is recorded and how much is unsent");
    ESP_LOGI(TAG, "  log clear     throw the log away");
    ESP_LOGI(TAG, "  net           the network and what it has sent");
    ESP_LOGI(TAG, "  net set <url> where to post the records");
    ESP_LOGI(TAG, "  net ssid <s> <p>  which Wi-Fi to join");
    ESP_LOGI(TAG, "  net name <name>   this hub's name on the dashboard");
    ESP_LOGI(TAG, "  net token <t>     the dashboard's shared secret");
    ESP_LOGI(TAG, "  upload        send the unsent records now");
    ESP_LOGI(TAG, "  logtest       prove, on this chip, that out-of-order "
                  "records are not lost");
}

/* The kind of record, in the word the caregiver would use. */
static const char *kind_name(uint8_t kind)
{
    switch (kind) {
    case CRYNET_LOG_CRY:   return "cry";
    case CRYNET_LOG_DEAF:  return "deaf";
    case CRYNET_LOG_HEARD: return "heard";
    case CRYNET_LOG_BOOT:  return "boot";
    case CRYNET_LOG_TEST:  return "test";
    default:               return "?";
    }
}

/* When a record happened.  The hub has no clock of its own: until it
 * has reached a time server it knows only how long it has been awake,
 * and it says so rather than inventing a date. */
static void format_when(char *out, size_t cap, const crynet_log_event_t *e)
{
    if (e->epoch_s != 0) {
        const time_t t = (time_t)e->epoch_s;
        struct tm tm_utc;
        gmtime_r(&t, &tm_utc);
        strftime(out, cap, "%Y-%m-%d %H:%M:%SZ", &tm_utc);
    } else {
        snprintf(out, cap, "up %lus (no clock)",
                 (unsigned long)(e->uptime_ms / 1000u));
    }
}

/* The history command.  Ten records at a time is what fits on a screen
 * without scrolling the useful part away. */
static void print_history(int want)
{
    if (want < 1) {
        want = 1;
    }
    if (want > 40) {
        want = 40;
    }
    crynet_log_event_t recs[40];
    const int n = crynet_log_recent(recs, want);
    if (n == 0) {
        ESP_LOGI(TAG, "the log is empty");
        return;
    }
    ESP_LOGI(TAG, "the last %d record(s), newest first "
                  "(times are UTC; the dashboard shows your own):", n);
    for (int i = 0; i < n; i++) {
        const crynet_log_event_t *e = &recs[i];
        char when[40];
        format_when(when, sizeof when, e);
        if (e->kind == CRYNET_LOG_CRY) {
            ESP_LOGI(TAG, "  #%-5lu %-5s cot %u  %s  %lu.%lus  "
                          "peak %u%%  rms %.4f/%.4f  %u windows",
                     (unsigned long)e->seq, kind_name(e->kind),
                     (unsigned)e->cot, when,
                     (unsigned long)(e->duration_ms / 1000u),
                     (unsigned long)((e->duration_ms % 1000u) / 100u),
                     (unsigned)e->peak_conf,
                     (double)e->peak_rms_milli / 1000.0,
                     (double)e->mean_rms_milli / 1000.0,
                     (unsigned)e->windows);
        } else {
            ESP_LOGI(TAG, "  #%-5lu %-5s cot %u  %s",
                     (unsigned long)e->seq, kind_name(e->kind),
                     (unsigned)e->cot, when);
        }
    }
}

static void print_log(void)
{
    const uint32_t total = crynet_log_total();
    const uint32_t pending = crynet_log_pending_count();
    const uint32_t dropped = crynet_log_dropped();
    ESP_LOGI(TAG, "the log holds %lu record(s), %lu still to send, "
                  "boot %lu, device %s",
             (unsigned long)total, (unsigned long)pending,
             (unsigned long)crynet_log_boot_id(), crynet_net_device_id());
    ESP_LOGI(TAG, "the clock %s",
             crynet_clock_known() ? "knows the time" :
             "does not know the time yet (records are marked by uptime)");
    if (dropped != 0) {
        ESP_LOGW(TAG, "%lu record(s) were lost: the log filled up while "
                      "the hub had nowhere to send them",
                 (unsigned long)dropped);
    }
}

static void print_net(void)
{
    crynet_net_status_t s;
    crynet_net_status(&s);
    ESP_LOGI(TAG, "wifi \"%s\": %s, channel %u%s",
             s.ssid[0] ? s.ssid : "(none set)",
             s.wifi_up ? "connected" : "not connected",
             (unsigned)s.channel,
             s.channel_ok ? "" : "  <-- NOT the cots' channel");
    if (s.ssid[0] && !s.channel_ok && s.channel != 6) {
        ESP_LOGW(TAG, "the cots talk on channel 6.  Set the router's "
                      "2.4 GHz channel to 6, or the wrist goes silent "
                      "while the dashboard looks healthy.");
    }
    ESP_LOGI(TAG, "dashboard: %s", s.url[0] ? s.url : "(none set)");
    ESP_LOGI(TAG, "sent this boot: %lu record(s) in %lu batch(es), "
                  "%lu failure(s) in a row",
             (unsigned long)s.uploaded, (unsigned long)s.batches,
             (unsigned long)s.failures);
    if (s.last_error[0]) {
        ESP_LOGW(TAG, "last problem: %s", s.last_error);
    }
}

/* Everything after the command word, with the spaces before it gone. */
static const char *arg_after(const char *line, size_t word)
{
    const char *p = line + word;
    while (*p == ' ') {
        p++;
    }
    return p;
}

/* The net commands.  They only write configuration; the uploader picks
 * the change up on its next turn, so nothing here touches the radio
 * from the console's task. */
static void run_net(const char *line)
{
    const char *arg = arg_after(line, 3);
    if (*arg == '\0' || strncmp(arg, "status", 6) == 0) {
        print_net();
        return;
    }
    if (strncmp(arg, "set ", 4) == 0) {
        const char *url = arg_after(arg, 3);
        if (*url == '\0') {
            ESP_LOGW(TAG, "net set needs an address: "
                          "net set http://192.168.1.50:8787/api/v1/events");
            return;
        }
        if (crynet_net_set_url(url)) {
            ESP_LOGI(TAG, "the dashboard is now %s", url);
        }
        return;
    }
    if (strncmp(arg, "ssid ", 5) == 0) {
        const char *p = arg_after(arg, 4);
        const char *space = strchr(p, ' ');
        if (space == NULL) {
            ESP_LOGW(TAG, "net ssid needs both: net ssid Amazyn me_mine_me");
            return;
        }
        char ssid[CRYNET_NET_SSID_MAX];
        const size_t n = (size_t)(space - p);
        if (n == 0 || n >= sizeof ssid) {
            ESP_LOGW(TAG, "a Wi-Fi name is 1 to 32 characters");
            return;
        }
        memcpy(ssid, p, n);
        ssid[n] = '\0';
        const char *pass = arg_after(space, 0);
        if (crynet_net_set_wifi(ssid, pass)) {
            ESP_LOGI(TAG, "the hub will join \"%s\"", ssid);
            ESP_LOGI(TAG, "remember: the router's 2.4 GHz channel must be 6");
        }
        return;
    }
    if (strncmp(arg, "name ", 5) == 0) {
        const char *name = arg_after(arg, 4);
        if (*name && crynet_net_set_name(name)) {
            ESP_LOGI(TAG, "the dashboard will call this hub \"%s\"", name);
        }
        return;
    }
    if (strncmp(arg, "token ", 6) == 0) {
        const char *tok = arg_after(arg, 5);
        if (crynet_net_set_token(tok)) {
            ESP_LOGI(TAG, "the token is stored (%s)",
                     *tok ? "set" : "cleared");
        }
        return;
    }
    ESP_LOGW(TAG, "net understands: status, set <url>, ssid <s> <p>, "
                  "name <name>, token <t>");
}

/* The status command: what the hub knows about each cot. */
static void print_status(void)
{
    link_stage_cot_t cots[CONSOLE_MAX_COTS];
    const int n = link_stage_cots(cots, CONSOLE_MAX_COTS);
    if (n == 0) {
        ESP_LOGI(TAG, "no cot has been heard yet");
        return;
    }
    for (int i = 0; i < n; i++) {
        const link_stage_cot_t *c = &cots[i];
        /* The signal strength is reported with the cot's other numbers,
         * because it is the one reading that says whether the cot is
         * merely quiet or out of reach.  Zero means no reading yet. */
        char link[24];
        if (c->rssi != 0) {
            snprintf(link, sizeof link, "  link %d dBm", (int)c->rssi);
        } else {
            snprintf(link, sizeof link, "  link --");
        }
        ESP_LOGI(TAG, "  cot %u: rms %.4f  level %.4f  window %.4f%s  "
                      "confidence %u%%%s",
                 (unsigned)c->node_id, (double)c->rms, (double)c->level,
                 (double)c->frozen_rms,
                 c->window_full ? " (whole)" : " (filling)",
                 (unsigned)c->confidence, link);
    }
}

/* Run one line.  The line has already had its newline removed. */
static void run_line(const char *line)
{
    ESP_LOGI(TAG, "<< %s", line);

    if (strcmp(line, "help") == 0 || strcmp(line, "?") == 0) {
        print_help();
        return;
    }
    if (strcmp(line, "status") == 0) {
        print_status();
        return;
    }
    if (strcmp(line, "clear") == 0) {
        link_stage_test_clear();
        return;
    }
    if (strncmp(line, "history", 7) == 0) {
        const char *arg = arg_after(line, 7);
        print_history(*arg ? atoi(arg) : 10);
        return;
    }
    if (strncmp(line, "log", 3) == 0) {
        const char *arg = arg_after(line, 3);
        if (strcmp(arg, "clear") == 0) {
            if (crynet_log_clear()) {
                ESP_LOGW(TAG, "the log has been thrown away; the record "
                              "numbers carry on from here");
            }
            return;
        }
        print_log();
        return;
    }
    if (strncmp(line, "net", 3) == 0) {
        run_net(line);
        return;
    }
    if (strcmp(line, "upload") == 0) {
        crynet_net_upload_now();
        ESP_LOGI(TAG, "the uploader has been asked to try now; "
                      "watch for its next line, or type net");
        return;
    }
    if (strcmp(line, "logtest") == 0) {
        /* The proof the ordering rule holds on this chip.  It touches
         * only its own scratch file; the real log is untouched. */
        if (crynet_log_selftest()) {
            ESP_LOGW(TAG, "logtest: PASS");
        } else {
            ESP_LOGE(TAG, "logtest: FAIL -- a record was lost or "
                          "claimed before it was sent");
        }
        return;
    }
    if (strncmp(line, "alert", 5) == 0) {
        const char *arg = line + 5;
        while (*arg == ' ') {
            arg++;
        }
        if (*arg == '\0') {
            ESP_LOGW(TAG, "alert needs a cot number: alert 1");
            return;
        }
        const int cot = atoi(arg);
        if (cot < 1 || cot > 8) {
            ESP_LOGW(TAG, "a cot is numbered 1 to 8, not %d", cot);
            return;
        }
        link_stage_test_alert((uint8_t)cot);
        return;
    }
    ESP_LOGW(TAG, "unknown command: %s", line);
}

/* The console task. */
static void console_task(void *arg)
{
    (void)arg;
    char line[CONSOLE_LINE_MAX];
    int len = 0;

    ESP_LOGI(TAG, "the console is listening: help, status, alert <cot>, "
                  "clear, history, log, net, upload, logtest");

    for (;;) {
        uint8_t c;
        /* A short wait, so the task does not spin on a quiet line. */
        const int n = uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(50));
        if (n != 1) {
            continue;
        }
        if (c == '\r' || c == '\n') {
            if (len > 0) {
                line[len] = '\0';
                run_line(line);
                len = 0;
            }
            continue;
        }
        if (c == 8 || c == 127) {   /* backspace */
            if (len > 0) {
                len--;
            }
            continue;
        }
        if (len < CONSOLE_LINE_MAX - 1) {
            line[len++] = (char)c;
        }
    }
}

void console_start(void)
{
    /* The UART driver has to be installed before anything can be read
     * from the console UART.  The ESP-IDF log writes to that UART
     * without a driver -- it puts the bytes in the hardware's own
     * register -- and the driver, with the receive buffer a command
     * arrives in, is installed only by the console's REPL, which this
     * firmware does not start.
     *
     * Installing it does not disturb the log: the log's own write path
     * keeps using the hardware register, because the VFS only switches
     * to the driver when the REPL takes the port over. */
    const esp_err_t err = uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "the console UART could not be set up: %s",
                 esp_err_to_name(err));
        return;
    }
    /* The history command holds forty records on its stack, so the
     * console needs more than the bare line reader did. */
    xTaskCreate(console_task, "console", 5120, NULL, 3, NULL);
}
