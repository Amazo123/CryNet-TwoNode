/*
 * CryNet hub — the cry log.  See include/crynet_log.h for what it is for.
 *
 * The shape of it: one file of fixed-size records, appended to, and a
 * second tiny file holding the counters.  Two files rather than one
 * because SPIFFS cannot rewrite four bytes in the middle of a file
 * cheaply -- it rewrites the whole file -- and the counters change on
 * every record while the records themselves never change at all.
 *
 * Nothing here is allowed to break the hub.  Every call is best-effort:
 * if the flash will not mount, or a write fails, the log says so and
 * returns, and the cot still cries on the caregiver's wrist exactly as
 * it did before any of this existed.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "esp_log.h"
#include "esp_spiffs.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#include "crynet_clock.h"
#include "crynet_log.h"

static const char *TAG = "crylog";

#define LOG_DIR     "/log"
#define EVENTS_PATH "/log/events.bin"
#define META_PATH   "/log/meta.bin"
#define EVENTS_TMP  "/log/events.tmp"

#define REC_SIZE    32u
#define HEADER_SIZE 16u

/* "CRY1" and "CRYM", read as little-endian words. */
#define EVENTS_MAGIC 0x31595243u
#define META_MAGIC   0x4D595243u
#define FORMAT_VER   1u

/* Six megabytes would hold a hundred and ninety thousand records; the
 * cap is far below that on purpose.  SPIFFS slows down as a file grows
 * and wears the flash while it does it, and a caregiver does not need
 * eight thousand episodes on the hub once they are on the dashboard.
 * At a busy ten cries a night, eight thousand is two years. */
#define MAX_RECORDS       8192u
#define KEEP_AFTER_UPLOAD 2000u

/* Records copied at a time when the log is compacted.  Four kilobytes
 * of stack-free heap, so compaction needs no large allocation. */
#define COPY_CHUNK 128u

/* Episodes that have started and not yet finished.  Two cots can cry
 * at once and a deaf cot can come back mid-cry, so eight is generous. */
#define OPEN_SLOTS 8u

_Static_assert(sizeof(crynet_log_event_t) == REC_SIZE,
               "the record must stay thirty-two bytes");

typedef struct {
    uint32_t magic;
    uint32_t next_seq;       /* the number the next record will get */
    uint32_t uploaded_seq;   /* everything up to here has been sent */
    uint32_t boot_id;
    uint32_t dropped;
    uint32_t reserved;
    uint64_t last_epoch_ms;
} log_meta_t;

_Static_assert(sizeof(log_meta_t) == 32, "the meta file is thirty-two bytes");

typedef struct {
    uint32_t seq;            /* nought means the slot is free */
    uint32_t start_epoch_s;
    uint32_t start_uptime_ms;
    uint8_t  kind;
    uint8_t  cot;
} open_slot_t;

static bool              s_ready = false;
static SemaphoreHandle_t s_lock = NULL;
static int               s_fd = -1;
static log_meta_t        s_meta;
static open_slot_t       s_open[OPEN_SLOTS];

/* ---------------------------------------------------------------- */
/* The file, with the lock already held.                            */

static uint32_t count_locked(void)
{
    struct stat st;
    if (s_fd < 0 || fstat(s_fd, &st) != 0) {
        return 0;
    }
    if (st.st_size <= (off_t)HEADER_SIZE) {
        return 0;
    }
    return (uint32_t)((st.st_size - HEADER_SIZE) / REC_SIZE);
}

static bool read_at_locked(uint32_t index, crynet_log_event_t *out)
{
    const off_t off = (off_t)(HEADER_SIZE + index * REC_SIZE);
    return pread(s_fd, out, REC_SIZE, off) == (ssize_t)REC_SIZE;
}

static bool save_meta_locked(void)
{
    /* Not O_TRUNC.  Truncating would delete the file and build it
     * again, which is more pages of flash than writing the same
     * thirty-two bytes where they already are.  The counters file is
     * written on the path between a cot's microphone and the
     * caregiver's wrist, so what it costs is worth counting. */
    const int fd = open(META_PATH, O_WRONLY | O_CREAT, 0644);
    if (fd < 0) {
        ESP_LOGE(TAG, "cannot write the counters: %s", strerror(errno));
        return false;
    }
    bool ok = pwrite(fd, &s_meta, sizeof(s_meta), 0) == (ssize_t)sizeof(s_meta);
    if (ok && ftruncate(fd, (off_t)sizeof(s_meta)) != 0) {
        ok = false;
    }
    if (ok) {
        fsync(fd);
    }
    close(fd);
    if (!ok) {
        ESP_LOGE(TAG, "the counters did not write: %s", strerror(errno));
    }
    return ok;
}

static bool open_events_locked(void)
{
    if (s_fd >= 0) {
        close(s_fd);
        s_fd = -1;
    }
    s_fd = open(EVENTS_PATH, O_RDWR | O_CREAT, 0644);
    if (s_fd < 0) {
        ESP_LOGE(TAG, "cannot open the log: %s", strerror(errno));
        return false;
    }

    struct stat st;
    if (fstat(s_fd, &st) != 0) {
        return false;
    }

    if (st.st_size == 0) {
        uint32_t head[4] = { EVENTS_MAGIC, FORMAT_VER, REC_SIZE, 0 };
        if (write(s_fd, head, HEADER_SIZE) != (ssize_t)HEADER_SIZE) {
            ESP_LOGE(TAG, "cannot start the log: %s", strerror(errno));
            return false;
        }
        fsync(s_fd);
        return true;
    }

    uint32_t head[4] = { 0, 0, 0, 0 };
    if (pread(s_fd, head, HEADER_SIZE, 0) != (ssize_t)HEADER_SIZE ||
        head[0] != EVENTS_MAGIC || head[2] != REC_SIZE) {
        /* Not a log we wrote, or one from a format we no longer read.
         * Start again rather than append nonsense to it.  The record
         * numbers carry on so the dashboard is never confused. */
        ESP_LOGW(TAG, "the log file is not one of ours; starting a new one");
        close(s_fd);
        unlink(EVENTS_PATH);
        s_fd = open(EVENTS_PATH, O_RDWR | O_CREAT | O_TRUNC, 0644);
        if (s_fd < 0) {
            return false;
        }
        head[0] = EVENTS_MAGIC; head[1] = FORMAT_VER;
        head[2] = REC_SIZE;     head[3] = 0;
        return write(s_fd, head, HEADER_SIZE) == (ssize_t)HEADER_SIZE;
    }

    /* A power cut mid-append can leave half a record.  Cut it off, so
     * that every record after it still lands on its own boundary. */
    const off_t whole = (off_t)(HEADER_SIZE +
                                ((st.st_size - HEADER_SIZE) / REC_SIZE) * REC_SIZE);
    if (whole != st.st_size) {
        ESP_LOGW(TAG, "a half-written record at the end of the log; trimming it");
        if (ftruncate(s_fd, whole) != 0) {
            ESP_LOGE(TAG, "cannot trim the log: %s", strerror(errno));
        }
        fsync(s_fd);
    }
    return true;
}

static bool append_locked(const crynet_log_event_t *rec)
{
    if (s_fd < 0 && !open_events_locked()) {
        return false;
    }
    if (lseek(s_fd, 0, SEEK_END) == (off_t)-1) {
        return false;
    }
    if (write(s_fd, rec, REC_SIZE) != (ssize_t)REC_SIZE) {
        ESP_LOGE(TAG, "record %lu did not write: %s",
                 (unsigned long)rec->seq, strerror(errno));
        /* The next write must not land after a partial one. */
        const uint32_t n = count_locked();
        ftruncate(s_fd, (off_t)(HEADER_SIZE + n * REC_SIZE));
        return false;
    }
    fsync(s_fd);
    return true;
}

/* The index of the first record numbered above `seq`.  The numbers only
 * ever go up, so this is a binary search -- a handful of reads even
 * with eight thousand records in the file. */
static uint32_t first_above_locked(uint32_t seq)
{
    uint32_t lo = 0;
    uint32_t hi = count_locked();
    crynet_log_event_t rec;
    while (lo < hi) {
        const uint32_t mid = lo + (hi - lo) / 2;
        if (read_at_locked(mid, &rec) && rec.seq > seq) {
            hi = mid;
        } else {
            lo = mid + 1;
        }
    }
    return lo;
}

/* ---------------------------------------------------------------- */
/* Starting up.                                                      */

bool crynet_log_init(void)
{
    if (s_ready) {
        return true;
    }
    if (s_lock == NULL) {
        s_lock = xSemaphoreCreateMutex();
        if (s_lock == NULL) {
            return false;
        }
    }

    const esp_vfs_spiffs_conf_t conf = {
        .base_path = LOG_DIR,
        .partition_label = "storage",
        .max_files = 4,
        .format_if_mount_failed = true,
    };
    esp_err_t err = esp_vfs_spiffs_register(&conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "the storage partition will not mount (%s); "
                      "the hub carries on without a log",
                 esp_err_to_name(err));
        return false;
    }

    size_t total = 0, used = 0;
    if (esp_spiffs_info("storage", &total, &used) == ESP_OK) {
        ESP_LOGI(TAG, "storage mounted: %u of %u bytes used",
                 (unsigned)used, (unsigned)total);
    }

    xSemaphoreTake(s_lock, portMAX_DELAY);

    memset(&s_meta, 0, sizeof(s_meta));
    memset(s_open, 0, sizeof(s_open));
    s_meta.magic = META_MAGIC;
    s_meta.next_seq = 1;

    const int fd = open(META_PATH, O_RDONLY);
    if (fd >= 0) {
        log_meta_t stored;
        if (read(fd, &stored, sizeof(stored)) == (ssize_t)sizeof(stored) &&
            stored.magic == META_MAGIC && stored.next_seq != 0) {
            s_meta = stored;
        } else {
            ESP_LOGW(TAG, "the counters were unreadable; starting from one");
        }
        close(fd);
    }
    s_meta.boot_id++;
    s_meta.reserved = 0;

    if (!open_events_locked()) {
        xSemaphoreGive(s_lock);
        esp_vfs_spiffs_unregister("storage");
        return false;
    }
    save_meta_locked();

    const uint32_t n = count_locked();
    const uint32_t pending = n - first_above_locked(s_meta.uploaded_seq);
    s_ready = true;

    ESP_LOGI(TAG, "boot %lu: %lu records kept, %lu still to send, "
                  "next number %lu",
             (unsigned long)s_meta.boot_id, (unsigned long)n,
             (unsigned long)pending, (unsigned long)s_meta.next_seq);
    if (s_meta.dropped) {
        ESP_LOGW(TAG, "%lu records were lost to a full log before this boot",
                 (unsigned long)s_meta.dropped);
    }

    xSemaphoreGive(s_lock);
    return true;
}

/* ---------------------------------------------------------------- */
/* Writing.                                                          */

uint32_t crynet_log_reserve(uint8_t kind, uint8_t cot)
{
    if (!s_ready) {
        return 0;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);

    const int64_t t0 = esp_timer_get_time();
    const uint32_t seq = s_meta.next_seq++;
    /* Saved now, not at commit: if the hub loses power mid-cry, the
     * number is spent and the next boot leaves a hole rather than
     * handing the same number to a different cry.
     *
     * This is the one flash write that happens while a cot is crying,
     * so its cost is measured and printed: the owner can see what it
     * actually costs on the board in front of them rather than take
     * an estimate on trust. */
    save_meta_locked();
    const int64_t t1 = esp_timer_get_time();
    ESP_LOGI(TAG, "record %lu: the number was made durable in %lld ms",
             (unsigned long)seq, (long long)((t1 - t0) / 1000));

    int slot = -1;
    for (int i = 0; i < OPEN_SLOTS; i++) {
        if (s_open[i].seq == 0) {
            slot = i;
            break;
        }
    }
    if (slot < 0) {
        /* Should not happen with two cots.  Say so, and drop the
         * oldest rather than refuse the new cry. */
        slot = 0;
        for (int i = 1; i < OPEN_SLOTS; i++) {
            if (s_open[i].seq < s_open[slot].seq) {
                slot = i;
            }
        }
        ESP_LOGW(TAG, "more than %u episodes open at once; forgetting %lu",
                 OPEN_SLOTS, (unsigned long)s_open[slot].seq);
    }

    const uint64_t epoch_ms = crynet_clock_epoch_ms();
    s_open[slot].seq = seq;
    s_open[slot].kind = kind;
    s_open[slot].cot = cot;
    s_open[slot].start_epoch_s = (uint32_t)(epoch_ms / 1000u);
    s_open[slot].start_uptime_ms = (uint32_t)crynet_clock_uptime_ms();

    xSemaphoreGive(s_lock);
    return seq;
}

bool crynet_log_commit(uint32_t seq, uint32_t duration_ms, uint8_t peak_conf,
                       uint8_t windows, uint16_t peak_rms_milli,
                       uint16_t mean_rms_milli)
{
    if (!s_ready || seq == 0) {
        return false;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);

    int slot = -1;
    for (int i = 0; i < OPEN_SLOTS; i++) {
        if (s_open[i].seq == seq) {
            slot = i;
            break;
        }
    }
    if (slot < 0) {
        xSemaphoreGive(s_lock);
        ESP_LOGW(TAG, "record %lu was not open; nothing written",
                 (unsigned long)seq);
        return false;
    }

    crynet_log_event_t rec;
    memset(&rec, 0, sizeof(rec));
    rec.seq = seq;
    rec.boot_id = s_meta.boot_id;
    rec.uptime_ms = s_open[slot].start_uptime_ms;
    rec.epoch_s = s_open[slot].start_epoch_s;
    rec.duration_ms = duration_ms;
    rec.peak_rms_milli = peak_rms_milli;
    rec.mean_rms_milli = mean_rms_milli;
    rec.kind = s_open[slot].kind;
    rec.cot = s_open[slot].cot;
    rec.peak_conf = peak_conf;
    rec.windows = windows;
    rec.reserved = 0;

    const int64_t t0 = esp_timer_get_time();
    const bool ok = append_locked(&rec);
    const int64_t t1 = esp_timer_get_time();
    ESP_LOGI(TAG, "record %lu: %s in %lld ms",
             (unsigned long)seq, ok ? "written" : "NOT written",
             (long long)((t1 - t0) / 1000));
    memset(&s_open[slot], 0, sizeof(s_open[slot]));

    /* Remember the time for the next boot while we are here -- but
     * only when it has moved.  The clock is set once by SNTP and then
     * runs on its own, so a cry episode normally does not change it,
     * and every page of flash rewritten here is a page the radio path
     * has to wait for. */
    const uint64_t now_ms = crynet_clock_epoch_ms();
    if (now_ms != 0 &&
        (s_meta.last_epoch_ms == 0 ||
         now_ms > s_meta.last_epoch_ms + 60000u ||
         now_ms + 60000u < s_meta.last_epoch_ms)) {
        s_meta.last_epoch_ms = now_ms;
        save_meta_locked();
    }

    xSemaphoreGive(s_lock);
    return ok;
}

uint32_t crynet_log_write(uint8_t kind, uint8_t cot, uint32_t duration_ms,
                          uint8_t peak_conf, uint8_t windows,
                          uint16_t peak_rms_milli, uint16_t mean_rms_milli)
{
    const uint32_t seq = crynet_log_reserve(kind, cot);
    if (seq == 0) {
        return 0;
    }
    return crynet_log_commit(seq, duration_ms, peak_conf, windows,
                             peak_rms_milli, mean_rms_milli) ? seq : 0;
}

/* ---------------------------------------------------------------- */
/* Reading, for the uploader and the console.                        */

int crynet_log_pending(crynet_log_event_t *out, int max, uint32_t *last_seq)
{
    if (last_seq) {
        *last_seq = 0;
    }
    if (!s_ready || out == NULL || max <= 0) {
        return 0;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);

    const uint32_t n = count_locked();
    const uint32_t start = first_above_locked(s_meta.uploaded_seq);
    uint32_t take = (start < n) ? (n - start) : 0;
    if (take > (uint32_t)max) {
        take = (uint32_t)max;
    }
    for (uint32_t i = 0; i < take; i++) {
        if (!read_at_locked(start + i, &out[i])) {
            take = i;
            break;
        }
    }
    if (take && last_seq) {
        *last_seq = out[take - 1].seq;
    }

    xSemaphoreGive(s_lock);
    return (int)take;
}

bool crynet_log_mark_uploaded(uint32_t seq)
{
    if (!s_ready) {
        return false;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool ok = true;
    if (seq > s_meta.uploaded_seq) {
        s_meta.uploaded_seq = seq;
        ok = save_meta_locked();
    }
    xSemaphoreGive(s_lock);
    return ok;
}

int crynet_log_recent(crynet_log_event_t *out, int max)
{
    if (!s_ready || out == NULL || max <= 0) {
        return 0;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);

    const uint32_t n = count_locked();
    uint32_t take = (n < (uint32_t)max) ? n : (uint32_t)max;
    for (uint32_t i = 0; i < take; i++) {
        if (!read_at_locked(n - 1 - i, &out[i])) {
            take = i;
            break;
        }
    }

    xSemaphoreGive(s_lock);
    return (int)take;
}

uint32_t crynet_log_total(void)
{
    if (!s_ready) {
        return 0;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    const uint32_t n = count_locked();
    xSemaphoreGive(s_lock);
    return n;
}

uint32_t crynet_log_pending_count(void)
{
    if (!s_ready) {
        return 0;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    const uint32_t n = count_locked();
    const uint32_t start = first_above_locked(s_meta.uploaded_seq);
    xSemaphoreGive(s_lock);
    return (start < n) ? (n - start) : 0;
}

uint32_t crynet_log_dropped(void)
{
    return s_meta.dropped;
}

uint32_t crynet_log_boot_id(void)
{
    return s_meta.boot_id;
}

uint64_t crynet_log_last_epoch_ms(void)
{
    return s_meta.last_epoch_ms;
}

bool crynet_log_save_epoch_ms(uint64_t epoch_ms)
{
    if (!s_ready || epoch_ms == 0) {
        return false;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    /* Only worth a flash write when it has moved on a minute; the
     * uploader calls this every time it talks to the dashboard. */
    bool ok = true;
    if (epoch_ms > s_meta.last_epoch_ms + 60000u ||
        s_meta.last_epoch_ms == 0) {
        s_meta.last_epoch_ms = epoch_ms;
        ok = save_meta_locked();
    }
    xSemaphoreGive(s_lock);
    return ok;
}

/* ---------------------------------------------------------------- */
/* Keeping it to a rolling window.                                   */

void crynet_log_trim(void)
{
    if (!s_ready) {
        return;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);

    const uint32_t n = count_locked();
    const uint32_t start = first_above_locked(s_meta.uploaded_seq);
    const uint32_t pending = (start < n) ? (n - start) : 0;

    /* Keep everything still to send, plus a window of what has been
     * sent so the console's history still has something to show. */
    uint32_t target = pending;
    if (target < KEEP_AFTER_UPLOAD) {
        target = KEEP_AFTER_UPLOAD;
    }
    if (target > MAX_RECORDS) {
        target = MAX_RECORDS;   /* out of room: something has to go */
    }
    if (n <= target) {
        xSemaphoreGive(s_lock);
        return;
    }

    const uint32_t drop = n - target;
    const uint32_t sent = n - pending;
    if (drop > sent) {
        const uint32_t lost = drop - sent;
        s_meta.dropped += lost;
        ESP_LOGW(TAG, "the log is full and %lu unsent records are being "
                      "dropped; the hub has been offline too long",
                 (unsigned long)lost);
    }

    /* Copy the tail into a new file, then swap.  A power cut during
     * the copy leaves the original untouched. */
    crynet_log_event_t *buf = malloc(COPY_CHUNK * REC_SIZE);
    if (buf == NULL) {
        ESP_LOGE(TAG, "no memory to compact the log; leaving it as it is");
        xSemaphoreGive(s_lock);
        return;
    }

    const int tmp = open(EVENTS_TMP, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (tmp < 0) {
        ESP_LOGE(TAG, "cannot start the new log: %s", strerror(errno));
        free(buf);
        xSemaphoreGive(s_lock);
        return;
    }
    uint32_t head[4] = { EVENTS_MAGIC, FORMAT_VER, REC_SIZE, 0 };
    bool ok = write(tmp, head, HEADER_SIZE) == (ssize_t)HEADER_SIZE;

    for (uint32_t done = 0; ok && done < target; ) {
        uint32_t take = target - done;
        if (take > COPY_CHUNK) {
            take = COPY_CHUNK;
        }
        const off_t off = (off_t)(HEADER_SIZE + (drop + done) * REC_SIZE);
        if (pread(s_fd, buf, take * REC_SIZE, off) != (ssize_t)(take * REC_SIZE)) {
            ok = false;
            break;
        }
        if (write(tmp, buf, take * REC_SIZE) != (ssize_t)(take * REC_SIZE)) {
            ok = false;
            break;
        }
        done += take;
    }
    if (ok) {
        fsync(tmp);
    }
    close(tmp);
    free(buf);

    if (!ok) {
        ESP_LOGE(TAG, "compacting the log failed: %s; keeping the old one",
                 strerror(errno));
        unlink(EVENTS_TMP);
        xSemaphoreGive(s_lock);
        return;
    }

    close(s_fd);
    s_fd = -1;
    unlink(EVENTS_PATH);
    if (rename(EVENTS_TMP, EVENTS_PATH) != 0) {
        ESP_LOGE(TAG, "cannot put the compacted log in place: %s",
                 strerror(errno));
        open_events_locked();
        xSemaphoreGive(s_lock);
        return;
    }
    if (!open_events_locked()) {
        s_ready = false;
        xSemaphoreGive(s_lock);
        return;
    }

    /* Everything below the oldest kept record is gone; the sent pointer
     * must not point into thin air. */
    crynet_log_event_t oldest;
    if (read_at_locked(0, &oldest) && s_meta.uploaded_seq < oldest.seq) {
        s_meta.uploaded_seq = oldest.seq - 1;
    }
    save_meta_locked();

    ESP_LOGI(TAG, "log compacted: %lu dropped, %lu kept",
             (unsigned long)drop, (unsigned long)target);

    xSemaphoreGive(s_lock);
}

bool crynet_log_clear(void)
{
    if (!s_ready) {
        return false;
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);

    memset(s_open, 0, sizeof(s_open));
    const bool ok = open_events_locked() &&
                    ftruncate(s_fd, (off_t)HEADER_SIZE) == 0;
    if (ok) {
        fsync(s_fd);
        /* The numbers carry on: a new record must never reuse an old
         * one's number, or the dashboard would ignore it. */
        s_meta.uploaded_seq = s_meta.next_seq - 1;
        save_meta_locked();
        ESP_LOGI(TAG, "log cleared; numbering carries on at %lu",
                 (unsigned long)s_meta.next_seq);
    }

    xSemaphoreGive(s_lock);
    return ok;
}