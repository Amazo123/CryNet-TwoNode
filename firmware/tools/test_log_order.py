"""The cry log's ordering, proved on the host.

The hub numbers a record when the episode *starts* and writes it when
the episode *ends*.  Two cots crying at once can end in the opposite
order to the one they started in -- cot 1's long cry holds its number
while cot 2's short one finishes first -- so the file of records is
**not** in number order.

The old code found the records still to send with a binary search over
the file, which is only valid if the file is sorted.  It was not, and
the binary search answered wrongly in exactly the case that matters:
asked for the first record above a number, it could land *past* a
record whose number was lower.  That record was then never sent, and
the hub said it had sent everything.  The dashboard simply never showed
that cry.

The log now walks the file in order instead, and the number it claims
as sent stops below two things: the lowest number that did not fit in
the batch, and the lowest number an episode still holds while it is
being measured.

This file models that algorithm exactly and proves the property that
matters:

    every record that was written is eventually sent.

It is a model, not the firmware: the real proof is the hub's own
`logtest` command, which runs the same scenario against the real
component on the real chip (see crynet_log.c).  This one runs
anywhere, with no hardware, and it also demonstrates the bug it
guards, so the old behaviour cannot be reintroduced by accident.

    python firmware/tools/test_log_order.py
"""

from __future__ import annotations

import random
import sys


class Log:
    """The cry log's bookkeeping, as the firmware keeps it."""

    def __init__(self) -> None:
        # The file: records in the order they were written.
        self.file: list[int] = []
        self.next_seq = 1
        self.uploaded_seq = 0
        # Episodes that have started and not yet ended: their numbers.
        self.open: list[int] = []

    # ---- writing -------------------------------------------------------

    def reserve(self) -> int:
        seq = self.next_seq
        self.next_seq += 1
        self.open.append(seq)
        return seq

    def commit(self, seq: int) -> None:
        self.file.append(seq)
        self.open.remove(seq)

    # ---- the current algorithm ----------------------------------------

    def _collect(self, after: int, max_records: int) -> tuple[list[int], int, int]:
        """The records above `after`: the batch, the highest number in
        it, and the lowest number that did not fit.

        The batch is the *lowest* numbers, not the first ones in the
        file: the file is in the order the records were written, which
        is not the order they were numbered, and taking the first ones
        in the file could pick a high number while a lower one sits
        behind it -- and then that lower one would be sent over and
        over and the log would never move on.
        """
        qualifying = sorted(seq for seq in self.file if seq > after)
        batch = qualifying[:max_records]
        last_seq = batch[-1] if batch else 0
        stuck = qualifying[max_records] if len(qualifying) > max_records else 0
        return batch, last_seq, stuck

    def _watermark(self, last_seq: int, stuck: int) -> int:
        w = last_seq
        if stuck != 0 and (w == 0 or stuck - 1 < w):
            w = stuck - 1
        for seq in self.open:
            if seq - 1 < w:
                w = seq - 1
        if w < self.uploaded_seq:
            w = self.uploaded_seq
        return w

    def pending(self, max_records: int = 32) -> tuple[list[int], int]:
        batch, last_seq, stuck = self._collect(self.uploaded_seq, max_records)
        return batch, self._watermark(last_seq, stuck)

    def mark_uploaded(self, watermark: int) -> None:
        if watermark > self.uploaded_seq:
            self.uploaded_seq = watermark

    # ---- the old algorithm, kept so the bug stays visible --------------

    def _first_above_old(self, seq: int) -> int:
        """The old binary search.  Valid only on a sorted file."""
        lo, hi = 0, len(self.file)
        while lo < hi:
            mid = lo + (hi - lo) // 2
            if self.file[mid] > seq:
                hi = mid
            else:
                lo = mid + 1
        return lo

    def pending_old(self, max_records: int = 32) -> list[int]:
        start = self._first_above_old(self.uploaded_seq)
        return self.file[start:start + max_records]

    def mark_uploaded_old(self, last: int) -> None:
        if last > self.uploaded_seq:
            self.uploaded_seq = last


def drain(log: Log, batch: int = 32, sent: list[int] | None = None) -> list[int]:
    """Send everything, the way the uploader does, and return what went."""
    if sent is None:
        sent = []
    for _ in range(1000):
        records, watermark = log.pending(batch)
        if not records:
            break
        sent.extend(records)
        log.mark_uploaded(watermark)
    return sent


def drain_old(log: Log, batch: int = 32, sent: list[int] | None = None) -> list[int]:
    if sent is None:
        sent = []
    for _ in range(1000):
        records = log.pending_old(batch)
        if not records:
            break
        sent.extend(records)
        log.mark_uploaded_old(records[-1])
    return sent


# ---------------------------------------------------------------------
# The bug, and the case that caused it.
# ---------------------------------------------------------------------

def test_two_cots_out_of_order() -> None:
    """Cot 1's long cry starts first, cot 2's short one finishes first.

    The record of the short cry is written first and holds the higher
    number, so the file is out of order.  The uploader runs while the
    long cry is still going -- that is the ordinary case, the hub is on
    the network all night -- and both records must still be sent.
    """
    log = Log()
    long_cry = log.reserve()     # cot 1, starts first
    short_cry = log.reserve()    # cot 2, starts second
    log.commit(short_cry)        # ... but finishes first

    sent = drain(log)
    assert short_cry in sent, "the short cry was never sent"

    log.commit(long_cry)         # cot 1's cry ends later
    sent = drain(log)
    assert long_cry in sent, "the long cry was never sent"


def test_the_old_algorithm_loses_the_record() -> None:
    """The bug this guards, shown rather than described.

    The old code searched the file for the first record above the
    number it had sent.  With the file out of order it landed past a
    record that had never been sent, and that record was never sent at
    all.
    """
    log = Log()
    long_cry = log.reserve()
    short_cry = log.reserve()
    log.commit(short_cry)

    # The uploader runs while the long cry is still going.
    first = drain_old(log)
    assert short_cry in first, "the old code did not send the short cry"

    log.commit(long_cry)
    second = drain_old(log)

    assert long_cry not in first + second, (
        "the old code is expected to lose the long cry; if it does not, "
        "this test is no longer describing the bug it guards")


def test_a_batch_that_does_not_fit() -> None:
    """More records than one batch holds, with an episode still open."""
    log = Log()
    seqs = [log.reserve() for _ in range(40)]
    for seq in seqs:
        log.commit(seq)
    still_open = log.reserve()          # starts, does not finish yet

    sent = drain(log, batch=32)
    assert sorted(set(sent)) == sorted(seqs), "a record was lost"
    assert still_open not in sent

    # Now the open episode finishes and must be sent too.
    log.commit(still_open)
    sent = drain(log, batch=32)
    assert still_open in sent, "the episode that was still open was lost"


def test_an_episode_open_across_the_whole_upload() -> None:
    """The awkward case: one episode holds its number throughout."""
    log = Log()
    held = log.reserve()
    other = log.reserve()
    log.commit(other)

    sent = drain(log)
    assert other in sent, "the finished episode was not sent"
    assert held not in sent, "the open episode was sent before it finished"

    log.commit(held)
    sent = drain(log)
    assert held in sent, "the episode that finished late was never sent"


def test_soak() -> None:
    """Ten thousand random interleavings, every record sent.

    Episodes are reserved and committed in a random order, the uploader
    runs at random moments in between, in batches of a random size, and
    an episode is sometimes left open across the whole upload.
    """
    rng = random.Random(20261124)
    for _ in range(10000):
        log = Log()
        episodes = [log.reserve() for _ in range(rng.randint(1, 12))]
        rng.shuffle(episodes)
        batch = rng.choice([1, 2, 3, 8, 32])

        sent: list[int] = []
        written: list[int] = []
        for seq in episodes:
            log.commit(seq)
            written.append(seq)
            if rng.random() < 0.4:
                drain(log, batch=batch, sent=sent)
        drain(log, batch=batch, sent=sent)

        # Anything still open finishes now and must go out too.
        for seq in list(log.open):
            log.commit(seq)
            written.append(seq)
        drain(log, batch=batch, sent=sent)

        assert set(written) <= set(sent), (
            f"lost {sorted(set(written) - set(sent))} "
            f"(batch {batch}, order {episodes})")


def test_the_soak_catches_the_old_algorithm() -> None:
    """The soak is only worth running if it fails on the old code.

    It is run here against the old algorithm, and it is expected to
    lose records.  If it ever stops losing them, the soak has stopped
    testing what it was written to test.
    """
    rng = random.Random(20261124)
    lost_once = False
    for _ in range(2000):
        log = Log()
        episodes = [log.reserve() for _ in range(rng.randint(1, 12))]
        rng.shuffle(episodes)
        batch = rng.choice([1, 2, 3, 8, 32])

        sent: list[int] = []
        written: list[int] = []
        for seq in episodes:
            log.commit(seq)
            written.append(seq)
            if rng.random() < 0.4:
                drain_old(log, batch=batch, sent=sent)
        drain_old(log, batch=batch, sent=sent)
        for seq in list(log.open):
            log.commit(seq)
            written.append(seq)
        drain_old(log, batch=batch, sent=sent)

        if not set(written) <= set(sent):
            lost_once = True
            break

    assert lost_once, (
        "the old algorithm lost nothing in two thousand runs; the soak is "
        "no longer testing the thing it was written to test")


def main() -> int:
    tests = [
        test_two_cots_out_of_order,
        test_the_old_algorithm_loses_the_record,
        test_a_batch_that_does_not_fit,
        test_an_episode_open_across_the_whole_upload,
        test_soak,
        test_the_soak_catches_the_old_algorithm,
    ]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print()
    print("OK  every record the log writes is eventually sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
