/*
 * CryNet hub — the wall clock.
 *
 * The hub records every cry it hears, and a record without a time is not
 * much of a record: the whole point of the dashboard is that a caregiver
 * can see that the baby was up at three in the morning, in that cot,
 * most nights this week.  So the hub needs to know what time it is.
 *
 * It has no real-time clock and no battery-backed one.  It gets the time
 * from the network (SNTP) when it is on the network, and it keeps the
 * time it was last given for as long as it is running.  Two rules make
 * that work:
 *
 *   - The hub's own monotonic uptime (the FreeRTOS tick, which never
 *     runs backwards and is not affected by anything else) is the
 *     authority for *how long* it has been running.  The wall clock is
 *     stored as a pair -- "at this uptime, the time was that" -- so a
 *     correction from the network moves the wall clock without moving
 *     the uptime, and no record is ever stamped twice.
 *
 *   - When the hub is restarted, the last time it knew is written to
 *     NVS and read back at boot.  The clock then starts from that time
 *     and runs on the uptime again.  It is wrong by however long the hub
 *     was switched off, which is the price of not having a battery, and
 *     the network corrects it within a minute or two of connecting.
 *
 * The one thing it cannot do is invent a time it never had: before the
 * first correction of a boot, the clock reads as "unknown" and the
 * records written in that window are marked as untimed.  The dashboard
 * counts those and does not place them on a timeline.
 */

#ifndef CRYNET_CLOCK_H
#define CRYNET_CLOCK_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Start the clock.  It knows nothing until it is given a time. */
void crynet_clock_init(void);

/* Set the clock to a trusted time, now.  The network does this. */
void crynet_clock_set(uint64_t epoch_ms);

/* Start the clock from a stored time, at boot.  The time is a little
 * stale -- it is as old as the hub's last contact with the network. */
void crynet_clock_restore(uint64_t epoch_ms);

/* Whether the clock knows what time it is. */
bool crynet_clock_known(void);

/* The time now, in milliseconds since the epoch, or 0 when unknown. */
uint64_t crynet_clock_epoch_ms(void);

/* Milliseconds since the hub started.  Always right. */
uint64_t crynet_clock_uptime_ms(void);

#ifdef __cplusplus
}
#endif

#endif /* CRYNET_CLOCK_H */
