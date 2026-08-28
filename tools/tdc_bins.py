#!/usr/bin/env python3
"""Is the converter's transfer function monotone, and are its bins uniform?

WHY THIS EXISTS, AND WHAT IT CAUGHT

A tapped delay line converter is usually described as if a tap's threshold were
the delay down the line to that tap. It is not. The tap fires when the launched
edge has passed it AT THE MOMENT THE SAMPLING EDGE ARRIVES, so the quantity that
orders the taps is

    T_i = (line delay to stage i) - (sampling tree delay to stage i's flop)

Both terms are in the extracted timing of every build. Neither was being looked
at. The first term was checked by tools/tdc_range.py and the second by
tools/tdc_race.py, and the DIFFERENCE, which is the thing the instrument
actually measures with, was checked by nothing.

On the build of 2026-08-28 the sampling tree's root had twelve sinks against a
max fanout of ten, so the resizer inserted one repeater in front of two of the
four branches and left the other two direct. Taps 0 to 15 were therefore sampled
0.52 ns later than taps 16 to 31 at the typical corner. The line delays were
fine. The race margin was fine. The bin between tap 15 and tap 16 was 5.08
nominal taps wide at all nine corners, which is fifteen percent of the range
sitting in a single undivided bin, and the pre-registered repeat counts, which
are computed from ONE tap of quantization variance, would have been understated
by a factor of twenty five for any path that landed in it.

It was still monotone, and that was luck. The repeater landed on the low half.
Had it landed on the high half the same 0.52 ns would have run the thresholds
BACKWARDS across four bins and the thermometer code would not have been one.

MONOTONICITY IS A HARD FAIL. Everything downstream of the converter, in the
decoder and in the calibration, assumes the code is a thermometer code: that the
set of taps reading one is a prefix. A non-monotone T means two different
arrival times produce the same code and some codes are unreachable, and no
amount of per-bin calibration recovers what the chip did not encode.

WIDTH IS A FAIL ABOVE --max-bin NOMINAL TAPS. Some spread is unavoidable, since
the placer chooses the wires. The number is set at 2.0 because the repeat counts
in predictions/ are computed from the quantization variance of one bin, that
variance goes as the square of the width, and a factor of four in repeats is
inside the trial budget while a factor of twenty five is not.

USAGE

    tools/tdc_bins.py <sdf> [--taps 32] [--max-bin 2.0] [--markdown]

Exits nonzero on a non-monotone code, on a bin wider than the limit, or if the
delay line is not connected stage to stage in the SDF. A tool that cannot find
the chain it measures has to fail rather than report a short one.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdf_graph import load       # noqa: E402
from tdc_race import sampled_by  # noqa: E402

STAGE = re.compile(r"^(u_tdc\.dl\[(\d+)\]\..*)/([A-Z]+)$")


def stage_pins(g, taps):
    """{i: (input pin, output pin)} for the delay line, from the SDF names."""
    ins, outs = {}, {}
    for p in set(list(g.edges) + list(g.ins)):
        m = STAGE.match(p)
        if not m:
            continue
        i, pin = int(m.group(2)), m.group(3)
        if pin == "A":
            ins[i] = p
        elif pin in ("X", "Y", "Z"):
            outs[i] = p
    missing = [i for i in range(taps) if i not in ins or i not in outs]
    if missing:
        return None, (f"delay line stages {missing} have no pins in the SDF; "
                      f"the line is not {taps} stages long in this build")
    return {i: (ins[i], outs[i]) for i in range(taps)}, None


def thresholds(g, taps):
    """(line, tree, thr, error) for the delay line, all in ns, per tap.

    Shared with tools/tdc_range.py, which sizes its repeat counts from the
    WIDEST bin rather than the mean tap. Two implementations of the same walk
    would eventually disagree and the one that disagreed quietly would be the
    one feeding the pre-registration.
    """
    sp, err = stage_pins(g, taps)
    if err:
        return None, None, None, err
    root = [p for p in g.pins("samp_rt") if p.endswith("/X")]
    if not root:
        return None, None, None, ("no samp_rt output in the SDF; the sampling "
                                  "tree root is gone and with it the second "
                                  "half of every threshold")
    close = [p for p in g.pins("ring_close") if p.endswith("/Y")]
    if not close:
        return None, None, None, "no ring_close output in the SDF"
    reach = g.slowest(root[0], lambda p: p.endswith("/CLK"))

    acc, line, gaps = 0.0, {}, []
    prev_out = close[0]
    for i in range(taps):
        a, x = sp[i]
        for src, dst in ((prev_out, a), (a, x)):
            e = g.edges.get(src, {}).get(dst)
            if e is None:
                gaps.append(f"{src} -> {dst}")
            else:
                acc += e[1]
        line[i] = acc
        prev_out = x
    if gaps:
        return None, None, None, (
            f"{len(gaps)} missing timing edge(s) in the delay line, first "
            f"{gaps[0]}. The chain is not connected in this SDF and a broken "
            f"chain reports narrower bins than the real one")

    tree, orphan = {}, []
    for i in range(taps):
        ds = sampled_by(g, sp[i][1], reach)
        clks = [d.rsplit("/", 1)[0] + "/CLK" for d in ds]
        have = [reach[c][0] for c in clks if c in reach]
        if not have:
            orphan.append(i)
        else:
            tree[i] = min(have)
    if orphan:
        return None, None, None, (
            f"taps {orphan} have no sampling flip flop reachable from the "
            f"sampling root. A tap that is not sampled is not a tap")

    return line, tree, [line[i] - tree[i] for i in range(taps)], None


def widest_bin(g, taps):
    """(widest bin ns, nominal tap ns), or (None, None) if not measurable."""
    line, _tree, thr, err = thresholds(g, taps)
    if err:
        return None, None
    bins = [thr[i + 1] - thr[i] for i in range(taps - 1)]
    return max(bins), (line[taps - 1] - line[0]) / (taps - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sdf")
    ap.add_argument("--taps", type=int, default=32)
    ap.add_argument("--max-bin", type=float, default=2.0,
                    help="widest bin allowed, in nominal taps")
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

    line, tree, thr, err = thresholds(g, args.taps)
    if err:
        print(f"FAIL: {err}.", file=sys.stderr)
        return 1

    nominal = (line[args.taps - 1] - line[0]) / (args.taps - 1)
    bins = [thr[i + 1] - thr[i] for i in range(args.taps - 1)]
    back = [i for i, w in enumerate(bins) if w <= 0.0]
    widest = max(range(len(bins)), key=lambda i: bins[i])

    print(f"nominal tap           {nominal * 1000:.1f} ps")
    print(f"threshold span        {thr[-1] - thr[0]:.4f} ns "
          f"over {args.taps} taps")
    print(f"bin width             min {min(bins) * 1000:.1f} ps  "
          f"max {max(bins) * 1000:.1f} ps  "
          f"({max(bins) / nominal:.2f} nominal taps, at tap "
          f"{widest} to {widest + 1})")
    print(f"sampling tree spread  "
          f"{(max(tree.values()) - min(tree.values())) * 1000:.1f} ps "
          f"({(max(tree.values()) - min(tree.values())) / nominal:.2f} taps)")

    if args.markdown:
        print()
        print("| tap | line ns | tree ns | threshold ns | bin taps |")
        print("|---|---|---|---|---|")
        for i in range(args.taps):
            w = f"{bins[i] / nominal:.2f}" if i < len(bins) else ""
            print(f"| {i} | {line[i]:.4f} | {tree[i]:.4f} | {thr[i]:.4f} "
                  f"| {w} |")
        print()

    if back:
        print(f"FAIL: the code is NOT a thermometer code. Bins {back} run "
              f"backwards, so tap i+1 crosses its threshold BEFORE tap i and "
              f"the set of taps reading one is not a prefix. The decoder, the "
              f"code density calibration and the coarse/fine boundary rule all "
              f"assume it is.", file=sys.stderr)
        return 1
    if max(bins) > args.max_bin * nominal:
        print(f"FAIL: bin {widest} is {max(bins) / nominal:.2f} nominal taps "
              f"wide, over the {args.max_bin:.2f} limit. Quantization variance "
              f"goes as the square of the bin, so the repeat counts in "
              f"predictions/ are understated by "
              f"{(max(bins) / nominal) ** 2:.0f}x for any arrival landing "
              f"there, and code density calibration has that much less to "
              f"work with.", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
