#!/usr/bin/env python3
"""Does the capture beat the kill? Answered from extraction, at every corner.

WHAT THE RACE IS

src/tdc.v samples the whole delay line on the arrival edge and, on the same
edge, kills the ring so it stops running. Those two things race. If the kill
reached the line first, the flip flops would latch a line the arrival edge never
saw, and the reading would be short by however far the kill had walked.

The design's argument for why the capture wins is short: the capture is one
buffer from the arrival edge and the kill is a flip flop, three gates and two
deliberate guard buffers from it. A short argument about a race is not a margin,
and the failure it guards against is not a crash. It is a reading that is wrong
by one or two taps, on some dies, at some corners, in a direction that looks
exactly like a fast path.

So the argument is replaced by a number, taken from the same extracted timing
the build already produces, and the number is checked.

WHAT IS COMPARED

    capture   samp_root -> branch buffer -> sampling flip flop clock pin
              taken at MAX, plus a hold allowance for the flop itself
    kill      samp_root -> kill flop -> guard buffers -> ring NAND -> line[1]
              taken at MIN, and found by searching the graph rather than by
              naming cells the flow invented

Both start at the root buffer's output, which is the last node they share, so
everything before it cancels and does not need to be modelled.

The hold allowance is a parameter and not a measurement. LibreLane's SDF carries
IOPATH delays and interconnect, not TIMINGCHECK records, so the flop's own hold
requirement is not in the file. The default is deliberately larger than any
sky130 dfxtp hold, and the point of the guard band on top of it is that the
answer should not be sensitive to either number.

USAGE

    tools/tdc_race.py <sdf> [--guard 0.10] [--hold 0.05] [--markdown]

Exits nonzero if the margin falls below the guard band, or if the structures it
needs are not in the SDF at all. A check that cannot find what it checks has to
fail; passing quietly is how a constraint that matches nothing gets shipped.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sdf_graph import load  # noqa: E402


def find_one(g, *needles, endswith=None):
    hits = [p for p in g.pins(*needles)
            if endswith is None or p.endswith(endswith)]
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sdf")
    ap.add_argument("--guard", type=float, default=0.10,
                    help="ns of margin required beyond the hold allowance")
    ap.add_argument("--hold", type=float, default=0.05,
                    help="ns allowed for the sampling flip flop's own hold")
    ap.add_argument("--taps", type=int, default=32,
                    help="how many sampling flops the tree must reach")
    ap.add_argument("--branches", type=int, default=4)
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
    print(f"timing edges          {g.n_iopath} iopath, "
          f"{g.n_interconnect} interconnect")

    # ------------------------------------------------------------- the root
    root_out = find_one(g, "samp_rt", endswith="/X")
    if not root_out:
        print("FAIL: no samp_rt output pin in the SDF. The sampling tree root "
              "is a keep/dont_touch cell; if it is gone, the tree it anchors "
              "is gone with it.", file=sys.stderr)
        return 1
    root = root_out[0]
    print(f"root                  {root}")

    # --------------------------------------------------------- the capture
    # SEARCHED, not counted in hops. The tree is built by hand in src/tdc.v as
    # one root and four branch buffers, and that is NOT what the flow built:
    # it inserted a fanout repeater, so the arrival edge reaches a sampling flop
    # through root, repeater, branch, flop. A tool that assumed the hop count
    # finds nothing here, which is what the first version of this one did.
    branch_outs = [p for p in g.pins("sampbuf") if p.endswith("/X")]
    if not branch_outs:
        print("FAIL: no sampbuf branch buffers in the SDF. The balanced "
              "sampling tree is not in the netlist.", file=sys.stderr)
        return 1

    samp_clks = set()
    for b in branch_outs:
        samp_clks |= {p for p in g.edges.get(b, {}) if p.endswith("/CLK")}
    if not samp_clks:
        print("FAIL: the sampling tree in the SDF does not reach any flip flop "
              "clock pin. Either the branch buffers were merged away or the "
              "capture registers were.", file=sys.stderr)
        return 1

    reach = g.slowest(root, lambda p: p.endswith("/CLK"))
    captured = {p: reach[p] for p in samp_clks if p in reach}
    if not captured:
        print("FAIL: no path from the sampling root to any sampling flip flop.",
              file=sys.stderr)
        return 1
    worst_capture, worst_path = max(captured.values())
    worst_desc = worst_path[-1]

    # SIZE IS GATED, NOT JUST PRINTED. If three of four branches vanished, or
    # thirty of thirty-two sampling flops did, the capture time computed from
    # whatever survived would be SMALLER, the margin would be LARGER, and this
    # tool would pass a converter that had mostly been optimised away.
    if len(branch_outs) != args.branches:
        print(f"FAIL: {len(branch_outs)} sampling branch buffers, expected "
              f"{args.branches}. The hand-built tree is not in the netlist and "
              f"a smaller tree makes this gate's margin look better.",
              file=sys.stderr)
        return 1
    # TAPS sampling flops plus one fired flag per branch.
    want_flops = args.taps + args.branches
    if len(samp_clks) != want_flops:
        print(f"FAIL: the sampling tree reaches {len(samp_clks)} flip flops, "
              f"expected {want_flops} ({args.taps} taps plus one fired flag per "
              f"branch). A capture register that is not there cannot be timed "
              f"and cannot be sampled.", file=sys.stderr)
        return 1

    # The four branches must be fed from ONE node, or the repeater the flow
    # inserted has unbalanced the tree that was hand built to be balanced.
    feeds = set()
    for b in branch_outs:
        inst = b.rsplit("/", 1)[0]
        feeds |= set(g.ins.get(f"{inst}/A", {}))
    print(f"capture, worst        {worst_capture:.4f} ns  (to {worst_desc})")
    print(f"                      {len(branch_outs)} branches, "
          f"{len(samp_clks)} sampling flops, fed from {len(feeds)} node(s)")
    for f in sorted(feeds):
        print(f"                        via {f}")
    if len(feeds) != 1:
        print(f"FAIL: the four branch buffers are driven from {len(feeds)} "
              f"different nodes. The tree is hand built balanced so that every "
              f"sampling flop is the same distance from the arrival edge; if "
              f"the branches are fed unequally then the skew is back to being "
              f"an accident of a tool run and it lands on the measurement.",
              file=sys.stderr)
        return 1

    # Flops clocked straight off the root rather than through a branch are the
    # ring kill and the coarse capture, which are meant to be there. Reported so
    # that a change in that population is visible rather than assumed.
    direct = {p for p in g.edges.get(root, {}) if p.endswith("/CLK")}
    print(f"                      {len(direct)} flops clocked directly from "
          f"the root (ring kill and the coarse capture)")
    spread = max(d for d, _ in captured.values()) - \
        min(d for d, _ in captured.values())
    print(f"sampling skew, spread {spread:.4f} ns  across the {len(captured)} "
          f"flops the arrival edge has to reach")

    # ------------------------------------------------------------ the kill
    # Searched, not named. Between the kill flop and the ring NAND sit an
    # inverter and an AND that the flow created and named itself, and the first
    # tap the kill can corrupt is the delay line's own first buffer output.
    first_tap = [p for p in g.pins("dl") if ".dl" in p and p.endswith("/X")]
    first_tap = [p for p in first_tap if "[0]" in p or ".dl.0." in p]
    if not first_tap:
        print("FAIL: no delay line stage 0 output in the SDF.", file=sys.stderr)
        return 1
    target = set(first_tap)
    kill, path = g.fastest(root, lambda p: p in target)
    if kill is None:
        print("FAIL: no path at all from the sampling root to the delay line. "
              "The ring kill is not connected, which means the ring never "
              "stops and every long measurement is a supply disturbance.",
              file=sys.stderr)
        return 1
    print(f"kill, fastest         {kill:.4f} ns  ({len(path)} pins)")
    for p in path:
        print(f"                        {p}")

    margin = kill - worst_capture - args.hold
    print(f"hold allowance        {args.hold:.4f} ns")
    print(f"MARGIN                {margin:+.4f} ns   "
          f"(guard band {args.guard:.4f} ns)")

    if args.markdown:
        print()
        print("| corner | capture (max) | kill (min) | hold | margin | verdict |")
        print("|---|---|---|---|---|---|")
        verdict = "pass" if margin >= args.guard else "FAIL"
        print(f"| {corner} | {worst_capture:.4f} ns | {kill:.4f} ns | "
              f"{args.hold:.4f} ns | {margin:+.4f} ns | {verdict} |")

    if margin < args.guard:
        print(f"\nFAIL: the capture beats the kill by only {margin:+.4f} ns "
              f"against a {args.guard:.4f} ns guard band. The converter would "
              f"latch a delay line the arrival edge never saw, and the error "
              f"would be a short reading, which is the direction that looks "
              f"like a result.", file=sys.stderr)
        return 1
    print("\nPASS: the capture closes before the kill can reach the line.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
