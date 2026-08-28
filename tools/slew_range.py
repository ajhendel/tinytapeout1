#!/usr/bin/env python3
"""Is any measured node driven outside the library's characterization range?

WHY THIS MATTERS MORE HERE THAN IN AN ORDINARY DESIGN

A Liberty cell model is a table, and a table has edges. sky130_fd_sc_hd is
characterized to an input transition of 1.5 ns; past that the delay a static
timing tool reports is an EXTRAPOLATION off the end of the table rather than an
interpolation inside it.

For most designs that is a timing risk and nothing more. For this one it is a
claim risk. The whole point of the chip is to compare three model layers against
silicon, and a node whose Liberty number came from outside the table has not
been predicted by the Liberty layer at all. Reporting a "model to silicon gap"
there would be reporting the size of an extrapolation.

So the question is asked per node, per corner, and only about the nodes whose
delays are quoted: the converter, the characterization paths, the calibration
strip and the fabric sites. Control and reset distribution is reported and not
gated, because nothing is quoted against it.

WHAT WAS FOUND BY ASKING

docs/AREA_GATE.md carried this table typed by hand from an older build, and it
had gone stale in three separate ways. It said the worst structure was
calibration ring 5 at 1.320 ns; on the 2026-08-28 build ring 5 is at 1.008 and
the worst is the characterization merge node at 1.318. It said the TDC reported
nothing, which is still true and is the only row that survived. And it said the
pins past 1.5 ns were all on the rst_n chain; they are now all on a fabric
site's `live` control chain. A table that is typed goes stale silently, so this
one is generated.

LibreLane's own MAX_TRANSITION_CONSTRAINT is 0.75, half the library value. That
is a house rule and violating it is not a physical fact, so it is not what is
gated here. The 1.5 ns library value is.

USAGE

    tools/slew_range.py <artifacts dir or checks.rpt> [--limit 1.5] [--markdown]
"""

import argparse
import glob
import os
import re
import sys

# Prefix to group. Order matters, first match wins.
GROUPS = [
    ("u_tdc", "TDC"),
    ("u_char", "characterization paths"),
    ("u_calib", "calibration strip"),
    ("sites[", "fabric sites"),
]
# Everything a delay is quoted against. `other` is reported and not gated.
MEASURED = {name for _, name in GROUPS}

VIOL = re.compile(r"^(\S+)\s+([\d.]+)\s+([\d.]+)\s+(-[\d.]+)\s+\(VIOLATED\)")


def parse(path):
    """{pin: slew ns} from the max slew violator section of one checks.rpt."""
    out, inside = {}, False
    for line in open(path, errors="replace"):
        s = line.strip()
        if s.startswith("max slew"):
            inside = True
            continue
        if inside and (s.startswith("max fanout")
                       or s.startswith("max capacitance")):
            break
        if not inside:
            continue
        m = VIOL.match(s)
        if m:
            out[m.group(1)] = float(m.group(3))
    return out


def group_of(pin):
    for prefix, name in GROUPS:
        if pin.startswith(prefix):
            return name
    return "control and reset"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="artifacts directory, or one checks.rpt")
    ap.add_argument("--limit", type=float, default=1.5,
                    help="the library's characterized max_transition, in ns")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    if os.path.isdir(args.path):
        rpts = sorted(glob.glob(os.path.join(args.path, "**", "checks.rpt"),
                                recursive=True))
        rpts = [p for p in rpts if "stapostpnr" in p] or rpts
    else:
        rpts = [args.path]
    if not rpts:
        print("no checks.rpt found; the slew question was not asked and a "
              "check that cannot find its input has to fail", file=sys.stderr)
        return 1

    rows, over = [], []
    for rpt in rpts:
        corner = os.path.basename(os.path.dirname(rpt))
        viols = parse(rpt)
        worst = {}
        for pin, slew in viols.items():
            g = group_of(pin)
            if slew > worst.get(g, (0.0, ""))[0]:
                worst[g] = (slew, pin)
            if slew > args.limit and g in MEASURED:
                over.append((corner, g, pin, slew))
        for g in [n for _, n in GROUPS] + ["control and reset"]:
            slew, pin = worst.get(g, (0.0, "none reported"))
            rows.append((corner, g, slew, pin))

    if args.markdown:
        print("| corner | group | worst slew | pin | of the limit |")
        print("|---|---|---|---|---|")
        for corner, g, slew, pin in rows:
            frac = f"{slew / args.limit * 100:.0f} %" if slew else ""
            print(f"| {corner} | {g} | "
                  f"{(f'{slew:.3f} ns' if slew else 'none reported')} | "
                  f"`{pin}` | {frac} |")
        print()
    else:
        for corner, g, slew, pin in rows:
            if slew:
                print(f"{corner:<18} {g:<24} {slew:.3f} ns  "
                      f"({slew / args.limit * 100:3.0f} percent of "
                      f"{args.limit} ns)  {pin}")
            else:
                print(f"{corner:<18} {g:<24} none reported")

    worst_measured = max((r for r in rows if r[1] in MEASURED),
                         key=lambda r: r[2], default=None)
    if worst_measured:
        print()
        print(f"worst measured node   {worst_measured[2]:.3f} ns at "
              f"{worst_measured[0]}, {worst_measured[3]}")
        print(f"                      "
              f"{worst_measured[2] / args.limit * 100:.0f} percent of the "
              f"{args.limit} ns library limit")

    if over:
        print()
        for corner, g, pin, slew in over:
            print(f"FAIL: {pin} ({g}) slews {slew:.3f} ns at {corner}, past "
                  f"the {args.limit} ns the library is characterized to. Its "
                  f"Liberty delay is an extrapolation off the end of the "
                  f"table, so the Liberty layer has not predicted this node "
                  f"and no model to silicon gap can be quoted at it.",
                  file=sys.stderr)
        return 1
    print("PASS: every node a delay is quoted against is inside the "
          "characterized range.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
