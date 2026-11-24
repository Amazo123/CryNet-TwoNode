/*
 * CryNet hub — the network.  See include/crynet_net.h for the rule it
 * lives by: nothing here may stand between a cry and the wrist.
 *
 * One task, ticking once a second, doing whatever is next: join the
 * network, ask the time, post the records.  It is deliberately not
 * clever.  A supervisor that ticks is easy to reason about when the
 * radio is doing three jobs at once, and a second of latency means
 * nothing to a record that is already safe in flash.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "crynet_clock.h"
#include "crynet_log.h"
#include "crynet_net.h"

static const char *TAG = "crynet";

/* ------------------------------------------------------------------
 * The network to join, and where to post.
 *
 * These are the defaults baked into the image so that a freshly
 * flashed hub joins the owner's network with no further steps.  The
 * password is in the source in plain text: this is a nursery monitor
 * on a home network, and the alternative -- a provisioning flow the
 * owner has to run before the hub works -- costs more than it protects.
 * Anything set later with the console's `net` commands is stored in
 * NVS and takes precedence, and NVS is not touched by reflashing.
 *
 * The URL is empty on purpose.  The dashboard runs on the owner's own
 * machine and its address is not knowable at build time; the dashboard
 * prints the exact `net set ...` line to type once it is running.
 * ------------------------------------------------------------------ */
#define DEFAULT_SSID "Amazyn"
#define DEFAULT_PASS "me_mine_me"
#define DEFAULT_URL  ""
#define DEFAULT_NAME "Nursery hub"

#define CRYNET_FW_VERSION "2.0-dashboard"

/* The cots' channel.  node_link.c pins the radio here; joining a
 * router on any other channel would break the link. */
#define COT_CHANNEL 6

#define NVS_NAMESPACE "crynet"

#define BATCH_RECORDS 32
#define BATCHES_PER_TURN 32
#define JSON_CAP 12288
#define RESP_CAP 256

#define UPLOAD_EVERY_S 30
#define RECONNECT_EVERY_S 15
#define WRONG_CHANNEL_RETRY_S 300

#define BIT_IP    (1u << 0)
#define BIT_LOST  (1u << 1)

static char s_ssid[CRYNET_NET_SSID_MAX];
static char s_pass[64];
static char s_url[CRYNET_NET_URL_MAX];
static char s_token[80];
static char s_name[48];
static char s_device[16];

static EventGroupHandle_t s_events;
static bool     s_started = false;
static bool     s_connected = false;
static bool     s_wrong_channel = false;
static bool     s_config_dirty = false;
static bool     s_force_upload = false;
static bool     s_sntp_up = false;
static bool     s_channel_reported = false;
static uint8_t  s_channel = 0;

static int64_t  s_next_connect_us = 0;
static int64_t  s_next_upload_us = 0;
static int64_t  s_channel_retry_us = 0;

static crynet_net_status_t s_st;
static char s_resp[RESP_CAP];
static int  s_resp_len = 0;

static char *s_json = NULL;
static crynet_log_event_t *s_recs = NULL;

/* ------------------------------------------------------------------ */
/* Configuration in NVS.                                               */

static void load_str(nvs_handle_t h, const char *key, char *dst, size_t cap,
                     const char *fallback)
{
    size_t len = cap;
    if (nvs_get_str(h, key, dst, &len) != ESP_OK || dst[0] == 0) {
        snprintf(dst, cap, "%s", fallback);
    }
    dst[cap - 1] = 0;
}

static bool store_str(const char *key, const char *value)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h) != ESP_OK) {
        return false;
    }
    const esp_err_t err = nvs_set_str(h, key, value);
    const esp_err_t commit = nvs_commit(h);
    nvs_close(h);
    return err == ESP_OK && commit == ESP_OK;
}

static void load_config(void)
{
    nvs_handle_t h;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &h) != ESP_OK) {
        snprintf(s_ssid, sizeof(s_ssid), "%s", DEFAULT_SSID);
        snprintf(s_pass, sizeof(s_pass), "%s", DEFAULT_PASS);
        snprintf(s_url, sizeof(s_url), "%s", DEFAULT_URL);
        snprintf(s_name, sizeof(s_name), "%s", DEFAULT_NAME);
        s_token[0] = 0;
        return;
    }
    load_str(h, "ssid", s_ssid, sizeof(s_ssid), DEFAULT_SSID);
    load_str(h, "pass", s_pass, sizeof(s_pass), DEFAULT_PASS);
    load_str(h, "url", s_url, sizeof(s_url), DEFAULT_URL);
    load_str(h, "name", s_name, sizeof(s_name), DEFAULT_NAME);
    load_str(h, "token", s_token, sizeof(s_token), "");
    nvs_close(h);
}

/* ------------------------------------------------------------------ */
/* The radio.  Shared with node_link, which started it.                */

static void radio_events(void *arg, esp_event_base_t base, int32_t id,
                         void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
        uint8_t primary = 0;
        wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
        esp_wifi_get_channel(&primary, &second);
        s_channel = primary;
        if (primary != COT_CHANNEL) {
            /* The router has moved the radio off the cots' channel.
             * Every ESP-NOW frame from here would be lost, so leave
             * now rather than look connected while the wrist is deaf. */
            s_wrong_channel = true;
            s_channel_retry_us = esp_timer_get_time() +
                                 (int64_t)WRONG_CHANNEL_RETRY_S * 1000000;
            esp_wifi_disconnect();
            return;
        }
        s_wrong_channel = false;
        s_channel_reported = false;
        ESP_LOGI(TAG, "joined \"%s\" on channel %u -- the cots' channel, "
                      "so the link is safe", s_ssid, primary);
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_connected = false;
        xEventGroupClearBits(s_events, BIT_IP);
        xEventGroupSetBits(s_events, BIT_LOST);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        s_connected = true;
        xEventGroupSetBits(s_events, BIT_IP);
        const ip_event_got_ip_t *ev = (const ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "address " IPSTR, IP2STR(&ev->ip_info.ip));
    }
}

static void apply_wifi_config(void)
{
    wifi_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    /* The radio's fields are fixed-size and not necessarily terminated:
     * a 32-character name fills its field exactly.  The buffers were
     * zeroed above, so a copy of at most the field's length is right. */
    size_t n = strnlen(s_ssid, sizeof(cfg.sta.ssid));
    memcpy(cfg.sta.ssid, s_ssid, n);
    n = strnlen(s_pass, sizeof(cfg.sta.password));
    memcpy(cfg.sta.password, s_pass, n);
    cfg.sta.threshold.authmode = s_pass[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    cfg.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    esp_wifi_set_config(WIFI_IF_STA, &cfg);
}

/* Put the radio back where the cots can hear it. */
static void restore_cot_channel(void)
{
    uint8_t primary = 0;
    wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
    esp_wifi_get_channel(&primary, &second);
    if (primary != COT_CHANNEL) {
        esp_wifi_set_channel(COT_CHANNEL, WIFI_SECOND_CHAN_NONE);
        ESP_LOGW(TAG, "radio put back on channel %u for the cots", COT_CHANNEL);
    }
}

/* ------------------------------------------------------------------ */
/* The clock.                                                          */

static void on_time_sync(struct timeval *tv)
{
    if (tv == NULL || tv->tv_sec < 1700000000) {
        return;   /* not a believable answer */
    }
    const uint64_t ms = (uint64_t)tv->tv_sec * 1000u +
                        (uint64_t)tv->tv_usec / 1000u;
    crynet_clock_set(ms);
}

static void start_sntp(void)
{
    if (s_sntp_up) {
        return;
    }
    /* Two servers, so one being unreachable does not leave the hub
     * without a clock.  The list has to go through ESP_SNTP_SERVER_LIST:
     * a bare brace pair would read as two macro arguments, not one. */
    esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG_MULTIPLE(
        2, ESP_SNTP_SERVER_LIST("pool.ntp.org", "time.google.com"));
    cfg.sync_cb = on_time_sync;
    cfg.smooth_sync = false;
    if (esp_netif_sntp_init(&cfg) == ESP_OK) {
        s_sntp_up = true;
        ESP_LOGI(TAG, "asking the network what time it is");
    }
}

/* ------------------------------------------------------------------ */
/* Posting the records.                                                */

static const char *kind_name(uint8_t kind)
{
    switch (kind) {
    case CRYNET_LOG_CRY:   return "cry";
    case CRYNET_LOG_DEAF:  return "deaf";
    case CRYNET_LOG_HEARD: return "heard";
    case CRYNET_LOG_BOOT:  return "boot";
    case CRYNET_LOG_TEST:  return "test";
    default:               return "cry";
    }
}

/* A string as JSON needs it.  Only the hub's name can contain anything
 * awkward -- the owner types it at the console -- but a name with a
 * quote in it would otherwise produce a body the dashboard cannot read,
 * and the records would never be accepted. */
static void json_escape(char *out, size_t cap, const char *in)
{
    size_t o = 0;
    for (const unsigned char *p = (const unsigned char *)in; *p; p++) {
        char buf[8];
        int len;
        if (*p == '"' || *p == '\\') {
            buf[0] = '\\';
            buf[1] = (char)*p;
            len = 2;
        } else if (*p < 0x20) {
            len = snprintf(buf, sizeof buf, "\\u%04x", (unsigned)*p);
        } else {
            buf[0] = (char)*p;
            len = 1;
        }
        if (o + (size_t)len >= cap) {
            break;
        }
        memcpy(out + o, buf, (size_t)len);
        o += (size_t)len;
    }
    out[o] = 0;
}

/* Hand-built JSON: ESP-IDF 6.1 ships no cJSON, and the shape is fixed
 * and small enough that a parser would be more code than this. */
static int build_batch(const crynet_log_event_t *recs, int n)
{
    char name[sizeof(s_name) * 6 + 1];
    json_escape(name, sizeof name, s_name);
    int used = snprintf(s_json, JSON_CAP,
                        "{\"device\":\"%s\",\"hub\":{\"fw\":\"%s\","
                        "\"name\":\"%s\"},\"events\":[",
                        s_device, CRYNET_FW_VERSION, name);
    if (used < 0 || used >= JSON_CAP) {
        return -1;
    }
    for (int i = 0; i < n; i++) {
        const crynet_log_event_t *r = &recs[i];
        const uint32_t dur_s = (r->duration_ms + 500u) / 1000u;
        const uint32_t end = r->epoch_s ? r->epoch_s + dur_s : 0;
        const int add = snprintf(
            s_json + used, JSON_CAP - used,
            "%s{\"seq\":%lu,\"kind\":\"%s\",\"cot\":%u,"
            "\"start\":%lu,\"end\":%lu,\"duration_s\":%lu,"
            "\"peak_conf\":%u,\"windows\":%u,"
            "\"peak_rms\":%.4f,\"mean_rms\":%.4f,"
            "\"boot\":%lu,\"uptime_ms\":%lu}",
            i ? "," : "",
            (unsigned long)r->seq, kind_name(r->kind), (unsigned)r->cot,
            (unsigned long)r->epoch_s, (unsigned long)end,
            (unsigned long)dur_s,
            (unsigned)r->peak_conf, (unsigned)r->windows,
            r->peak_rms_milli / 1000.0, r->mean_rms_milli / 1000.0,
            (unsigned long)r->boot_id, (unsigned long)r->uptime_ms);
        if (add < 0 || add >= JSON_CAP - used) {
            return -1;   /* would not fit; send fewer next time */
        }
        used += add;
    }
    if (used + 3 >= JSON_CAP) {
        return -1;
    }
    s_json[used++] = ']';
    s_json[used++] = '}';
    s_json[used] = 0;
    return used;
}

static esp_err_t http_event(esp_http_client_event_t *ev)
{
    if (ev->event_id == HTTP_EVENT_ON_DATA && ev->data_len > 0) {
        int room = RESP_CAP - 1 - s_resp_len;
        if (room > 0) {
            int take = ev->data_len < room ? ev->data_len : room;
            memcpy(s_resp + s_resp_len, ev->data, take);
            s_resp_len += take;
            s_resp[s_resp_len] = 0;
        }
    }
    return ESP_OK;
}

static bool post_batch(const crynet_log_event_t *recs, int n)
{
    const int len = build_batch(recs, n);
    if (len <= 0) {
        snprintf(s_st.last_error, sizeof(s_st.last_error),
                 "a batch would not fit in the buffer");
        return false;
    }

    s_resp_len = 0;
    s_resp[0] = 0;

    esp_http_client_config_t cfg = {
        .url = s_url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 10000,
        .event_handler = http_event,
        .buffer_size = 2048,
        .buffer_size_tx = 2048,
        .keep_alive_enable = true,
#ifdef CONFIG_MBEDTLS_CERTIFICATE_BUNDLE
        .crt_bundle_attach = esp_crt_bundle_attach,
#endif
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (client == NULL) {
        snprintf(s_st.last_error, sizeof(s_st.last_error),
                 "cannot start the HTTP client");
        return false;
    }
    esp_http_client_set_header(client, "Content-Type", "application/json");
    if (s_token[0]) {
        esp_http_client_set_header(client, "X-CryNet-Token", s_token);
    }
    esp_http_client_set_post_field(client, s_json, len);

    const esp_err_t err = esp_http_client_perform(client);
    const int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (err != ESP_OK) {
        snprintf(s_st.last_error, sizeof(s_st.last_error),
                 "%s", esp_err_to_name(err));
        return false;
    }
    if (status < 200 || status >= 300) {
        snprintf(s_st.last_error, sizeof(s_st.last_error),
                 "HTTP %d: %.48s", status, s_resp);
        return false;
    }
    return true;
}

static void upload_turn(void)
{
    int batches = 0;
    for (; batches < BATCHES_PER_TURN; batches++) {
        uint32_t last = 0;
        const int n = crynet_log_pending(s_recs, BATCH_RECORDS, &last);
        if (n <= 0) {
            break;
        }
        if (!post_batch(s_recs, n)) {
            s_st.failures++;
            ESP_LOGW(TAG, "upload failed (%lu in a row): %s",
                     (unsigned long)s_st.failures, s_st.last_error);
            break;
        }
        crynet_log_mark_uploaded(last);
        s_st.uploaded += (uint32_t)n;
        s_st.batches++;
        s_st.failures = 0;
        s_st.last_error[0] = 0;
        s_st.last_ok_epoch_s = (uint32_t)(crynet_clock_epoch_ms() / 1000u);
        ESP_LOGI(TAG, "sent %d records, up to #%lu (%s)", n,
                 (unsigned long)last, s_resp);
        crynet_log_save_epoch_ms(crynet_clock_epoch_ms());
        if (n < BATCH_RECORDS) {
            batches++;
            break;
        }
        /* Let the audio loop and the radio have the chip between
         * batches; nothing here is in a hurry. */
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    if (batches > 0) {
        crynet_log_trim();
    }
}

/* ------------------------------------------------------------------ */
/* The supervisor.                                                     */

static void net_task(void *arg)
{
    (void)arg;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        const int64_t now = esp_timer_get_time();

        if (s_config_dirty) {
            s_config_dirty = false;
            esp_wifi_disconnect();
            apply_wifi_config();
            s_next_connect_us = 0;
            s_wrong_channel = false;
            s_channel_retry_us = 0;
        }

        if (s_ssid[0] == 0) {
            continue;   /* no network configured: do nothing at all */
        }

        if (s_wrong_channel) {
            restore_cot_channel();
            if (!s_channel_reported) {
                s_channel_reported = true;
                ESP_LOGE(TAG, "the router \"%s\" is on channel %u, but the "
                              "cots talk on channel %u. Left the network so "
                              "the cots keep working. Set the router's "
                              "2.4 GHz channel to %u and the hub will join "
                              "by itself.",
                         s_ssid, s_channel, COT_CHANNEL, COT_CHANNEL);
                snprintf(s_st.last_error, sizeof(s_st.last_error),
                         "router is on channel %u, cots need %u",
                         s_channel, COT_CHANNEL);
            }
            if (now < s_channel_retry_us) {
                continue;
            }
            s_wrong_channel = false;
            s_channel_retry_us = 0;
        }

        if (!s_connected) {
            if (now >= s_next_connect_us) {
                s_next_connect_us = now + (int64_t)RECONNECT_EVERY_S * 1000000;
                esp_wifi_connect();
            }
            continue;
        }

        start_sntp();

        if (s_url[0] == 0) {
            continue;   /* clock only; nothing to post to */
        }
        if (!s_force_upload && now < s_next_upload_us) {
            continue;
        }
        s_force_upload = false;
        /* Back off when it is failing, so a dashboard that is switched
         * off does not cost a connection attempt every thirty seconds. */
        const uint32_t backoff = s_st.failures > 6 ? 6 : s_st.failures;
        s_next_upload_us = now +
            (int64_t)UPLOAD_EVERY_S * 1000000 * (1 + backoff);
        upload_turn();
    }
}

/* ------------------------------------------------------------------ */
/* Starting and steering.                                              */

bool crynet_net_start(void)
{
    if (s_started) {
        return true;
    }

    uint8_t mac[6] = { 0 };
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(s_device, sizeof(s_device), "hub-%02x%02x%02x%02x",
             mac[2], mac[3], mac[4], mac[5]);

    load_config();
    memset(&s_st, 0, sizeof(s_st));
    snprintf(s_st.ssid, sizeof(s_st.ssid), "%s", s_ssid);
    snprintf(s_st.url, sizeof(s_st.url), "%s", s_url);

    s_events = xEventGroupCreate();
    s_json = heap_caps_malloc(JSON_CAP, MALLOC_CAP_SPIRAM);
    if (s_json == NULL) {
        s_json = malloc(JSON_CAP);
    }
    s_recs = heap_caps_malloc(BATCH_RECORDS * sizeof(crynet_log_event_t),
                              MALLOC_CAP_SPIRAM);
    if (s_recs == NULL) {
        s_recs = malloc(BATCH_RECORDS * sizeof(crynet_log_event_t));
    }
    if (s_events == NULL || s_json == NULL || s_recs == NULL) {
        ESP_LOGE(TAG, "no memory for the uploader; the log still records");
        return false;
    }

    /* node_link has already initialised the radio for ESP-NOW.  Only
     * the station interface is missing. */
    wifi_mode_t mode = WIFI_MODE_NULL;
    if (esp_wifi_get_mode(&mode) != ESP_OK) {
        ESP_LOGE(TAG, "the radio is not up; start node_link first");
        return false;
    }
    if (esp_netif_create_default_wifi_sta() == NULL) {
        ESP_LOGE(TAG, "cannot create the station interface");
        return false;
    }
    esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, radio_events, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, radio_events, NULL);

    apply_wifi_config();
    s_started = true;

    if (s_ssid[0] == 0) {
        ESP_LOGI(TAG, "no network configured; the hub records to flash only");
        return true;
    }

    BaseType_t ok = xTaskCreate(net_task, "crynet", 6144, NULL, 3, NULL);
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "cannot start the uploader; the log still records");
        return false;
    }
    ESP_LOGI(TAG, "%s ready: network \"%s\", dashboard %s",
             s_device, s_ssid, s_url[0] ? s_url : "(not set -- log only)");
    return true;
}

bool crynet_net_set_url(const char *url)
{
    if (url == NULL) {
        return false;
    }
    if (url[0] && strncmp(url, "http://", 7) != 0 &&
        strncmp(url, "https://", 8) != 0) {
        ESP_LOGE(TAG, "the address must start with http:// or https://");
        return false;
    }
    if (strlen(url) >= sizeof(s_url)) {
        ESP_LOGE(TAG, "that address is too long");
        return false;
    }
    snprintf(s_url, sizeof(s_url), "%s", url);
    snprintf(s_st.url, sizeof(s_st.url), "%s", s_url);
    s_next_upload_us = 0;
    s_force_upload = true;
    return store_str("url", s_url);
}

bool crynet_net_set_wifi(const char *ssid, const char *password)
{
    if (ssid == NULL || ssid[0] == 0 || strlen(ssid) >= sizeof(s_ssid)) {
        return false;
    }
    if (password && strlen(password) >= sizeof(s_pass)) {
        return false;
    }
    snprintf(s_ssid, sizeof(s_ssid), "%s", ssid);
    snprintf(s_pass, sizeof(s_pass), "%s", password ? password : "");
    snprintf(s_st.ssid, sizeof(s_st.ssid), "%s", s_ssid);
    s_config_dirty = true;
    const bool a = store_str("ssid", s_ssid);
    const bool b = store_str("pass", s_pass);
    return a && b;
}

bool crynet_net_set_token(const char *token)
{
    if (token == NULL || strlen(token) >= sizeof(s_token)) {
        return false;
    }
    snprintf(s_token, sizeof(s_token), "%s", token);
    return store_str("token", s_token);
}

bool crynet_net_set_name(const char *name)
{
    if (name == NULL || name[0] == 0 || strlen(name) >= sizeof(s_name)) {
        return false;
    }
    snprintf(s_name, sizeof(s_name), "%s", name);
    return store_str("name", s_name);
}

void crynet_net_status(crynet_net_status_t *out)
{
    if (out == NULL) {
        return;
    }
    *out = s_st;
    out->wifi_up = s_connected;
    out->channel_ok = !s_wrong_channel;
    out->channel = s_channel;
    out->clock_known = crynet_clock_known();
    snprintf(out->ssid, sizeof(out->ssid), "%s", s_ssid);
    snprintf(out->url, sizeof(out->url), "%s", s_url);
}

void crynet_net_upload_now(void)
{
    s_force_upload = true;
    s_next_upload_us = 0;
}

const char *crynet_net_device_id(void)
{
    return s_device;
}