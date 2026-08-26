"""Link framing tests, including the resynchronisation and corruption paths.

A framing layer that is only tested on clean input is not tested. These
deliberately feed it garbage, truncation, and bit flips, because the reason the
framing exists at all is that the wire will do exactly that.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evofab.genome import random_genome
from evofab.link import (SYNC, RUN_BATCH, BATCH_RESULT, ResultRecord, FrameError,
                         crc16_ccitt_false, decode_batch_result, decode_run_batch,
                         decode_stream, encode, encode_batch_result,
                         encode_run_batch)


def test_crc16_matches_the_named_variant():
    """CRC-16/CCITT-FALSE has a published check value for "123456789"."""
    assert crc16_ccitt_false(b"123456789") == 0x29B1


def test_roundtrip_one_frame():
    raw = encode(RUN_BATCH, b"hello")
    got = decode_stream(bytearray(raw))
    assert got == [(RUN_BATCH, b"hello")]


def test_leading_garbage_is_skipped():
    buf = bytearray(b"\x00\x11\x22garbage" + encode(RUN_BATCH, b"x"))
    assert decode_stream(buf) == [(RUN_BATCH, b"x")]


def test_truncated_frame_waits_for_the_rest():
    raw = encode(RUN_BATCH, b"abcdefgh")
    buf = bytearray(raw[:-3])
    assert decode_stream(buf) == []
    buf.extend(raw[-3:])
    assert decode_stream(buf) == [(RUN_BATCH, b"abcdefgh")]


def test_a_corrupt_frame_is_dropped_not_delivered():
    raw = bytearray(encode(RUN_BATCH, b"payload"))
    raw[8] ^= 0xFF
    good = encode(RUN_BATCH, b"second")
    got = decode_stream(bytearray(bytes(raw) + good))
    assert got == [(RUN_BATCH, b"second")], "a corrupt frame was delivered"


def test_a_truncated_frame_blocks_only_until_its_claimed_length_passes():
    """The device is reset halfway through sending a frame.

    The decoder cannot tell a truncated frame from an incomplete one, so it
    waits, which is correct and is bounded by the claimed length. It recovers as
    soon as enough further bytes arrive to test and reject the stale header, and
    then every following good frame is recovered, not just the last one. This
    matters because the alternative implementation, trusting the bad header's
    length and skipping it, silently eats the frame that follows.
    """
    stale = encode(BATCH_RESULT, b"\x00" * 40)[:20]   # claims 50 bytes, has 20
    good = encode(BATCH_RESULT, encode_batch_result([]))

    buf = bytearray(stale + good)
    assert decode_stream(buf) == [], "must wait rather than mis-frame"

    # More traffic arrives, enough to exceed the stale header's claim.
    buf.extend(good * 4)
    got = decode_stream(buf)
    assert got == [(BATCH_RESULT, encode_batch_result([]))] * 5, (
        f"resync lost frames: recovered {len(got)} of 5")


def test_resync_when_the_stale_header_is_immediately_testable():
    """Same situation but the stale frame claims a short length, so it can be
    tested and rejected at once and the good frame comes straight through."""
    stale = bytearray(encode(BATCH_RESULT, b"\x00" * 4))
    stale[-1] ^= 0xFF                                  # break its CRC
    good = encode(BATCH_RESULT, encode_batch_result([]))
    got = decode_stream(bytearray(bytes(stale) + good))
    assert got == [(BATCH_RESULT, encode_batch_result([]))]


def test_scan_frames_survive_a_non_byte_aligned_bit_count():
    """A scan chain is not a whole number of bytes. Padding and letting the
    firmware guess is how a genome gets rotated, so the bit count is explicit."""
    rng = random.Random(0)
    # Chain width is 24 + 12N, so it is byte aligned for some site counts and
    # not for others. Both are covered here deliberately, because a padding bug
    # only shows up on the unaligned ones.
    widths = {}
    for n_sites in (1, 2, 3, 4, 8, 16, 48, 64):
        g = random_genome(n_sites, rng)
        bits = g.bits_msb_first()
        widths[n_sites] = len(bits) % 8
        back = decode_run_batch(encode_run_batch([bits]))
        assert back == [bits], f"{n_sites} sites, {len(bits)} bits, rotated"
    assert 0 in widths.values() and any(v for v in widths.values()), \
        f"this test must cover both aligned and unaligned widths, got {widths}"


def test_batch_of_many_scan_frames():
    rng = random.Random(1)
    frames = [random_genome(8, rng).bits_msb_first() for _ in range(24)]
    assert decode_run_batch(encode_run_batch(frames)) == frames


def test_result_records_roundtrip():
    recs = [ResultRecord(i, -3 + i, 1234 + i, 7 * i, 555 + i, i & 0x0F)
            for i in range(24)]
    assert decode_batch_result(encode_batch_result(recs)) == recs


def test_a_partial_batch_is_refused_rather_than_truncated():
    recs = [ResultRecord(1, 2, 3, 4, 5, 1), ResultRecord(2, 3, 4, 5, 6, 1)]
    payload = encode_batch_result(recs)[:-4]
    with pytest.raises(FrameError):
        decode_batch_result(payload)


def test_fuzz_never_delivers_a_frame_that_was_not_sent():
    """Random noise must never decode into a frame. The 16 bit CRC over a random
    body should reject essentially always; this asserts it empirically because
    the alternative failure is silent."""
    rng = random.Random(2)
    sent = encode(RUN_BATCH, b"real")
    delivered = 0
    for _ in range(400):
        noise = bytes(rng.randrange(256) for _ in range(200))
        for (t, p) in decode_stream(bytearray(noise)):
            delivered += 1
    assert delivered == 0, f"{delivered} frames conjured out of noise"
    assert decode_stream(bytearray(sent)) == [(RUN_BATCH, b"real")]
