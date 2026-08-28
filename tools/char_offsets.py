#!/usr/bin/env python3
"""What does each characterization path pay before and after its own chain?

WHY THIS EXISTS

src/char_paths.v launches all twenty fixed paths from one hand-built tree, one
root buffer into five branch buffers into four launch gates each, and merges
them back through a one-hot tri-state onto a single node. The comment says the
tree is balanced so that every path is the same number of gates from the launch
register, and it is. Being the same number of GATES is not being the same
DELAY: the wires are the placer's decision and this design has already been
taught twice what the placer does with a tree nobody measured.

tools/tdc_range.py charges every path ONE fixed overhead, taken from path 0's
branch. That is the right thing to print and the wrong thing to fit against.

WHY THE DEPTH SERIES IS THE PLACE IT HURTS

The depth series is paths 8, 9, 10, 11 and 19, at depths 2, 4, 8, 16 and 32, and
its slope is the per-stage delay that every other number on this chip is quoted
against. The four short points are all on launch branch 2. The 32 stage point,
which carries most of the lever arm, is on branch 4. So a per-branch delay
difference lands almost entirely on the longest arm, which is the worst place
for it to land, and it moves the SLOPE rather than the intercept.

Measured on the build of 2026-08-28, all nine corners: the per-path offset
spreads 102 to 251 ps, and the slope bias it injects is +0.81 to +2.12 ps per
stage against a slope of about 41.5, so two to five percent. The residual it
injects is 0.07 to 0.12 taps, so linearity survives and only the unit moves.

Two to five percent on the unit is not nothing for a chip whose whole claim is
the size of model to silicon gaps, since several of the effects being hunted are
themselves ten to twenty five percent.

WHAT IS DONE ABOUT IT

Not a redesign. The offsets are a fixed property of the build, they are in the
extraction, and they are subtracted before the fit, exactly the way
tools/stop_tree.py's per-tap selector offsets are subtracted before the per-site
fit. What is claimed is therefore "equal logical launch and merge depth with an
extracted per-path offset correction", and not "a balanced tree".

This tool measures them, writes them out for the correction, and gates two
things. The residual after correction must stay small, because a large one means
the offsets are not a constant plus noise and subtracting them is not modelling
anything. And the raw slope bias must stay inside --max-bias, because a
correction worth more than a tenth of the quantity it corrects is doing too much
of the work.

USAGE

    tools/char_offsets.py <sdf> [--max-bias 0.10] [--max-residual 0.25]
                                [--json out.json] [--markdown]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdf_graph import load  # noqa: E402
import tdc_range as tr      # noqa: E402

# Paths 8, 9, 10, 11 and 19 at these depths. Kept here rather than imported so
# that a change in one place shows up as a disagreement rather than as silent
# agreement with itself, the same reason CHAR_PATHS is duplicated in
# tools/tdc_range.py. harness/tests/test_char_paths_match_rtl.py checks both
# copies against the Verilog.
DEPTH_SERIES = [(8, 2), (9, 4), (10, 8), (11, 16), (19, 32)]

LAUNCH_ROOT = "u_char.lrt"
MERGE_OUT = "u_char.merge_out"


def _one(g, needle, suffix):
    hits = [p for p in g.pins(needle) if p.endswith(suffix)]
    return hits[0] if hits else None


def offsets(g, npaths=20):
    """{path index: launch ns, merge ns} plus an error string."""
    root = _one(g, LAUNCH_ROOT, "/X")
    if root is None:
        return None, ("no launch tree root in the SDF; every path's launch time "
                      "is unmeasurable and the depth series has no unit")
    mo_y = _one(g, MERGE_OUT, "/Y")
    mo_a = _one(g, MERGE_OUT, "/A")
    if mo_y is None or mo_a is None:
        return None, "no merge output cell in the SDF"

    reach = g.slowest(root, lambda p: "u_char.gate[" in p and p.endswith("/X"))
    out, missing = {}, []
    for k in range(npaths):
        gx = f"u_char.gate[{k}].u.u/X"
        if gx not in reach:
            missing.append(k)
            continue
        launch = reach[gx][0]
        # DERIVED FROM THE /Z PIN, not searched for independently. The einvn
        # wrapper contains an enable inverter that also has an /A pin, and
        # picking whichever the parser happened to yield first would silently
        # measure the enable path instead of the data path.
        zz = _one(g, f"u_char.merge[{k}].", "/Z")
        za = (zz.rsplit("/", 1)[0] + "/A") if zz else None
        merge = 0.0
        for a, b in ((za, zz), (zz, mo_a), (mo_a, mo_y)):
            e = g.edges.get(a, {}).get(b) if a and b else None
            if e:
                merge += e[1]
        out[k] = (launch, merge)
    if missing:
        return None, (f"paths {missing} are not reachable from the launch tree "
                      f"root; a path the launch edge cannot reach cannot be "
                      f"measured and its absence would shorten this table "
                      f"rather than fail it")
    return out, None


def fit(pts):
    n = len(pts)
    xb = sum(x for x, _ in pts) / n
    yb = sum(y for _, y in pts) / n
    sxx = sum((x - xb) ** 2 for x, _ in pts)
    m = sum((x - xb) * (y - yb) for x, y in pts) / sxx
    b = yb - m * xb
    return m, b, max(abs(y - (m * x + b)) for x, y in pts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sdf")
    ap.add_argument("--max-bias", type=float, default=0.10,
                    help="largest slope bias allowed, as a fraction of the slope")
    ap.add_argument("--max-residual", type=float, default=0.25,
                    help="largest residual the offsets may inject, in taps")
    ap.add_argument("--json")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.sdf):
        print(f"no SDF at {args.sdf}", file=sys.stderr)
        return 2
    g = load(args.sdf)
    if not g.edges:
        print("no timing edges parsed; that is not an SDF", file=sys.stderr)
        return 2

    corner = os.path.basename(os.path.dirname(args.sdf)) or "unknown"
    print(f"corner                {corner}")

    off, err = offsets(g)
    if err:
        print(f"FAIL: {err}.", file=sys.stderr)
        return 1

    by = tr.load_sdf(args.sdf)
    tap = sum(v for k, v in by.items() if k.startswith("u_tdc.dl")) / 32
    if tap <= 0:
        print("FAIL: no delay line in the SDF, so there is no tap to quote "
              "these against.", file=sys.stderr)
        return 1

    tot = {k: a + b for k, (a, b) in off.items()}
    spread = max(tot.values()) - min(tot.values())

    # The chains themselves, so the bias can be quoted against a real slope
    # rather than against a number typed into this file.
    chain = {k: tr.series(by, f"u_char.p{k}.") for k, _ in DEPTH_SERIES}
    raw = [(d, chain[k] + tot[k]) for k, d in DEPTH_SERIES]
    cor = [(d, chain[k]) for k, d in DEPTH_SERIES]
    m_raw, b_raw, r_raw = fit(raw)
    m_cor, b_cor, r_cor = fit(cor)
    bias = m_raw - m_cor

    # What the offsets alone inject, as their own line. This is the part that
    # says whether they are a constant plus noise, which is what makes
    # subtracting them a correction rather than a fudge.
    o_only = [(d, tot[k]) for k, d in DEPTH_SERIES]
    m_o, b_o, r_o = fit(o_only)

    print(f"tap                   {tap*1000:.1f} ps")
    print(f"per-path offset       {min(tot.values())*1000:.1f} to "
          f"{max(tot.values())*1000:.1f} ps, spread {spread*1000:.1f} ps")
    print(f"depth series slope    {m_cor*1000:.2f} ps/stage corrected, "
          f"{m_raw*1000:.2f} raw")
    print(f"slope bias            {bias*1000:+.3f} ps/stage "
          f"({bias/m_cor*100:+.1f} percent of the corrected slope)")
    print(f"fit residual          {r_cor*1000:.1f} ps corrected "
          f"({r_cor/tap:.2f} taps), {r_raw*1000:.1f} ps raw "
          f"({r_raw/tap:.2f} taps)")
    print(f"offsets alone         residual {r_o*1000:.1f} ps "
          f"({r_o/tap:.2f} taps) about their own line")

    if args.markdown:
        print()
        print("| path | branch | launch ps | merge ps | total ps | in taps |")
        print("|---|---|---|---|---|---|")
        for k in sorted(off):
            a, b = off[k]
            print(f"| {k} | {k // 4} | {a*1000:.1f} | {b*1000:.1f} | "
                  f"{tot[k]*1000:.1f} | {tot[k]/tap:.2f} |")
        print()

    if args.json:
        json.dump({"corner": corner, "tap_ns": tap,
                   "offsets_ns": {str(k): {"launch": off[k][0],
                                           "merge": off[k][1]}
                                  for k in sorted(off)},
                   "depth_series": {"slope_corrected_ns": m_cor,
                                    "slope_raw_ns": m_raw,
                                    "intercept_corrected_ns": b_cor,
                                    "bias_ns": bias,
                                    "residual_corrected_ns": r_cor,
                                    "residual_raw_ns": r_raw}},
                  open(args.json, "w"), indent=2)
        print(f"wrote {args.json}")

    ok = True
    if abs(bias) > args.max_bias * abs(m_cor):
        print(f"FAIL: the launch and merge offsets bias the depth series slope "
              f"by {bias/m_cor*100:+.1f} percent, over the "
              f"{args.max_bias*100:.0f} percent limit. That slope is the unit "
              f"every delay on this chip is quoted in, and a correction worth "
              f"more than a tenth of the quantity it corrects is doing too "
              f"much of the work to be called a correction.", file=sys.stderr)
        ok = False
    if r_o / tap > args.max_residual:
        print(f"FAIL: the offsets scatter {r_o/tap:.2f} taps about their own "
              f"straight line, over the {args.max_residual:.2f} limit. They "
              f"are then not a per-path constant plus small noise, and "
              f"subtracting them models nothing.", file=sys.stderr)
        ok = False
    if not ok:
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
