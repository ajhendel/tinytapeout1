"""The characterization path table, checked against the Verilog that builds it.

WHY THIS FILE EXISTS

The depth series is the single most load bearing measurement on this chip. Every
other delay is quoted against the fixed offset that its straight-line fit
recovers, so if the fit is wrong, everything downstream of it is wrong by the
same factor and nothing looks unusual.

The list of depths lived in three places: the Verilog that instantiates the
chains, the harness that fits them, and the pre-registration generator that
predicts them. Two of the three said depth 24 for `load_0` and the RTL builds it
at 16. The RTL was right and had a comment saying so. Nothing failed: the
simulation did not care, the netlist check did not care, and the cocotb test
that touches this path uses the correct depth by coincidence of being written
separately.

Fitting delays measured at [2, 4, 8, 16, 16, 32] against x values of
[2, 4, 8, 16, 24, 32] drags the fitted slope to about 0.89 of the true one and
inflates the residual that the pre-registration predicts will stay under a tap,
so the generated file could have pre-registered a falsification of its own
linearity claim.

So the numbers are read out of the Verilog. Not compared against a second list
written by hand, which is what failed; parsed from the module instantiations
themselves, which are the thing that becomes silicon.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evofab.genome import CHAR_PATHS, DEPTH_REPEAT, DEPTH_SERIES

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "src", "char_paths.v")

# char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(0)) p4 (.in(g[4]), .out(o[4]));
INST = re.compile(r"^\s*(char_\w+)\s*#\(([^)]*(?:\([^)]*\)[^)]*)*)\)\s*"
                  r"p(\d+)\s*\(", re.M)
PARAM = re.compile(r"\.(\w+)\s*\(\s*([^)]*?)\s*\)")


def rtl_paths():
    """{path index: (module, {param: value})} straight out of src/char_paths.v."""
    out = {}
    text = open(SRC).read()
    for mod, params, idx in INST.findall(text):
        out[int(idx)] = (mod, {k: v for k, v in PARAM.findall(params)})
    return out


def test_every_named_path_is_instantiated():
    rtl = rtl_paths()
    missing = [i for i in range(len(CHAR_PATHS)) if i not in rtl]
    assert not missing, (
        f"CHAR_PATHS names {len(CHAR_PATHS)} paths and src/char_paths.v does "
        f"not instantiate p{missing}. A select code with no path behind it "
        f"drives a floating node on the merge.")
    assert max(rtl) == len(CHAR_PATHS) - 1, (
        f"src/char_paths.v instantiates up to p{max(rtl)} and CHAR_PATHS names "
        f"{len(CHAR_PATHS)}; the readout slot that reports the path count "
        f"would be wrong and every host would address the wrong path")


def test_the_depth_series_depths_are_the_ones_the_rtl_builds():
    """The one that was wrong. Parsed, not restated."""
    rtl = rtl_paths()
    for depth, name in DEPTH_SERIES:
        i = CHAR_PATHS.index(name)
        mod, params = rtl[i]
        assert mod == "char_inv_chain", (
            f"{name} is p{i} and the RTL builds it with {mod}, which does not "
            f"take a DEPTH; it cannot be a point on a depth series")
        got = int(params["DEPTH"])
        assert got == depth, (
            f"DEPTH_SERIES says {name} is depth {depth} and "
            f"src/char_paths.v:p{i} builds it at {got}. Fitting the series "
            f"against the wrong x value biases the per-stage slope, which is "
            f"the number every other measurement on this chip is quoted "
            f"against, and nothing else would fail")


def test_the_repeat_point_really_is_the_same_depth_twice():
    """DEPTH_REPEAT claims two names for one measurement. Check it is true.

    If they were different depths this would be an ordinary series point being
    used as a repeatability check, and any disagreement between them would be
    read as instrument noise when it was actually depth.
    """
    depth, a, b = DEPTH_REPEAT
    rtl = rtl_paths()
    pa, pb = rtl[CHAR_PATHS.index(a)], rtl[CHAR_PATHS.index(b)]
    assert int(pa[1]["DEPTH"]) == int(pb[1]["DEPTH"]) == depth, (
        f"{a} and {b} are supposed to be the same depth measured twice, and "
        f"the RTL builds them at {pa[1]['DEPTH']} and {pb[1]['DEPTH']}")
    assert pa[1].get("LOAD") == pb[1].get("LOAD"), (
        f"{a} and {b} differ in LOAD ({pa[1].get('LOAD')} vs "
        f"{pb[1].get('LOAD')}), so they are not the same measurement and "
        f"their difference is not a repeatability check")


def test_the_load_series_holds_the_driver_fixed():
    """The mistake that made the drive series unmeasurable, in the other family.

    A load series has to vary the LOAD while the driver stays put. If DRIVE ever
    varies across these four, the series measures driver and load together and
    reports the sum as a load effect.
    """
    from evofab.genome import LOAD_SERIES
    rtl = rtl_paths()
    drives = {rtl[CHAR_PATHS.index(n)][1]["DRIVE"] for n in LOAD_SERIES}
    loads = {rtl[CHAR_PATHS.index(n)][1]["LOAD"] for n in LOAD_SERIES}
    depths = {rtl[CHAR_PATHS.index(n)][1]["DEPTH"] for n in LOAD_SERIES}
    assert len(drives) == 1, f"the load series varies DRIVE too: {drives}"
    assert len(depths) == 1, f"the load series varies DEPTH too: {depths}"
    assert len(loads) == len(LOAD_SERIES), (
        f"the load series does not vary LOAD across all four: {loads}")


def test_the_drive_series_holds_the_load_fixed():
    """The same check on the family where this actually went wrong once.

    Extraction measured the old drive series at 76 ps of spread across an
    eightfold drive change, not monotonic, because every stage's driver AND its
    load scaled together. The structure changed; this asserts it stayed changed.
    """
    from evofab.genome import DRIVE_SERIES
    rtl = rtl_paths()
    mods = {rtl[CHAR_PATHS.index(n)][0] for n in DRIVE_SERIES}
    assert mods == {"char_drive_series"}, (
        f"the drive series is built from {mods}; char_inv_chain scales the "
        f"driver and its load together, which is what made the old series "
        f"unmeasurable")
    sinks = {rtl[CHAR_PATHS.index(n)][1]["SINKS"] for n in DRIVE_SERIES}
    stages = {rtl[CHAR_PATHS.index(n)][1]["STAGES"] for n in DRIVE_SERIES}
    drives = {rtl[CHAR_PATHS.index(n)][1]["DRIVE"] for n in DRIVE_SERIES}
    assert len(sinks) == 1 and len(stages) == 1, (
        f"the drive series varies its load: SINKS={sinks}, STAGES={stages}")
    assert len(drives) == len(DRIVE_SERIES), (
        f"the drive series does not vary DRIVE across all four: {drives}")


def test_the_matched_pairs_differ_in_exactly_one_parameter():
    from evofab.genome import MATCHED_PAIRS
    rtl = rtl_paths()
    for label, (a, b) in MATCHED_PAIRS.items():
        ma, pa = rtl[CHAR_PATHS.index(a)]
        mb, pb = rtl[CHAR_PATHS.index(b)]
        assert ma == mb, f"{label}: {a} is {ma} and {b} is {mb}"
        differ = {k for k in set(pa) | set(pb) if pa.get(k) != pb.get(k)}
        assert len(differ) == 1, (
            f"{label}: {a} and {b} differ in {sorted(differ)}. A matched pair "
            f"differing in two things measures their sum and attributes it to "
            f"whichever one the paper is about")
