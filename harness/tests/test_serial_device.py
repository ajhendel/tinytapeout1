"""SerialDevice against a loopback stub that behaves like the firmware will.

The transport is injected, so the protocol can be exercised end to end without
hardware. That is the only way it can be right before the hardware exists, and
it means the day a board arrives the unknown is the board and not the framing.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evofab import link
from evofab.device import SerialDevice
from evofab.genome import Genome, random_genome


class StubFirmware:
    """A minimal, deliberately literal model of what the firmware must do.

    It scores on its own side of the link, which is the property the whole
    architecture exists to enforce, and it never sees a host round trip per
    input vector because there is no message that would carry one.
    """

    def __init__(self, n_sites=8, version=b"stub-1.0\x00", drop_first=False,
                 short_batch=False, corrupt=False):
        self.n_sites = n_sites
        self.version = version
        self.out = bytearray()
        self.buf = bytearray()
        self.trial = 0
        self.drop_first = drop_first
        self.short_batch = short_batch
        self.corrupt = corrupt
        self.seen_batches = 0
        self.seen_bit_counts = []

    # transport surface used by SerialDevice
    def write(self, data: bytes) -> None:
        self.buf.extend(data)
        for msg_type, payload in link.decode_stream(self.buf):
            self._handle(msg_type, payload)

    def read(self, n: int) -> bytes:
        chunk = bytes(self.out[:n])
        del self.out[:n]
        return chunk

    def _emit(self, msg_type: int, payload: bytes) -> None:
        raw = bytearray(link.encode(msg_type, payload))
        if self.corrupt:
            raw[7] ^= 0xFF
            self.corrupt = False
        if self.drop_first:
            self.drop_first = False
            return
        self.out.extend(raw)

    def _handle(self, msg_type: int, payload: bytes) -> None:
        if msg_type == link.HELLO:
            self._emit(link.HELLO_ACK, self.version)
        elif msg_type == link.RUN_BATCH:
            frames = link.decode_run_batch(payload)
            self.seen_batches += 1
            self.seen_bit_counts.append([len(f) for f in frames])
            recs = []
            for f in frames:
                self.trial += 1
                # Score on this side. The number is arbitrary but it is a
                # function of the frame, so a rotated or truncated frame gives a
                # different answer and the test can tell.
                num = sum(f) * 7 % 1000
                recs.append(link.ResultRecord(
                    trial_index=self.trial, fitness_num=num,
                    freq_count=100 + len(f), trans_count=3,
                    temp_proxy=1234, flags=link.FLAG_CRC_OK))
            if self.short_batch:
                recs = recs[:-1]
                self.short_batch = False
            self._emit(link.BATCH_RESULT, link.encode_batch_result(recs))


def test_hello_gives_the_firmware_version():
    dev = SerialDevice(StubFirmware(), n_sites=8)
    assert dev.firmware_version == "stub-1.0"


def test_a_batch_goes_down_and_scores_come_back():
    stub = StubFirmware()
    dev = SerialDevice(stub, n_sites=8)
    rng = random.Random(0)
    genomes = [random_genome(8, rng) for _ in range(24)]
    trials = dev.evaluate_many(genomes)
    assert len(trials) == 24
    assert stub.seen_batches == 1, "a generation must be one request, not 24"
    assert all(t.crc_ok for t in trials)
    assert all(t.temperature_proxy == 1234 for t in trials), \
        "the PVT covariate must arrive per trial"


def test_the_wire_carries_the_exact_chain_width():
    """A scan chain is not a whole number of bytes. If the width were implied
    rather than sent, the firmware would shift the wrong number of bits and
    every genome would be rotated."""
    stub = StubFirmware()
    dev = SerialDevice(stub, n_sites=8)
    g = random_genome(8, random.Random(1))
    dev.evaluate(g)
    assert stub.seen_bit_counts[-1] == [g.chain_w]


def test_a_short_batch_is_refused_rather_than_accepted():
    """A partial batch that looks complete is how a search scores genomes it
    never ran."""
    stub = StubFirmware(short_batch=True)
    dev = SerialDevice(stub, n_sites=8)
    rng = random.Random(2)
    with pytest.raises(Exception):
        dev.evaluate_many([random_genome(8, rng) for _ in range(4)])


def test_a_corrupt_reply_times_out_rather_than_being_accepted():
    """Corrupt the BATCH_RESULT, not the handshake, so the device is already up
    and the failure under test is the one we mean."""
    stub = StubFirmware()
    dev = SerialDevice(stub, n_sites=8, timeout_s=0.05)
    stub.corrupt = True
    with pytest.raises(TimeoutError):
        dev.evaluate(random_genome(8, random.Random(3)))


def test_a_dropped_reply_times_out():
    stub = StubFirmware()
    dev = SerialDevice(stub, n_sites=8, timeout_s=0.05)
    stub.drop_first = True
    with pytest.raises(TimeoutError):
        dev.evaluate(random_genome(8, random.Random(4)))


def test_site_count_mismatch_is_refused():
    dev = SerialDevice(StubFirmware(), n_sites=8)
    with pytest.raises(ValueError):
        dev.evaluate(random_genome(16, random.Random(5)))
