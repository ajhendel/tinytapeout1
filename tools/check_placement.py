#!/usr/bin/env python3
"""Report where the flow actually put the things whose position is the result.

WHY THIS EXISTS

src/calib_macro.v carries three byte-for-byte identical ring oscillators, ro0,
ro_twin_a and ro_twin_b. Nothing distinguishes them electrically. The only thing
that can make their frequencies differ on a die is WHERE THEY ARE, so their
difference is a spatial measurement and nothing else.

The problem is that we cannot ask for a position. Tiny Tapeout's LibreLane
configuration exposes no standard-cell placement regions, so "near the fabric"
and "far from it" are not properties this design can assert. Asserting them
anyway, and then reporting a spatial result, would be reporting an experiment
that may never have happened: if the placer clustered all three rings in the
same corner, their difference measures nothing and the numbers would still look
like data.

So the separation is MEASURED, from the placed DEF, and every spatial statement
is quoted against what this prints. If the achieved separation is small, the
honest conclusion is that this die could not run the experiment, not that the
experiment found no effect.

The same reasoning covers the fabric column and the TDC delay line. The delay
line's stage delays depend on how it was placed and routed, and a line scattered
across the die has a very different bin profile from a compact one. That is
recoverable by on-die calibration either way, but it is worth knowing which one
we got.

Usage:
    tools/check_placement.py <placed.def> [--json out.json]

The DEF comes from the LibreLane run in Tiny Tapeout's CI, typically
runs/<tag>/**/*.def with the largest one being the routed design. This script
never runs a flow and never needs a PDK.
"""

import argparse
import json
import math
import os
import re
import sys

# Groups whose placement is a result rather than an implementation detail. The
# key is the report label; the value is a regular expression matched against the
# DEF instance name.
GROUPS = {
    "calib ro0 (reference twin)":   r"u_calib\.ro0\b|u_calib/ro0[./]",
    "calib ro_twin_a":              r"u_calib\.ro_twin_a|u_calib/ro_twin_a",
    "calib ro_twin_b":              r"u_calib\.ro_twin_b|u_calib/ro_twin_b",
    "calib ro5 (drive replica)":    r"u_calib\.ro5\b|u_calib/ro5[./]",
    "TDC delay line":               r"u_tdc\.dl|u_tdc/dl",
    "TDC sampling tree":            r"u_tdc\.samp|u_tdc/samp",
    "characterization paths":       r"u_char\.",
    "fabric column":                r"\bsites\[|\bsites_",
}

# The three identical rings. Their pairwise separation is the whole spatial
# experiment, so it is reported on its own.
TWINS = ["calib ro0 (reference twin)", "calib ro_twin_a", "calib ro_twin_b"]

COMP = re.compile(r"^\s*-\s+(\S+)")
PLACED = re.compile(r"\+\s*(?:FIXED|PLACED)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)")


def parse_def(path):
    """Return {instance_name: (x_um, y_um)} for every placed component."""
    units = 1000.0
    insts = {}
    in_comps = False
    pending = None
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("UNITS DISTANCE MICRONS"):
                # The line ends "... 1000 ;" and the semicolon is sometimes its
                # own token and sometimes glued on, so take the last token that
                # actually parses as a number rather than the last token.
                for tok in reversed(line.replace(";", " ").split()):
                    try:
                        units = float(tok)
                        break
                    except ValueError:
                        continue
                continue
            if line.startswith("COMPONENTS"):
                in_comps = True
                continue
            if line.startswith("END COMPONENTS"):
                break
            if not in_comps:
                continue
            m = COMP.match(line)
            if m:
                pending = m.group(1)
            if pending:
                p = PLACED.search(line)
                if p:
                    insts[pending] = (int(p.group(1)) / units,
                                      int(p.group(2)) / units)
                    pending = None if line.rstrip().endswith(";") else pending
            if line.rstrip().endswith(";"):
                pending = None
    return insts


def stats(points):
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    spread = max(math.dist(p, (cx, cy)) for p in points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return {
        "cells": n,
        "centroid_um": [round(cx, 2), round(cy, 2)],
        "radius_um": round(spread, 2),
        "bbox_um": [round(min(xs), 2), round(min(ys), 2),
                    round(max(xs), 2), round(max(ys), 2)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deffile")
    ap.add_argument("--json", help="also write the report as JSON")
    args = ap.parse_args()

    if not os.path.exists(args.deffile):
        print(f"no DEF at {args.deffile}", file=sys.stderr)
        return 2

    insts = parse_def(args.deffile)
    print(f"placed components in {os.path.basename(args.deffile)}: {len(insts)}")
    if not insts:
        print("no placed components parsed; the DEF is not a placed one",
              file=sys.stderr)
        return 2

    report = {"def": os.path.basename(args.deffile), "groups": {}}
    xs = [p[0] for p in insts.values()]
    ys = [p[1] for p in insts.values()]
    die = (max(xs) - min(xs), max(ys) - min(ys))
    report["die_extent_um"] = [round(die[0], 2), round(die[1], 2)]
    diag = math.hypot(*die)
    print(f"placed extent: {die[0]:.1f} x {die[1]:.1f} um, "
          f"diagonal {diag:.1f} um\n")

    print(f"{'group':<32}{'cells':>7}{'centroid (um)':>22}{'radius':>9}")
    for label, pat in GROUPS.items():
        rx = re.compile(pat)
        pts = [xy for name, xy in insts.items() if rx.search(name)]
        if not pts:
            print(f"{label:<32}{'-':>7}{'not found':>22}")
            report["groups"][label] = None
            continue
        st = stats(pts)
        report["groups"][label] = st
        c = st["centroid_um"]
        print(f"{label:<32}{st['cells']:>7}"
              f"{f'({c[0]:.1f}, {c[1]:.1f})':>22}{st['radius_um']:>9.1f}")

    # ------------------------------------------------- the spatial experiment
    print("\nthe three identical rings, pairwise separation")
    have = [t for t in TWINS if report["groups"].get(t)]
    if len(have) < 2:
        print("  could not locate them in this DEF; no spatial statement is "
              "available from this build")
        report["twin_separation_um"] = None
    else:
        seps = {}
        for i, a in enumerate(have):
            for b in have[i + 1:]:
                d = math.dist(report["groups"][a]["centroid_um"],
                              report["groups"][b]["centroid_um"])
                seps[f"{a} <-> {b}"] = round(d, 2)
                print(f"  {a} <-> {b}: {d:.1f} um")
        report["twin_separation_um"] = seps
        worst = max(seps.values())
        frac = worst / diag if diag else 0.0
        print(f"\n  largest separation is {worst:.1f} um, "
              f"{frac * 100:.0f} percent of the placed diagonal")
        # A judgement, printed rather than enforced. This is a report, not a
        # gate: a clustered placement is a fact about the build that has to be
        # written down, not a reason to fail it.
        if frac < 0.25:
            print("  VERDICT: the three identical rings are CLUSTERED. This "
                  "build cannot support a spatial claim. Their spread is still "
                  "a valid within-die variation floor.")
        else:
            print("  VERDICT: the rings are separated. Their difference is "
                  "quotable as a placement effect, against the spread of the "
                  "closest pair as the noise floor.")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
