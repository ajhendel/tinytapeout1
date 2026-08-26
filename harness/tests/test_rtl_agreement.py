"""The Python model and the Verilog must agree.

These are the tests that catch an encoder that is self-consistent and wrong. If
iverilog is not installed they skip rather than fail, so the pure-Python tests
still run anywhere.
"""

import os
import random
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from evofab.genome import Genome, Globals, Site, random_genome, apply_sabotage
from evofab.device import IcarusDevice, SimDevice, column_output

pytestmark = pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="iverilog not available")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def dev():
    return IcarusDevice(n_sites=8, target="AND", repo_root=ROOT)


def test_model_matches_rtl_on_random_genomes(dev):
    rng = random.Random(11)
    genomes = [random_genome(8, rng) for _ in range(64)]
    rtl = dev.evaluate_many(genomes)
    sim = SimDevice("AND", 8)
    model = [sim.evaluate(g) for g in genomes]
    bad = [(i, r.components["correct"], m.components["correct"])
           for i, (r, m) in enumerate(zip(rtl, model))
           if abs(r.components["correct"] - m.components["correct"]) > 1e-9]
    assert not bad, f"model and RTL disagree on {len(bad)} genomes: {bad[:5]}"


def test_model_matches_rtl_under_sabotage(dev):
    """Sabotage is where a decode mistake would hide, because a sabotaged site
    still produces a perfectly reasonable looking output."""
    rng = random.Random(12)
    genomes = []
    for mode in range(6):
        for _ in range(6):
            g = random_genome(8, rng)
            genomes.append(apply_sabotage(g, rng.randrange(8), mode))
    rtl = dev.evaluate_many(genomes)
    sim = SimDevice("AND", 8)
    model = [sim.evaluate(g) for g in genomes]
    bad = [i for i, (r, m) in enumerate(zip(rtl, model))
           if abs(r.components["correct"] - m.components["correct"]) > 1e-9]
    assert not bad, f"model and RTL disagree under sabotage on {len(bad)} genomes"


def test_calibration_rings_are_ordered_as_physics_requires(dev):
    """Faster drive gives more edges in a fixed window, and the loaded ring is
    slowest. This is the check that the drive variant reaches the ring."""
    counts = []
    rng = random.Random(13)
    for sel in range(4):
        g = random_genome(8, rng, Globals(calib_en=1, calib_sel=sel,
                                          window_exp=2, trans_exp=15))
        counts.append(int(dev.evaluate_many([g])[0].components["freq_byte"]))
    inv1, inv2, inv4, loaded = counts
    assert loaded < inv1 < inv2 < inv4, f"ring order wrong: {counts}"


def test_a_corrupt_frame_never_reaches_the_fabric(dev):
    """Sabotage the CRC and require the device to refuse the load."""
    import subprocess
    rng = random.Random(14)
    g = random_genome(8, rng)
    frames = os.path.join(dev.build_dir, "corrupt.txt")
    out = os.path.join(dev.build_dir, "corrupt_out.txt")
    with open(frames, "w") as f:
        f.write(f"{g.frame() ^ 0xFF:x}\n")   # invert the CRC byte
        f.write(f"{g.frame():x}\n")
    subprocess.run(["vvp", dev.vvp, f"+frames={frames}", f"+out={out}"],
                   capture_output=True, text=True, check=True)
    rows = [line.split() for line in open(out) if line.strip()]
    bad, good = rows[0], rows[1]
    assert bad[1] == "0", "CRC_OK was high for a corrupt frame"
    assert bad[2] == "1", "a corrupt frame left the fabric live"
    assert good[1] == "1" and good[2] == "0"
