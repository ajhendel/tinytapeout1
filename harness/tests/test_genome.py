"""Tests for the genome encoding, run with pytest from the repo root.

The point of these is agreement between three independent things: this module's
encoder, the Python reference model, and the actual Verilog. Two of them being
consistent proves nothing if they were derived from each other.
"""

import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evofab.genome import (Genome, Globals, Site, UnsafeGenome, crc8,
                           random_genome, apply_sabotage, OPERATORS,
                           GLOBAL_W, SITE_W, CRC_W)


def test_frame_width():
    g = random_genome(8, random.Random(0))
    assert g.payload_w == GLOBAL_W + SITE_W * 8
    assert g.chain_w == g.payload_w + CRC_W
    assert len(g.bits_msb_first()) == g.chain_w


def test_payload_roundtrip():
    rng = random.Random(1)
    for _ in range(200):
        g = random_genome(rng.choice([1, 4, 8, 16]), rng)
        assert Genome.from_payload(g.payload(), g.n_sites) == g


def test_site_zero_is_in_the_high_bits():
    """Chain order is [global][site 0]...[site N-1][crc].

    Getting this backwards reverses the genome and every per-site experiment
    addresses the wrong site, while everything still looks plausible. So it is
    asserted rather than commented.
    """
    sites = tuple(Site(func=i % 8) for i in range(4))
    g = Genome(globals=Globals(), sites=sites)
    p = g.payload()
    top_site = (p >> (SITE_W * 3)) & ((1 << SITE_W) - 1)
    assert Site.decode(top_site) == sites[0]


def test_crc_detects_a_one_bit_shift():
    """The failure the CRC exists for is a frame short or long by one bit."""
    g = random_genome(8, random.Random(2))
    p = g.payload()
    good = crc8(p, g.payload_w)
    shifted = (p << 1) & ((1 << g.payload_w) - 1)
    assert crc8(shifted, g.payload_w) != good


def test_crc_detects_every_single_bit_error():
    g = random_genome(8, random.Random(3))
    p = g.payload()
    good = crc8(p, g.payload_w)
    for bit in range(g.payload_w):
        assert crc8(p ^ (1 << bit), g.payload_w) != good


def test_config_hash_is_stable_and_discriminating():
    rng = random.Random(4)
    seen = {}
    for _ in range(500):
        g = random_genome(8, rng)
        h = g.config_hash()
        if h in seen:
            assert seen[h] == g.payload(), "hash collision on different payloads"
        seen[h] = g.payload()
        assert g.config_hash() == h


def test_validator_rejects_unbounded_feedback():
    g = Genome(globals=Globals(fb_en=1, window_exp=15, trans_exp=15),
               sites=(Site(),))
    with pytest.raises(UnsafeGenome):
        g.validate()


def test_validator_rejects_disabled_trip_limit_with_feedback():
    g = Genome(globals=Globals(fb_en=1, window_exp=4, trans_exp=15),
               sites=(Site(),))
    with pytest.raises(UnsafeGenome):
        g.validate()


def test_validator_accepts_bounded_feedback():
    Genome(globals=Globals(fb_en=1, window_exp=4, trans_exp=2),
           sites=(Site(route=2),)).validate()


def test_validator_rejects_ring_during_a_fabric_measurement():
    g = Genome(globals=Globals(calib_en=1, cnt_src=1), sites=(Site(),))
    with pytest.raises(UnsafeGenome):
        g.validate()


def test_operators_change_exactly_one_site():
    rng = random.Random(5)
    base = random_genome(8, rng)
    for name, op in OPERATORS.items():
        for _ in range(50):
            child = op(base, rng)
            diff = [i for i in range(8) if child.sites[i] != base.sites[i]]
            assert len(diff) <= 1, f"{name} touched {len(diff)} sites"


def test_drive_and_load_operators_move_one_step():
    """A redraw from x1 to x8 is a large electrical change and makes the
    operator's effect size uninformative about the gradient."""
    rng = random.Random(6)
    base = random_genome(8, rng)
    for name in ("drive", "load"):
        for _ in range(200):
            child = OPERATORS[name](base, rng)
            for a, b in zip(base.sites, child.sites):
                assert abs(getattr(a, name) - getattr(b, name)) <= 1


def test_search_never_inserts_sabotage():
    """Sabotage is an experimental treatment, not a move the search may make.
    A search free to insert faults would learn to hide behind them."""
    rng = random.Random(7)
    g = random_genome(8, rng)
    for _ in range(500):
        g = OPERATORS[rng.choice(list(OPERATORS))](g, rng)
        assert all(s.sab == 0 for s in g.sites)
    assert apply_sabotage(g, 3, 2).sites[3].sab == 2
