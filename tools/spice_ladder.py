#!/usr/bin/env python3
"""Transistor-level SPICE on the load ladder pair. The one question Liberty cannot answer.

WHY THIS EXISTS

src/load_ladder.v carries an argument about transistors: enabling a ladder
element does not connect a capacitor, because the A input is permanently
connected, but it does change what the gate-to-source capacitance faces (a rail
when enabled, a floating internal node when disabled) and it does change how
fast the shared sink moves, which changes the Miller current back through a
gate-to-drain capacitance that was there all along.

Two model layers cannot check that argument.

  The released sky130 Liberty view assigns one capacitance number to this pin
  and does not represent any dependence on TE_B. Its prediction for this pair is
  EXACTLY ZERO. That is not a small number; it is the absence of the mechanism.
  Said about the view we compile against, which is checkable, rather than about
  what the format could carry, which is not what anyone measured.

  The extracted SDF inherits Liberty's capacitance and adds parasitics, so its
  number for this pair is routing. Two builds of the UNCHANGED circuit gave 7 ps
  and 57 ps. A quantity that moves eightfold when nothing changes is not a
  measurement of a mechanism.

So the pair goes to SPICE, which is the lowest layer available before silicon,
and the answer decides how docs/EXPERIMENT_MATRIX.md is allowed to write that
row: a resolvable measurement, a repeated statistical one, or an upper bound.
All three are legitimate results and the choice is preregistered rather than
made after looking at the dies.

WHAT IS SIMULATED

Both chains, in one deck, driven by the same source. Eight inverter stages each,
every stage carrying the ladder from src/load_ladder.v, identical in every
respect except that one chain's enables are tied high and the other's low. One
deck rather than two runs, so nothing about the solver or the stimulus can
differ between the two halves of a matched pair. That claim is now CHECKED
rather than asserted: the null control runs both arms disabled and requires the
delta to come out at zero.

WHAT IS SIMPLIFIED, STATED HERE RATHER THAN IMPLIED AWAY

This is not literally the die circuit and it should not be described as one.
Three things are left out, each because it cannot reach the measured node.
src/load_ladder.v's three xor2 monitor gates hang off the sink buffer's output,
downstream of everything timed here. The inverter inside cell_einvn that drives
TE_B is replaced by an ideal source, which is static during a measurement. And
this is a PRE-LAYOUT deck: no wire RC and no supply parasitics, so the die is
not required to land on this number. The enabled chain draws several times the
sink current of the disabled one and would droop a real local rail, and wire
capacitance on the sink node would dilute the Miller half of the mechanism.
The prediction has to be written with that stated.

PIN ORDER IS READ, NOT ASSUMED

The cell subcircuit pin order is taken out of the PDK's own spice library at run
time and the deck is generated from it. Guessing it would produce a netlist that
simulates happily with the enable wired to a supply, and the result would be a
clean, plausible, meaningless number.

USAGE

    tools/spice_ladder.py --pdk $PDK_ROOT/sky130A [--corner tt] [--dry-run]
    tools/spice_ladder.py --pdk ... --sweep --json spice_ladder.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

KEEPERS = ["sky130_fd_sc_hd__inv_1", "sky130_fd_sc_hd__inv_2",
           "sky130_fd_sc_hd__inv_4", "sky130_fd_sc_hd__inv_8",
           "sky130_fd_sc_hd__inv_16"]

CELLS = ["sky130_fd_sc_hd__inv_1",
         "sky130_fd_sc_hd__buf_1",
         "sky130_fd_sc_hd__einvn_1",
         "sky130_fd_sc_hd__einvn_2",
         "sky130_fd_sc_hd__einvn_4"] + KEEPERS[1:]

# The converter's own tap, simulated rather than assumed constant.
#
# The first version of this tool divided a corner-dependent delay by a FIXED tap
# of 0.082 ns, which is the extracted value at the typical corner only. The tap
# is a delay line built out of the same buffers as everything else, so it moves
# with corner too, and dividing a slow-corner delay by a typical-corner tap
# overstates the answer at ss and understates it at ff. It reported a spread of
# 2.00 to 3.89 taps across the sweep where the true spread is far tighter.
#
# So the deck carries a reference chain of plain buffers, the same cell the
# delay line is made of, and its per-stage delay at each corner scales the
# extracted tap. The anchor is extraction at the typical corner, which is the
# one place the two methods are supposed to agree.
REF_STAGES = 16

# Matches the shipped design: char_ladder_chain has DEPTH 8 and the ladder is
# the one in src/load_ladder.v, one per stage.
DEPTH = 8


def subckt_pins(spice_path, names):
    """{cell: [pin, ...]} straight out of the PDK's own netlist."""
    want = set(names)
    found = {}
    pat = re.compile(r"^\s*\.subckt\s+(\S+)\s+(.*)$", re.I)
    with open(spice_path, errors="replace") as fh:
        for line in fh:
            m = pat.match(line)
            if m and m.group(1) in want:
                found[m.group(1)] = m.group(2).split()
    return found


def order(pins, mapping):
    """Positional connections for one instance, from a pin-name mapping.

    Every pin the PDK declares has to be in the mapping. A missing one is a
    netlist with a floating terminal, which simulates fine and means nothing.
    """
    out = []
    for p in pins:
        if p not in mapping:
            raise KeyError(f"no net for pin {p}; the PDK declares {pins}")
        out.append(mapping[p])
    return out


def ref_chain(pins):
    """A plain buffer chain, the cell the TDC delay line is made of.

    Its per-stage delay is not interesting in itself. It is here so that the
    tap can be scaled to the corner being simulated instead of being held at
    its typical-corner value while everything around it moves.
    """
    lines = ["* ---- reference buffer chain, for the corner's tap width"]
    node = "stim"
    for i in range(REF_STAGES):
        nxt = f"ref_n{i+1}"
        lines.append("Xref{} {} {}".format(
            i, " ".join(order(pins["sky130_fd_sc_hd__buf_1"], {
                "A": node, "X": nxt, "VGND": "VGND", "VNB": "VGND",
                "VPB": "VPWR", "VPWR": "VPWR"})),
            "sky130_fd_sc_hd__buf_1"))
        node = nxt
    lines.append(f".save v(ref_n{REF_STAGES})")
    return lines, f"ref_n{REF_STAGES}"


def chain(tag, teb_net, pins, keeper="sky130_fd_sc_hd__inv_1"):
    """DEPTH inverter stages, each carrying one load ladder."""
    lines = [f"* ---- chain {tag}: ladder enables tied "
             f"{'low' if teb_net == 'VPWR' else 'high'}"
             f" (TE_B is active low, so EN high means TE_B on {teb_net})"]
    node = "stim"
    for i in range(DEPTH):
        nxt = f"{tag}_n{i+1}"
        lines.append("X{}_inv{} {} {}".format(
            tag, i, " ".join(order(pins["sky130_fd_sc_hd__inv_1"], {
                "A": node, "Y": nxt, "VGND": "VGND", "VNB": "VGND",
                "VPB": "VPWR", "VPWR": "VPWR"})),
            "sky130_fd_sc_hd__inv_1"))
        sk = f"{tag}_sk{i+1}"
        lines.append("X{}_keep{} {} {}".format(
            tag, i, " ".join(order(pins[keeper], {
                "A": nxt, "Y": sk, "VGND": "VGND", "VNB": "VGND",
                "VPB": "VPWR", "VPWR": "VPWR"})),
            keeper))
        for w in (1, 2, 4):
            cell = f"sky130_fd_sc_hd__einvn_{w}"
            lines.append("X{}_ld{}_{} {} {}".format(
                tag, w, i, " ".join(order(pins[cell], {
                    "A": nxt, "TE_B": teb_net, "Z": sk, "VGND": "VGND",
                    "VNB": "VGND", "VPB": "VPWR", "VPWR": "VPWR"})),
                cell))
        lines.append("X{}_snk{} {} {}".format(
            tag, i, " ".join(order(pins["sky130_fd_sc_hd__inv_1"], {
                "A": sk, "Y": f"{tag}_skb{i+1}", "VGND": "VGND",
                "VNB": "VGND", "VPB": "VPWR", "VPWR": "VPWR"})),
            "sky130_fd_sc_hd__inv_1"))
        node = nxt
    lines.append(f".save v({tag}_n{DEPTH})")
    return lines, f"{tag}_n{DEPTH}"


def deck(pdk, corner, vdd, temp, pins, keeper="sky130_fd_sc_hd__inv_1",
         null_control=False):
    """Both chains and the reference line, in ONE deck.

    One deck rather than two runs, so that nothing about the solver, the
    stimulus or the operating point can differ between the two halves of a
    matched pair.

    null_control ties BOTH chains' enables the same way. The delta then has to
    come out at exactly zero, and if it does not, this deck has a tag-dependent
    or instance-ordering asymmetry and every number it has ever produced is
    void. That check is cheap and it was not being run.
    """
    lib = os.path.join(pdk, "libs.tech", "ngspice", "sky130.lib.spice")
    cells = os.path.join(pdk, "libs.ref", "sky130_fd_sc_hd", "spice",
                         "sky130_fd_sc_hd.spice")
    # TE_B is active low. Enables low means TE_B at the positive rail.
    # VGND rather than the global node 0: they are shorted today, and the moment
    # anyone adds supply parasitics to model rail droop the enabled arm would
    # silently bypass them while the disabled arm would not, and the matched
    # pair would stop being matched without anything looking different.
    off, off_out = chain("off", "VPWR", pins, keeper)
    on, on_out = chain("on", "VPWR" if null_control else "VGND", pins, keeper)
    ref, ref_out = ref_chain(pins)
    half = vdd / 2.0
    L = [
        f"* load ladder matched pair, {corner} {vdd} V {temp} C, generated by",
        "* tools/spice_ladder.py. Do not edit; edit the generator.",
        f'.lib "{lib}" {corner}',
        f'.include "{cells}"',
        f".temp {temp}",
        "",
        f"VPWR VPWR 0 {vdd}",
        "VGND VGND 0 0",
        # Several cycles, and the measurement is taken on the THIRD edge.
        #
        # The disabled arm's einvn internal nodes are genuinely floating, so on
        # the very first edge after the DC operating point they sit wherever the
        # solver's leakage balance put them rather than where a few cycles of
        # capacitive pumping would put them. Measuring the first edge ever made
        # the least settled number in the sweep the one closest to the category
        # boundary.
        #
        # A realistic input slew, not an ideal step: a step would put both chains
        # in a region no cell on this die ever sees and would flatter whichever
        # mechanism is most slew sensitive, which is the one under test.
        f"Vin drv 0 PULSE(0 {vdd} 2n 0.15n 0.15n 4n 8n)",
        # One driving inverter shared by both chains and the reference, so every
        # arm sees exactly the same edge. Anything before this point cancels.
        "X_stim {} sky130_fd_sc_hd__inv_1".format(
            " ".join(order(pins["sky130_fd_sc_hd__inv_1"], {
                "A": "drv", "Y": "stim", "VGND": "VGND", "VNB": "VGND",
                "VPB": "VPWR", "VPWR": "VPWR"}))),
        ".save v(stim)",
        "",
    ]
    L += off + [""] + on + [""] + ref + [""]
    L += [".tran 1p 40n"]
    for tag, out in (("off", off_out), ("on", on_out), ("ref", ref_out)):
        L += [f".meas tran tr_{tag} TRIG v(stim) VAL={half} RISE=3 "
              f"TARG v({out}) VAL={half} RISE=3",
              f".meas tran tf_{tag} TRIG v(stim) VAL={half} FALL=3 "
              f"TARG v({out}) VAL={half} FALL=3"]
    L += [".end", ""]
    return "\n".join(L)


MEAS = re.compile(r"^\s*(tr_off|tf_off|tr_on|tf_on|tr_ref|tf_ref)\s*=\s*"
                  r"([-\d.eE+]+)", re.M | re.I)


def run(text, ngspice="ngspice"):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ladder.spice")
        with open(p, "w") as fh:
            fh.write(text)
        r = subprocess.run([ngspice, "-b", p], capture_output=True, text=True)
    out = r.stdout + r.stderr
    vals = {k.lower(): float(v) for k, v in MEAS.findall(out)}
    return vals, out


def measure(pdk, corner, vdd, temp, pins, ngspice, keeper=KEEPERS[0],
            null_control=False):
    """One simulation. Returns the four chain delays and the reference stage."""
    text = deck(pdk, corner, vdd, temp, pins, keeper, null_control)
    vals, log = run(text, ngspice)
    need = {"tr_off", "tf_off", "tr_on", "tf_on", "tr_ref", "tf_ref"}
    if not need <= set(vals):
        raise RuntimeError(f"{corner} {vdd}V {temp}C produced no measurements. "
                           f"ngspice said:\n{log[-3000:]}")
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk", default=os.path.join(os.environ.get("PDK_ROOT", ""),
                                                  "sky130A"))
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--vdd", type=float, default=1.8)
    ap.add_argument("--temp", type=float, default=25)
    ap.add_argument("--tap", type=float, default=0.082,
                    help="ns per TDC tap AT THE TYPICAL CORNER, from extraction. "
                         "It is scaled to each corner by the reference chain.")
    ap.add_argument("--sweep", action="store_true",
                    help="corners, supplies and temperatures, including the "
                         "combinations that minimise and maximise the effect")
    ap.add_argument("--decompose", action="store_true",
                    help="sweep the keeper strength to separate the two "
                         "mechanisms src/load_ladder.v names")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--ngspice", default="ngspice")
    args = ap.parse_args()

    cells = os.path.join(args.pdk, "libs.ref", "sky130_fd_sc_hd", "spice",
                         "sky130_fd_sc_hd.spice")
    if not os.path.exists(cells):
        print(f"no cell netlist at {cells}. Point --pdk at a sky130A install.",
              file=sys.stderr)
        return 2
    pins = subckt_pins(cells, CELLS)
    missing = [c for c in CELLS if c not in pins]
    if missing:
        print(f"the PDK netlist does not define {missing}", file=sys.stderr)
        return 2
    for c in CELLS:
        print(f"pin order  {c:<32} {' '.join(pins[c])}")
    print()

    if args.dry_run:
        print(deck(args.pdk, args.corner, args.vdd, args.temp, pins))
        return 0

    # --------------------------------------------------------- the null control
    # Run FIRST, and refuse to report anything if it fails. The deck's entire
    # claim is that one deck means nothing can differ between the two halves of
    # a matched pair. That claim had never been tested. If two identically
    # configured chains do not come out identical, then tag-dependent node
    # naming or instance ordering is worth picosecords, and every delta this
    # tool has ever printed is that asymmetry rather than the mechanism.
    print("null control: both chains disabled, the delta must be zero")
    try:
        n = measure(args.pdk, "tt", 1.8, 25, pins, args.ngspice,
                    null_control=True)
    except RuntimeError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    null_r = (n["tr_on"] - n["tr_off"]) * 1e12
    null_f = (n["tf_on"] - n["tf_off"]) * 1e12
    print(f"  rise {null_r:+.4f} ps, fall {null_f:+.4f} ps")
    if max(abs(null_r), abs(null_f)) > 0.05:
        print(f"\nFAIL: two identically configured chains differ by "
              f"{max(abs(null_r), abs(null_f)):.4f} ps. The deck has an "
              f"asymmetry that is not the enable state, so no number from it "
              f"means anything.", file=sys.stderr)
        return 1
    print("  PASS: the two arms are identical when configured identically\n")

    cases = [(args.corner, args.vdd, args.temp)]
    if args.sweep:
        # One factor at a time misses the corner that matters. The effect is
        # smallest fast-and-cold-and-high and largest slow-and-hot-and-low, and
        # neither of those combinations was being simulated, so the category was
        # being chosen on a sweep that omitted its own worst case.
        cases = [("tt", 1.80, 25),
                 ("tt", 1.80, -40), ("tt", 1.80, 100),
                 ("tt", 1.62, 25), ("tt", 1.98, 25),
                 ("ss", 1.80, 100), ("ff", 1.80, -40),
                 ("ss", 1.62, 100),      # the effect at its largest
                 ("ff", 1.98, -40)]      # the effect at its smallest

    results = []
    for corner, vdd, temp in cases:
        try:
            v = measure(args.pdk, corner, vdd, temp, pins, args.ngspice)
        except RuntimeError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1
        results.append(dict(
            corner=corner, vdd=vdd, temp=temp,
            tr_off_ps=v["tr_off"] * 1e12, tf_off_ps=v["tf_off"] * 1e12,
            tr_on_ps=v["tr_on"] * 1e12, tf_on_ps=v["tf_on"] * 1e12,
            ref_stage_ps=max(v["tr_ref"], v["tf_ref"]) * 1e12 / REF_STAGES,
            d_rise_ps=(v["tr_on"] - v["tr_off"]) * 1e12,
            d_fall_ps=(v["tf_on"] - v["tf_off"]) * 1e12))

    # The tap at the TYPICAL corner is the extraction anchor; every other
    # corner's tap is scaled by the same reference chain that ran in the same
    # deck. Dividing a slow-corner delay by a typical-corner tap is how the
    # first version of this tool reported a 2.00 to 3.89 tap spread for an
    # effect whose real spread is much tighter.
    anchor = next((r for r in results
                   if r["corner"] == "tt" and abs(r["vdd"] - 1.80) < 1e-9
                   and abs(r["temp"] - 25) < 1e-9), results[0])
    for r in results:
        r["tap_ps"] = args.tap * 1000.0 * (r["ref_stage_ps"] /
                                           anchor["ref_stage_ps"])
        r["worst_taps"] = max(abs(r["d_rise_ps"]),
                              abs(r["d_fall_ps"])) / r["tap_ps"]
        r["d_rise_per_stage_ps"] = r["d_rise_ps"] / DEPTH
        r["d_fall_per_stage_ps"] = r["d_fall_ps"] / DEPTH

    print(f"Every delta below is for the WHOLE {DEPTH} stage chain, not per "
          f"stage. Per stage is one eighth of it and is in the JSON.")
    print()
    print("| corner | V | C | off, rise | on, rise | delta rise | delta fall | "
          "tap at this corner | taps |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['corner']} | {r['vdd']:.2f} | {r['temp']:.0f} | "
              f"{r['tr_off_ps']:.1f} ps | {r['tr_on_ps']:.1f} ps | "
              f"{r['d_rise_ps']:+.1f} ps | {r['d_fall_ps']:+.1f} ps | "
              f"{r['tap_ps']:.1f} ps | {r['worst_taps']:.2f} |")

    deltas = [r["d_rise_ps"] for r in results] + [r["d_fall_ps"] for r in results]
    signs = {d > 0 for d in deltas}
    worst_taps = max(r["worst_taps"] for r in results)
    best_taps = min(min(abs(r["d_rise_ps"]), abs(r["d_fall_ps"])) / r["tap_ps"]
                    for r in results)
    fracs = [abs(r["d_rise_ps"]) / r["tr_off_ps"] for r in results]
    print()
    print(f"delta, largest         {max(abs(d) for d in deltas):+.1f} ps   "
          f"({worst_taps:.2f} taps at its own corner)")
    print(f"delta, smallest        {min(abs(d) for d in deltas):+.1f} ps   "
          f"({best_taps:.2f} taps at its own corner)")
    print(f"as a fraction of the disabled chain: "
          f"{min(fracs):.1%} to {max(fracs):.1%}")
    print(f"sign, consistent       {'yes' if len(signs) == 1 else 'NO'}")
    print()
    print("The fraction is the load bearing number. A capacitance ratio effect")
    print("is scale invariant, so a nearly constant fraction across corners")
    print("whose absolute delays span twofold is evidence the mechanism is real")
    print("rather than a solver artefact. A floating node artefact would not")
    print("track the base delay.")
    print()
    if best_taps >= 1.0:
        print("CATEGORY: resolvable measurement. The effect exceeds one tap at "
              "every corner simulated, each measured against ITS OWN corner's "
              "tap, so a single trial per configuration can read it.")
    elif worst_taps >= 1.0:
        print("CATEGORY: repeated statistical measurement. The effect exceeds "
              "one tap at some corners and not others, so the row needs a "
              "repeat count AND has to state that the repeats only help if the "
              "arrival time dithers across bin boundaries.")
    else:
        print("CATEGORY: upper bound. The effect is below one tap everywhere "
              "simulated. That is a legitimate result and the row has to be "
              "written as a bound with a preregistered confidence level.")
    if len(signs) != 1:
        print("\nWARNING: the sign of the effect is not the same at every "
              "corner, so it cannot be quoted as one number and the matrix row "
              "has to name the condition.")

    # ------------------------------------------------- mechanism decomposition
    decomposition = None
    if args.decompose:
        print()
        print("## Which of the two mechanisms is doing the work")
        print()
        print("src/load_ladder.v names two. (a) The gate to source capacitance")
        print("faces a rail when enabled and a floating node when disabled.")
        print("(b) Enabling also makes the element drive the shared sink, so")
        print("the sink moves faster and the Miller current back through the")
        print("gate to drain capacitance rises.")
        print()
        print("Strengthening the keeper makes the sink's edge rate its own")
        print("business, so enabling the ladder barely changes it and (b)")
        print("collapses. What survives at a strong keeper is (a). One sweep,")
        print("both mechanisms, no new topology.")
        print()
        print("| keeper | delta rise | delta fall | attributed |")
        print("|---|---|---|---|")
        rows = []
        for k in KEEPERS:
            v = measure(args.pdk, "tt", 1.80, 25, pins, args.ngspice, keeper=k)
            dr = (v["tr_on"] - v["tr_off"]) * 1e12
            df = (v["tf_on"] - v["tf_off"]) * 1e12
            rows.append(dict(keeper=k, d_rise_ps=dr, d_fall_ps=df))
        base = rows[0]["d_rise_ps"]
        asym = rows[-1]["d_rise_ps"]
        for r in rows:
            note = ("both (a) and (b)" if r is rows[0]
                    else "mostly (a)" if r is rows[-1] else "")
            print(f"| {r['keeper'].split('__')[1]} | {r['d_rise_ps']:+.1f} ps | "
                  f"{r['d_fall_ps']:+.1f} ps | {note} |")
        print()
        print(f"mechanism (a), the gate to source term: about {asym:+.1f} ps")
        print(f"mechanism (b), the Miller term:         about {base-asym:+.1f} ps")
        print()
        print("If the asymptote is near zero the effect is all Miller and the")
        print("gate to source half of the comment in src/load_ladder.v is")
        print("wrong. If it is near the whole delta the Miller half is wrong.")
        print("Either way the comment gets corrected rather than defended.")
        decomposition = dict(rows=rows, mechanism_a_ps=asym,
                             mechanism_b_ps=base - asym)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(dict(depth=DEPTH, tap_ns_typical=args.tap,
                           ref_stages=REF_STAGES,
                           note=("every d_*_ps is for the whole chain of "
                                 f"{DEPTH} stages, not per stage"),
                           null_control_ps=dict(rise=null_r, fall=null_f),
                           cases=results, decomposition=decomposition),
                      fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
