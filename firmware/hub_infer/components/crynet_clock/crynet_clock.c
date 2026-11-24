/*
 * CryNet hub — the wall clock.  See include/crynet_clock.h for why it
 * is built the way it is.
 */

#include <stdint.h>

#include "esp_log.h"
#include "esp_timer.h"

#include "crynet_clock.h"

static const char *TAG = "clock";

/* The pair that makes the wall clock: "at this uptime, the time was
 * that".  Both are zero when the clock knows nothing. */
static uint64_t s_base_epoch_ms = 0;
static uint64_t s_base_uptime_ms = 0;
static bool     s_known = false;

void crynet_clock_init(void)
{
    s_base_epoch_ms = 0;
    s_base_uptime_ms = 0;
    s_known = false;
    ESP_LOGI(TAG, "the clock starts empty; it is told the time by the network");
}

void crynet_clock_set(uint64_t epoch_ms)
{
    s_base_epoch_ms = epoch_ms;
    s_base_uptime_ms = esp_timer_get_time() / 1000;
    s_known = true;
    ESP_LOGI(TAG, "the clock is set to %llu ms since the epoch "
                  "(uptime %llu ms)",
             (unsigned long long)epoch_ms, (unsigned long long)s_base_uptime_ms);
}

void crynet_clock_restore(uint64_t epoch_ms)
{
    if (epoch_ms == 0) {
        return;
    }
    s_base_epoch_ms = epoch_ms;
    s_base_uptime_ms = 0;   /* the uptime of this boot starts at zero */
    s_known = true;
    ESP_LOGI(TAG, "the clock starts from the stored time %llu ms since the "
                  "epoch; the network will correct it",
             (unsigned long long)epoch_ms);
}

bool crynet_clock_known(void)
{
    return s_known;
}

uint64_t crynet_clock_uptime_ms(void)
{
    return esp_timer_get_time() / 1000;
}

uint64_t crynet_clock_epoch_ms(void)
{
    if (!s_known) {
        return 0;
    }
    const uint64_t now = esp_timer_get_time() / 1000;
    return s_base_epoch_ms + (now - s_base_uptime_ms);
}
