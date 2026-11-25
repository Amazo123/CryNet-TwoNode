/*
 * CryNet hub — the network, when there is one.
 *
 * The rule this component lives by: the hub must work exactly as it
 * does now with no internet at all.  So nothing here is on the path
 * between a cot's microphone and the caregiver's wrist.  The log is
 * written by the audio loop whether or not this component ever runs;
 * this component only reads the log afterwards and posts it somewhere.
 * If the network is absent, misconfigured, or broken, the only thing
 * that changes is that the records stay on the hub.
 *
 * The one real hazard is the radio.  The cot nodes and the hub talk
 * ESP-NOW on channel 6, fixed -- see node_link.c.  Joining a Wi-Fi
 * network moves the radio to the router's channel, and if that is not
 * 6 the cot link dies: the wrist goes silent while the dashboard looks
 * healthy.  So this component checks the channel the moment it
 * associates, and if it is not 6 it drops the connection immediately,
 * puts the radio back on 6, and says what to do about it.  The router's
 * 2.4 GHz channel has to be set to 6.  That is a one-time change in the
 * router's admin page, and it is the price of one radio doing two jobs.
 *
 * What it does when the network is there:
 *   - asks an NTP server what time it is, and tells crynet_clock, so
 *     that records get real timestamps;
 *   - posts the records that have not been sent, oldest first, in
 *     batches, and marks them sent only when the dashboard says it has
 *     them;
 *   - trims the log once it has been emptied.
 */

#ifndef CRYNET_NET_H
#define CRYNET_NET_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CRYNET_NET_URL_MAX  160
#define CRYNET_NET_SSID_MAX 33

/* How many cots the hub can report on. */
#define CRYNET_NET_MAX_NODES 4

/* What the hub knows about one cot, right now.  The cots have no
 * network of their own -- they talk to the hub over its radio -- so the
 * hub is the only thing that can tell the dashboard who is in the room.
 */
typedef struct {
    uint8_t cot;      /* the cot number, 1-based */
    bool    online;   /* the hub has heard from it lately */
    bool    deaf;     /* the hub cannot get a window from it */
    int8_t  rssi;     /* the telemetry signal strength in dBm; 0 = unknown */
} crynet_net_node_t;

typedef struct {
    char     ssid[CRYNET_NET_SSID_MAX];
    char     url[CRYNET_NET_URL_MAX];
    bool     wifi_up;          /* associated and has an address */
    bool     channel_ok;       /* the router is on the cots' channel */
    uint8_t  channel;          /* the channel the radio is on now */
    bool     clock_known;
    uint32_t uploaded;         /* records sent this boot */
    uint32_t batches;          /* successful posts this boot */
    uint32_t failures;         /* consecutive failures right now */
    uint32_t last_ok_epoch_s;  /* when the dashboard last answered */
    char     last_error[80];
} crynet_net_status_t;

/* Bring up the station and the uploader.  The radio must already be
 * started by node_link_start() -- this component shares it, it does
 * not own it.  Safe to call when there is no network configured: it
 * starts nothing and costs nothing. */
bool crynet_net_start(void);

/* Where to post.  A full URL, e.g.
 *   http://192.168.1.50:8787/api/v1/events
 * Stored in NVS, so it survives a reflash.  An empty string turns
 * uploading off but leaves the clock and the log alone. */
bool crynet_net_set_url(const char *url);

/* Which network to join.  Stored in NVS. */
bool crynet_net_set_wifi(const char *ssid, const char *password);

/* An optional shared secret, sent as X-CryNet-Token. */
bool crynet_net_set_token(const char *token);

/* The name the caregiver sees on the dashboard. */
bool crynet_net_set_name(const char *name);

void crynet_net_status(crynet_net_status_t *out);

/* Ask the uploader to try now rather than wait for its next turn. */
void crynet_net_upload_now(void);

/* Say who is here.  The hub hands over what it knows about each cot --
 * whether it is answering, whether it has gone deaf, how strong its
 * radio is -- and this component posts it to the dashboard, whether or
 * not there is anything in the log to send.
 *
 * That is the point of it: a hub that has been quiet for a week is
 * still a hub that is working, and a dashboard that only learns of a
 * hub when a cry happens cannot say whether the silence is a quiet baby
 * or a dead hub.  The copy is taken here, so the caller's array does
 * not have to outlive the call. */
void crynet_net_set_presence(const crynet_net_node_t *nodes, uint8_t count);

/* Name the thing that decides whether a cot's radio traffic is in
 * flight -- a window being pulled from a cot, say -- and the presence
 * will wait for it rather than take the air from under it.  The link
 * stage registers this, because the link stage is the one that knows.
 * The wait is capped inside the network stage, so a guard that is
 * stuck saying "busy" can delay a report but never stop the reports:
 * the dashboard may be a few seconds behind, never absent.  Pass NULL
 * to remove one. */
void crynet_net_set_radio_guard(bool (*busy)(void));

/* This hub's identity on the dashboard, e.g. "hub-7c9ebd12". */
const char *crynet_net_device_id(void);

#ifdef __cplusplus
}
#endif

#endif /* CRYNET_NET_H */