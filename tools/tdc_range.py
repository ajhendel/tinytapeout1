#!/usr/bin/env python3
"""Does the TDC have usable range for every path we intend to measure?

WHY THIS EXISTS

The first version of this design shipped a 32 stage linear delay line and a
config bit that pointed it at the fabric column, and nobody bounded the two
against each other. From the post place-and-route SDF of that build: the line
spanned 3.835 ns at the typical corner and ONE fabric site's series path was
3.515 ns, 92 percent of it. The whole 24 site column was about 84 ns, 22 times
the span. Every fabric configuration would have returned all ones and every
slow configuration would have looked identical to every other one.

That is a question answerable from extraction, before fabrication, and it was
not asked. So it is asked here, automatically, from the same artifact the build
already produces.

The ring in src/tdc.v removes saturation as a failure mode. This tool still
matters for two reasons. A REFERENCE path must sit inside one ring period, so
that nothing the other measurements are quoted against depends on the coarse
counter. And the fixed launch and merge overhead is charged to every single
reading, so it is worth watching rather than discovering.

USAGE

    tools/tdc_range.py <sdf> [--taps 32] [--markdown]

The SDF comes from the LibreLane run in Tiny Tapeout's CI, at
runs/<tag>/*-openroad-stapostpnr/<corner>/*.sdf. Run it for at least the
typical and the slow corner; the slow one is where the ratio is worst for the
paths and best for the line, and they do not move together.
"""

import argparse
import collections
import os
import re
import sys

# The characterization paths, in select order, matching src/char_paths.v and
# CHAR_PATHS in harness/evofab/genome.py. Kept as a list here rather than
# imported so that a rename in one place shows up as a mismatch rather than
# silently agreeing with itself.
CHAR_PATHS = [
    "inv1_d8", "inv2_d8", "inv4_d8", "inv8_d8",
    "inv1_d8_loaded", "inv2_d8_loaded", "inv4_d8_loaded", "inv8_d8_loaded",
    "inv1_d2", "inv1_d4", "inv1_d16", "inv1_d32",
    "nand1_d8", "nand4_d8", "mux4_d4",
    "drive_isolated_d4", "drive_shared_d4",
    "ladder_off_d8", "ladder_on_d8", "spare_d8",
]

# The series chain inside one fabric site, in order. Load-ladder and monitor
# cells hang off the path rather than sitting in it, so they are excluded.
SITE_CHAIN = ["route_mux", "fmux_hi", "fmux", "sab_lo_mux", "sab_mux",
              "u_inert_gate", "u_drive.g_iso.i0", "u_drive.drv"]

CELL = re.compile(r'\(CELL\s*\(CELLTYPE\s*"([^"]+)"\)\s*\(INSTANCE\s*([^)]*)\)(.*?)\n\s*\)\n',
                  re.S)
TRIPLE = re.compile(r'\(([-\d.]+):([-\d.]+):([-\d.]+)\)')


def load_sdf(path):
    """{instance: worst IOPATH delay in ns} for every cell in the SDF."""
    by = {}
    for _, inst, body in CELL.findall(open(path, errors="replace").read()):
        vals = [max(abs(float(g)) for g in m.groups())
                for m in TRIPLE.finditer(body)]
        if vals:
            by[inst.replace("\\", "").strip()] = max(vals)
    return by


def series(by, prefix, exclude=(".ld.", "mon_", "keep", "snk")):
    """Worst cell per stage under `prefix`, summed. One element per stage."""
    per = collections.defaultdict(float)
    for k, v in by.items():
        if not k.startswith(prefix) or any(x in k for x in exclude):
            continue
        m = re.search(r"stage\[(\d+)\]", k)
        if m:
            per[int(m.group(1))] = max(per[int(m.group(1))], v)
    return sum(per.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sdf")
    ap.add_argument("--taps", type=int, default=32)
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.sdf):
        print(f"no SDF at {args.sdf}", file=sys.stderr)
        return 2
    by = load_sdf(args.sdf)
    if not by:
        print("no cells parsed; that is not an SDF", file=sys.stderr)
        return 2

    span = sum(v for k, v in by.items() if k.startswith("u_tdc.dl"))
    tap = span / args.taps if args.taps else 0.0
    # One ring period is two traversals of the line.
    period = 2 * span

    corner = os.path.basename(os.path.dirname(args.sdf)) or "unknown"
    print(f"corner            {corner}")
    print(f"tap delay         {tap:.4f} ns")
    print(f"line span         {span:.3f} ns over {args.taps} taps")
    print(f"ring period       {period:.3f} ns  (a wrap is worth {2*args.taps} taps)")

    # Fixed overhead charged to every reading: launch tree, launch gate, merge.
    over = sum(by.get(k, 0.0) for k in (
        "u_char.lrt.g4.u", "u_char.lbuf[0].u.g2.u", "u_char.gate[0].u.u",
        "u_char.merge[0].u.g4.u", "u_char.merge_out.g2.u"))
    print(f"fixed overhead    {over:.3f} ns  "
          f"({over/span*100:.0f} percent of one traversal)")

    rows = []
    for i, name in enumerate(CHAR_PATHS):
        s = series(by, f"u_char.p{i}.")
        if not s:
            continue
        tot = s + over
        rows.append((name, s, tot, tot / period))

    site = 0.0
    for c in SITE_CHAIN:
        hits = [v for k, v in by.items() if k.startswith(f"sites[0].u_site.{c}")]
        if hits:
            site += max(hits)
    n_sites = len({int(m.group(1)) for m in
                   (re.match(r"sites\[(\d+)\]", k) for k in by) if m})

    print()
    if args.markdown:
        print("| path | series ns | + overhead | ring periods | fits in fine range |")
        print("|---|---|---|---|---|")
        for n, s, t, f in rows:
            print(f"| {n} | {s:.3f} | {t:.3f} | {f:.2f} | "
                  f"{'yes' if f < 1 else 'NO, uses the coarse counter'} |")
    else:
        print(f"{'path':<20}{'series ns':>11}{'+overhead':>11}"
              f"{'ring periods':>14}  fine range")
        for n, s, t, f in rows:
            print(f"{n:<20}{s:.3f>11}" if False else
                  f"{n:<20}{s:>11.3f}{t:>11.3f}{f:>14.2f}  "
                  f"{'yes' if f < 1 else 'NO, coarse'}")

    print()
    print(f"one fabric site, series path: {site:.3f} ns "
          f"= {site/tap:.0f} taps = {site/period:.2f} ring periods")
    print(f"{n_sites} sites end to end:        {site*n_sites:.1f} ns "
          f"= {site*n_sites/period:.1f} ring periods")
    print()
    print("A linear line would have saturated on anything past one site. The")
    print("per-site stop tap in src/project.v is what makes the SLOPE, rather")
    print("than one unusable total, the thing being measured.")

    bad = [n for n, _, _, f in rows if f >= 1]
    if bad:
        print()
        print("REFERENCE PATHS OUTSIDE THE FINE RANGE:", ", ".join(bad))
        print("These depend on the coarse counter. That is allowed for a")
        print("measurement and NOT for a reference other measurements are")
        print("quoted against. See src/char_paths.v.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
