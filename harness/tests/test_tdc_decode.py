"""The TDC decoder, against captures made up on purpose.

WHY THIS FILE EXISTS

The decoder is part of the instrument. It is the half that turns a tap register
and a Gray coded counter into a number, and if it is wrong the chip is wrong in
a way no amount of silicon fixes. It also cannot be developed after the dies
arrive, because by then there is nothing to compare its output against: every
reading it produces will look plausible, and the two failures that matter
(a saturated coarse count, a capture taken while the counter was carrying) look
exactly like ordinary fast readings.

So the captures here are synthesised, from a model of the ring rather than from
the RTL, and the decoder has to agree with the model. The model is written out
in ring_capture() below and is the specification: a ring of 32 bins of arbitrary
width, an edge walking it, the taps below the edge holding the new value, and a
counter ticking once per two traversals.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evofab.genome import (TDC_GRAY_SATURATED, TDC_TAPS, TdcStatus, bin_to_gray,
                           gray_to_bin, tdc_bubbles, tdc_decode, tdc_reading,
                           tdc_runs)

N = TDC_TAPS


def ring_capture(traversal, pos):
    """The raw (taps, gray) a ring produces with the edge at `pos` in `traversal`.

    The ring parks with every tap high. Traversal 0 walks a 1 to 0 transition
    down the line, traversal 1 walks a 0 to 1 back down it, and so on, so the
    taps BELOW the edge carry the new value and which value that is alternates.
    The coarse counter is clocked by the last tap and therefore ticks once per
    two traversals.
    """
    assert 0 <= pos <= N
    if traversal % 2 == 0:                       # new value is 0
        taps = ((1 << N) - 1) ^ ((1 << pos) - 1)
    else:                                        # new value is 1
        taps = (1 << pos) - 1
    return taps, bin_to_gray(traversal // 2)


def test_gray_round_trips_over_the_whole_counter():
    assert all(gray_to_bin(bin_to_gray(i)) == i for i in range(256))
    # Adjacent counts differ in exactly one bit. That property is the entire
    # reason the coarse count is coded at all: it is what confines an
    # asynchronous capture taken mid carry to the two counts either side.
    for i in range(255):
        d = bin_to_gray(i) ^ bin_to_gray(i + 1)
        assert bin(d).count("1") == 1, f"{i} to {i+1} is not a single bit"
    assert gray_to_bin(TDC_GRAY_SATURATED) == 0xFF


def test_ideal_codes_decode_to_their_own_bin_index():
    """Every interior position of every traversal, back to where it came from.

    The two positions either side of the coarse counter's own clock edge are
    excluded and have their own test; a capture there is ambiguous by a whole
    ring period and the decoder refuses it rather than picking.
    """
    for traversal in range(6):
        for pos in range(2, N - 1):
            taps, gray = ring_capture(traversal, pos)
            r = tdc_reading(taps, gray)
            assert r.status == TdcStatus.VALID, (traversal, pos, r.status)
            assert r.delay_taps == traversal * N + pos
            assert tdc_decode(taps, gray) == traversal * N + pos


def test_a_population_count_is_the_wrong_decode():
    """The mistake this decoder was built to stop making.

    On odd traversals the ones count RISES with the delay and on even ones it
    FALLS, so a decoder that counts ones reports a longer path as a smaller
    number half the time. It reads as a perfectly ordered series, backwards,
    which is how the real one was found.
    """
    ones = [bin(ring_capture(t, 10)[0]).count("1") for t in (0, 1)]
    assert ones[0] != ones[1]
    decoded = [tdc_reading(*ring_capture(t, 10)).delay_taps for t in (0, 1)]
    assert decoded[1] > decoded[0]


def test_the_saturated_coarse_count_is_not_a_measurement():
    taps, _ = ring_capture(4, 12)
    r = tdc_reading(taps, TDC_GRAY_SATURATED)
    assert r.status == TdcStatus.COARSE_SATURATED
    assert r.delay_taps is None, (
        "a saturated count returned a number; a wrapped counter is "
        "indistinguishable from a fast path and this is how a slow circuit "
        "gets published as a fast one")


def test_a_trial_with_no_arrival_is_not_a_measurement():
    """The stale read. The tap register holds the PREVIOUS capture, so a trial
    that saw nothing decodes to a perfectly plausible number for a measurement
    that did not happen."""
    taps, gray = ring_capture(2, 9)
    assert tdc_reading(taps, gray, done=True).status == TdcStatus.VALID
    r = tdc_reading(taps, gray, done=False)
    assert r.status == TdcStatus.NO_ARRIVAL and r.delay_taps is None


@pytest.mark.parametrize("coarse", [1, 2, 5])
def test_the_carry_boundary_is_flagged_and_both_candidates_offered(coarse):
    """A capture at the counter's own clock edge is ambiguous by a whole period.

    The counter is clocked by the last tap, so it ticks at the END of every odd
    traversal. The two captures that can straddle that tick are the last bins of
    an odd traversal and the first bins of the even one after it, and nowhere
    else in the period.

    The Gray coding confines the ambiguity to ADJACENT counts, which is what
    makes it detectable at all, but adjacent counts are one ring period apart in
    time. Two candidates 2*N taps apart must never be averaged, and the decoder
    says so by refusing to pick one.
    """
    cases = [
        (2 * coarse + 1, N - 1),      # last bin before the tick
        (2 * coarse + 1, N),          # the tick itself, the all ones code
        (2 * coarse + 2, 0),          # the same instant, seen as the next
        (2 * coarse + 2, 1),          # first bin after the tick
    ]
    for traversal, pos in cases:
        taps, gray = ring_capture(traversal, pos)
        r = tdc_reading(taps, gray)
        assert r.status == TdcStatus.BOUNDARY_AMBIGUOUS, (traversal, pos, r)
        assert r.delay_taps is None
        assert len(r.candidates) == 2
        assert r.candidates[1] - r.candidates[0] == 2 * N, (
            "the two candidates must differ by exactly one ring period; any "
            "other spacing means the decoder is offering the wrong alternative")


def test_the_interior_of_a_traversal_is_never_flagged():
    """The guard band has to be a band, not the whole period. If everything were
    ambiguous the chip could not measure anything."""
    flagged = sum(1 for t in range(4) for pos in range(N + 1)
                  if tdc_reading(*ring_capture(t, pos)).status
                  == TdcStatus.BOUNDARY_AMBIGUOUS)
    total = 4 * (N + 1)
    assert flagged / total < 0.12, (
        f"{flagged} of {total} positions were refused as boundary captures")


def test_the_all_ones_field_is_the_boundary_and_not_a_zero_delay():
    """Every tap high means either the ring is still parked or a rising
    traversal has just finished. Those are one period apart and the fine code
    cannot separate them, so this must not silently decode as a fast path."""
    r = tdc_reading((1 << N) - 1, bin_to_gray(3))
    assert r.status == TdcStatus.BOUNDARY_AMBIGUOUS
    assert r.candidates == (3 * 2 * N, 4 * 2 * N)


def test_the_all_zero_field_is_the_end_of_a_falling_traversal():
    r = tdc_reading(0, bin_to_gray(1))
    assert r.status == TdcStatus.VALID
    assert r.delay_taps == 2 * 1 * N + N


def test_bubbles_move_the_reading_by_at_most_the_bubble_depth():
    """Bubbles are the calibration, not an error, so they must not be rejected.

    A bubble is a tap that sampled the wrong side of the edge because its bin is
    narrow or its branch of the sampling tree is slightly late. The decoder
    counts ones, so a bubble shifts the answer by exactly the number of
    misplaced bits and nothing worse. That is the property that makes code
    density calibration work.
    """
    taps, gray = ring_capture(1, 12)
    # Not the bits either side of the edge: flipping those just MOVES the
    # boundary and produces a clean code for a neighbouring position, which is
    # not a bubble at all. A bubble is a tap on the wrong side of an intact
    # boundary.
    for flip in (9, 14):
        dirty = taps ^ (1 << flip)
        r = tdc_reading(dirty, gray)
        assert r.status == TdcStatus.VALID
        assert abs(r.delay_taps - (1 * N + 12)) <= 1
        assert tdc_bubbles(dirty) >= 1


def test_a_scattered_field_is_not_a_delay_line_reading():
    """Bubbles are LOCAL. A code with runs all the way down the line is a
    sampling fault, and reporting it as a delay would put a number on a
    converter that was not converting."""
    assert tdc_runs(0xAAAAAAAA) == N
    r = tdc_reading(0xAAAAAAAA, bin_to_gray(1))
    assert r.status == TdcStatus.THERMOMETER_INVALID
    assert r.delay_taps is None


def test_a_missing_sampling_branch_is_not_always_visible_in_the_code():
    """Stated as a test because it is a limitation, not a feature.

    The sampling tree has four branches of eight flip flops. If one branch never
    fires, its eight taps read zero, and for many positions the surviving
    pattern is a perfectly well formed code for a DIFFERENT position. The
    decoder cannot see that and does not pretend to.

    What catches it is hardware: src/tdc.v ANDs the four branch fired flags, so
    a partial capture reports done=0 and never reaches this decoder. This test
    exists so that anyone who removes that AND finds out here why it was there.
    """
    taps, gray = ring_capture(0, 6)                 # bits 6..31 high
    truth = tdc_reading(taps, gray).delay_taps
    broken = taps & ~(0xFF << 24)                   # branch 3 never fired
    r = tdc_reading(broken, gray)
    assert r.status == TdcStatus.VALID, (
        "if this now reports an invalid code, the decoder got better and this "
        "test should be tightened rather than deleted")
    assert r.delay_taps != truth, (
        "a lost branch changed nothing, which would mean the taps it holds are "
        "not being read")


def test_random_bin_widths_still_decode_to_a_monotone_series():
    """The whole point of a code density calibration, exercised end to end.

    The bins of a real delay line are not equal, and nothing in this design
    assumes they are. What the decoder must guarantee is that the BIN INDEX it
    returns rises monotonically with the true arrival time, because that index
    is what the calibration table is indexed by. If the index were not monotone
    the table could not exist.
    """
    rng = random.Random(20260828)
    widths = [rng.uniform(0.5, 1.8) for _ in range(N)]
    edges = []
    acc = 0.0
    for w in widths:
        acc += w
        edges.append(acc)
    traversal_time = acc

    def capture_at(t):
        traversal = int(t // traversal_time)
        within = t - traversal * traversal_time
        pos = sum(1 for e in edges if e <= within)
        return ring_capture(traversal, pos)

    times = sorted(rng.uniform(0, 6 * traversal_time) for _ in range(400))
    last = -1
    for t in times:
        r = tdc_reading(*capture_at(t))
        if r.status != TdcStatus.VALID:
            continue          # boundary captures are refused, not misdecoded
        assert r.delay_taps >= last, (
            f"the decoded bin index went backwards at t={t:.3f}")
        last = r.delay_taps
    assert last > 5 * N, "the sweep never reached the later traversals"
