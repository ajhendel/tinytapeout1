#!/usr/bin/env python3
"""Is the stop selector's delay correlated with the tap number?

WHAT THE FABRIC EXPERIMENT ACTUALLY PRODUCES

Not a delay. A SLOPE. The converter is pointed at site 0, then site 1, and so on
up the column, and the per-site cost is the gradient of that series. Everything
common to all the readings, the launch gate, the merge, the converter's own
input stage, cancels out of a gradient and does not need to be known.

What does NOT cancel is anything that varies WITH the tap index. The stop
selector is a tree of multiplexers, one input per site, and if its delay happens
to rise with the tap number then that rise is added to the gradient and is
reported as the cost of a site. It would be a completely stable, completely
reproducible, completely wrong number, and no amount of repetition on silicon
would reveal it, because it is not noise.

So the tree is built balanced by hand in src/project.v: three cells deep for
every input, padded to 32 so that no code selects a shallower branch. That
removes the part of the effect that comes from LOGIC DEPTH. It does not remove
the part that comes from ROUTING, because nothing in the design chooses where
the placer puts anything, and a claim that a balanced tree cancels is a claim
about wires that the design cannot make.

This tool measures what is left.

WHAT IS REPORTED, AND WHAT IS GATED

Reported, per tap: cell delay through the three levels, the incoming wire, rise
and fall separately. Then the mean, the spread, the LINEAR TREND with tap index,
and the largest residual about that trend.

Gated: the trend, because the trend is the part that lands in the gradient. A
spread with no trend is an offset per site and washes out of a fit; a trend is a
bias in the answer. The threshold is a quarter of one tap per site, which is the
point at which the selector would be worth a quarter of the converter's own
resolution over a single site step, and about five taps across the whole column.

USAGE

    tools/stop_tree.py <sdf> [--sites 20] [--limit 0.25] [--markdown]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdf_graph import load  # noqa: E402


def find_inst(g, needle):
    """The one instance whose name contains `needle`, or None."""
    hits = sorted({p.rsplit("/", 1)[0] for p in g.pins(needle)})
    return hits[0] if len(hits) == 1 else None


def leg(g, inst, in_pin, out_pin="X"):
    """(rise, fall) through one cell, and the SLOWEST route into it.

    The slowest route, not the only one. The first input of this tree is a
    fabric site's output, which is a one-hot tri-state node carrying four drive
    variants, so it has four drivers by construction and asking for exactly one
    returned nothing for nineteen of the twenty taps.
    """
    cell = g.edge(f"{inst}/{in_pin}", f"{inst}/{out_pin}")
    wire = g.in_worst(f"{inst}/{in_pin}")
    return cell, wire


def fit(xs, ys):
    """Least squares slope and intercept. Written out rather than imported;
    numpy is not a dependency of this repository and this is four lines."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    m = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0
    return m, my - m * mx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sdf")
    ap.add_argument("--sites", type=int, default=int(os.environ.get("N_SITES", 20)))
    ap.add_argument("--taps", type=int, default=32)
    ap.add_argument("--limit", type=float, default=0.25,
                    help="taps of slope bias per site that will be tolerated")
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

    # The converter's own resolution, so the answer can be quoted in taps.
    span = 0.0
    for a, outs in g.edges.items():
        if ".dl" not in a:
            continue
        for b, (_lo, hi) in outs.items():
            if b.rsplit("/", 1)[0] == a.rsplit("/", 1)[0]:
                span += hi
    tap = span / args.taps if span else 0.0

    print(f"corner                {corner}")
    print(f"tap delay             {tap:.4f} ns   (line span {span:.4f} ns)")

    rows = []
    missing = []
    for t in range(args.sites):
        k, m = divmod(t, 4)          # level 1: tapl1[k], input A{m}
        j, i = divmod(k, 4)          # level 2: tapl2[j], input A{i}
        l1 = find_inst(g, f"tapl1[{k}].")
        l2 = find_inst(g, f"tapl2[{j}].")
        l3 = find_inst(g, "tapl3.")
        if not (l1 and l2 and l3):
            missing.append(t)
            continue
        c1, w1 = leg(g, l1, f"A{m}")
        c2, w2 = leg(g, l2, f"A{i}")
        c3, w3 = leg(g, l3, f"A{j}")
        if None in (c1, c2, c3):
            missing.append(t)
            continue
        # THE WIRE IS THE MEASUREMENT. Equal logical depth already removes the
        # cell contribution's dependence on which input was selected; what is
        # left, and the only thing that can put a trend into the fitted slope,
        # is routing. Dropping a missing wire silently would collapse the trend
        # toward zero and pass the gate for the wrong reason, so a tap whose
        # wires cannot all be found is a failure and not a row.
        wires = [w1, w2, w3]
        if any(w is None for w in wires):
            missing.append(t)
            continue
        rise = c1[0] + c2[0] + c3[0] + sum(w[0] for w in wires)
        fall = c1[1] + c2[1] + c3[1] + sum(w[1] for w in wires)
        rows.append((t, rise, fall, sum(w[0] for w in wires), len(wires)))

    if missing or not rows:
        print(f"FAIL: the stop selector tree could not be measured for taps "
              f"{missing or 'any'}. Either the keep/dont_touch multiplexers in "
              f"src/project.v were flattened, or an input's incoming route "
              f"could not be resolved to a single driver. Routing is the whole "
              f"non-cancelling part of this measurement; a tap missing its "
              f"wire term would drag the trend toward zero and pass.",
              file=sys.stderr)
        return 1

    print(f"taps found            {len(rows)} of {args.sites}")
    print()
    print("  tap   rise (ns)   fall (ns)   wire (ns)  wires")
    for t, rise, fall, wire, nw in rows:
        print(f"  {t:>3}   {rise:9.4f}   {fall:9.4f}   {wire:9.4f}  {nw:>5}")

    worst = [max(r, f) for _, r, f, _, _ in rows]
    xs = [t for t, *_ in rows]
    mean = sum(worst) / len(worst)
    var = sum((v - mean) ** 2 for v in worst) / len(worst)
    sd = var ** 0.5
    slope, intercept = fit(xs, worst)
    resid = max(abs(v - (slope * x + intercept)) for x, v in zip(xs, worst))
    rise_fall = max(abs(r - f) for _, r, f, _, _ in rows)

    slope_taps = slope / tap if tap else float("inf")
    total = slope * (len(rows) - 1)

    print()
    print(f"mean offset           {mean:.4f} ns   ({mean/tap:.2f} taps)"
          if tap else f"mean offset           {mean:.4f} ns")
    print(f"spread, sd            {sd:.4f} ns   ({sd/tap:.2f} taps)")
    print(f"rise vs fall, worst   {rise_fall:.4f} ns   ({rise_fall/tap:.2f} taps)")
    print(f"TREND with tap index  {slope:+.5f} ns/site   "
          f"({slope_taps:+.3f} taps/site)")
    print(f"max residual          {resid:.4f} ns   ({resid/tap:.2f} taps)")
    print(f"across the column     {total:+.4f} ns   ({total/tap:+.2f} taps "
          f"over {len(rows)-1} steps)")

    if args.markdown:
        print()
        print("| corner | mean | sd | rise vs fall | trend | trend, taps/site | max residual |")
        print("|---|---|---|---|---|---|---|")
        print(f"| {corner} | {mean:.4f} ns | {sd:.4f} ns | {rise_fall:.4f} ns | "
              f"{slope:+.5f} ns/site | {slope_taps:+.3f} | {resid:.4f} ns |")

    if abs(slope_taps) > args.limit:
        print(f"\nFAIL: the selector's delay trends {slope_taps:+.3f} taps per "
              f"site, against a limit of {args.limit}. That trend is added to "
              f"the fitted per-site slope and is indistinguishable from it. "
              f"Either the tree has to be placed differently or the per-site "
              f"result has to be corrected by this measured offset and say so.",
              file=sys.stderr)
        return 1
    print(f"\nPASS: the selector contributes {slope_taps:+.3f} taps per site to "
          f"the fitted slope, inside the {args.limit} tap limit. It is still an "
          f"offset per tap and the per-code numbers above are the correction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
