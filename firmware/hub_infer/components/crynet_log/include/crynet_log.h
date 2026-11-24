/*
 * CryNet hub — the cry log.
 *
 * Every cry the hub hears is written here, in the hub's own flash, and
 * it is written whether or not there is a network.  That is the whole
 * point: the system has to work exactly as it does now with no internet
 * at all, and the record must survive a power cut.  The network, when
 * it is there, takes the records off the hub and puts them on the
 * dashboard; until then they sit in the hub's flash.
 *
 * Where it lives: the partition table reserves six megabytes for it --
 *
 *     storage,  data, spiffs,  0x210000, 0x600000,
 *
 * and the comment on that line says what it is for.  It had never been
 * mounted, which is why the hub kept nothing: the space was there and
 * nothing used it.  This component mounts it and writes to it.
 *
 * What is written: one fixed-size record per event, thirty-two bytes,
 * appended to a file.  A record is one cry episode -- it starts when the
 * model says cry and ends when the cry has been held quiet long enough
 * to be sure it is over -- together with how long it lasted, how
 * confident the model was, and how loud it was.  The other kinds of
 * record (a cot going deaf, the hub starting) are the system's own
 * health, which belongs beside the cry data.
 *
 * The record is written once, when the episode ends, and it is never
 * changed afterwards.  The number the caregiver's wrist shows ("event
 * #1042") is the same number the dashboard shows, so the two can be
 * matched up after the fact.
 */

#ifndef CRYNET_LOG_H
#define CRYNET_LOG_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The kinds of record. */
#define CRYNET_LOG_CRY  1u   /* a cry episode */
#define CRYNET_LOG_DEAF 2u   /* a cot went deaf */
#define CRYNET_LOG_HEARD 3u  /* a deaf cot came back */
#define CRYNET_LOG_BOOT 4u   /* the hub started */
#define CRYNET_LOG_TEST 5u   /* a test alert from the console */

/* One record.  Thirty-two bytes, so that a hundred and twenty-eight of
 * them fill a flash page exactly. */
typedef struct {
    uint32_t seq;             /* the hub's own number for this record */
    uint32_t boot_id;         /* which run of the hub it belongs to */
    uint32_t uptime_ms;       /* when it happened, from the hub's start */
    uint32_t epoch_s;         /* and in the world, if the clock knew */
    uint32_t duration_ms;     /* how long the episode lasted */
    uint16_t peak_rms_milli;  /* the loudest moment, in thousandths */
    uint16_t mean_rms_milli;  /* and the average over the episode */
    uint8_t  kind;            /* one of the kinds above */
    uint8_t  cot;             /* which cot, 1-based */
    uint8_t  peak_conf;       /* the model's highest confidence, percent */
    uint8_t  windows;         /* how many windows the model judged */
    uint32_t reserved;        /* room for the next field */
} __attribute__((packed)) crynet_log_event_t;

/* Mount the log and open the file.  Returns false if the flash could
 * not be mounted -- the hub carries on without a log rather than
 * refusing to work. */
bool crynet_log_init(void);

/* Take the next record number for an event that is happening now, and
 * remember when it started.  The number is returned so that the
 * caregiver's wrist can show it while the episode is still running.
 * Returns 0 if the log is not available. */
uint32_t crynet_log_reserve(uint8_t kind, uint8_t cot);

/* Write the record for an event that has finished.  The numbers are the
 * ones the hub measured while it was happening. */
bool crynet_log_commit(uint32_t seq, uint32_t duration_ms, uint8_t peak_conf,
                        uint8_t windows, uint16_t peak_rms_milli,
                        uint16_t mean_rms_milli);

/* Write a record for an event that needs no waiting: a cot going deaf,
 * the hub starting.  Returns the record's number, or 0 if the log is
 * not available -- the number is what the wrist shows, so it has to
 * come back to the caller. */
uint32_t crynet_log_write(uint8_t kind, uint8_t cot, uint32_t duration_ms,
                          uint8_t peak_conf, uint8_t windows,
                          uint16_t peak_rms_milli, uint16_t mean_rms_milli);

/* The records that have not been sent yet, in the order the file holds
 * them.  Returns how many were written into `out`, and the number the
 * caller may claim as sent once the batch has gone -- everything up to
 * it has been sent, and nothing above it has.  That number is not
 * simply the highest one in the batch: two cots crying at once can end
 * in the opposite order to the one they started in, and an episode
 * that has started but not yet ended holds a number of its own.  The
 * log accounts for both, so no record is ever claimed as sent before
 * it has gone. */
int crynet_log_pending(crynet_log_event_t *out, int max, uint32_t *last_seq);

/* Say that everything up to this number has been sent. */
bool crynet_log_mark_uploaded(uint32_t seq);

/* The last records, newest first, for the console's history command. */
int crynet_log_recent(crynet_log_event_t *out, int max);

/* How many records the log holds, and how many are still to send. */
uint32_t crynet_log_total(void);
uint32_t crynet_log_pending_count(void);

/* Keep the log to a rolling window once the records have been sent.
 * Records that have not been sent are never dropped unless the log has
 * run out of room, and that is said out loud when it happens. */
void crynet_log_trim(void);

/* Throw the log away.  The record numbers carry on, so the dashboard
 * does not confuse the new records with the old ones. */
bool crynet_log_clear(void);

/* The last wall-clock time the hub knew, kept across a restart so that
 * the clock can start from it.  Zero if it never knew.  See
 * crynet_clock.h for why this is needed and what it costs. */
uint64_t crynet_log_last_epoch_ms(void);
bool crynet_log_save_epoch_ms(uint64_t epoch_ms);

/* How many records have been lost to a full log.  It should be nought;
 * anything else is said out loud, because it means the hub was offline
 * long enough to fill six megabytes. */
uint32_t crynet_log_dropped(void);

/* Which run of the hub this is, counting from the first time the log
 * was made. */
uint32_t crynet_log_boot_id(void);

/* Run the on-board proof of the ordering rule: two cots crying at
 * once, the first cry to start ending last, the uploader running in
 * between -- every record must still be sent.  Runs on the chip,
 * against the real component, on its own scratch file: the real log
 * is not touched.  Returns true if the proof held.  See
 * firmware/tools/test_log_order.py for the host model of the same
 * property. */
bool crynet_log_selftest(void);

#ifdef __cplusplus
}
#endif

#endif /* CRYNET_LOG_H */
