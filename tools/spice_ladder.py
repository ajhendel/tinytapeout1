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
differ between the two halves of a matched pair.

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

CELLS = ["sky130_fd_sc_hd__inv_1",
         "sky130_fd_sc_hd__einvn_1",
         "sky130_fd_sc_hd__einvn_2",
         "sky130_fd_sc_hd__einvn_4"]

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


def chain(tag, teb_net, pins):
    """DEPTH inverter stages, each carrying one load ladder."""
    lines = [f"* ---- chain {tag}: ladder enables tied "
             f"{'high' if teb_net == '0' else 'low'}"]
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
            tag, i, " ".join(order(pins["sky130_fd_sc_hd__inv_1"], {
                "A": nxt, "Y": sk, "VGND": "VGND", "VNB": "VGND",
                "VPB": "VPWR", "VPWR": "VPWR"})),
            "sky130_fd_sc_hd__inv_1"))
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


def deck(pdk, corner, vdd, temp, pins):
    lib = os.path.join(pdk, "libs.tech", "ngspice", "sky130.lib.spice")
    cells = os.path.join(pdk, "libs.ref", "sky130_fd_sc_hd", "spice",
                         "sky130_fd_sc_hd.spice")
    off, off_out = chain("off", "VPWR", pins)   # TE_B high  -> disabled
    on, on_out = chain("on", "0", pins)         # TE_B low   -> enabled
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
        # A realistic input slew. An ideal step would put both chains in a
        # region no cell on this die ever sees and would flatter whichever
        # mechanism is most sensitive to slew, which is the one under test.
        f"Vin drv 0 PULSE(0 {vdd} 2n 0.15n 0.15n 8n 16n)",
        # One driving inverter shared by both chains, so the pair sees exactly
        # the same edge. Anything before this point cancels.
        "X_stim {} sky130_fd_sc_hd__inv_1".format(
            " ".join(order(pins["sky130_fd_sc_hd__inv_1"], {
                "A": "drv", "Y": "stim", "VGND": "VGND", "VNB": "VGND",
                "VPB": "VPWR", "VPWR": "VPWR"}))),
        "",
    ]
    L += off + [""] + on + ["",
                            ".tran 1p 20n",
                            f".meas tran tr_off TRIG v(stim) VAL={half} RISE=1 "
                            f"TARG v({off_out}) VAL={half} RISE=1",
                            f".meas tran tf_off TRIG v(stim) VAL={half} FALL=1 "
                            f"TARG v({off_out}) VAL={half} FALL=1",
                            f".meas tran tr_on TRIG v(stim) VAL={half} RISE=1 "
                            f"TARG v({on_out}) VAL={half} RISE=1",
                            f".meas tran tf_on TRIG v(stim) VAL={half} FALL=1 "
                            f"TARG v({on_out}) VAL={half} FALL=1",
                            ".end", ""]
    return "\n".join(L)


MEAS = re.compile(r"^\s*(tr_off|tf_off|tr_on|tf_on)\s*=\s*([-\d.eE+]+)",
                  re.M | re.I)


def run(text, ngspice="ngspice"):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ladder.spice")
        with open(p, "w") as fh:
            fh.write(text)
        r = subprocess.run([ngspice, "-b", p], capture_output=True, text=True)
    out = r.stdout + r.stderr
    vals = {k.lower(): float(v) for k, v in MEAS.findall(out)}
    return vals, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk", default=os.path.join(os.environ.get("PDK_ROOT", ""),
                                                  "sky130A"))
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--vdd", type=float, default=1.8)
    ap.add_argument("--temp", type=float, default=25)
    ap.add_argument("--tap", type=float, default=0.082,
                    help="ns per TDC tap, for quoting the answer in taps")
    ap.add_argument("--sweep", action="store_true",
                    help="corners, supplies and temperatures")
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

    cases = [(args.corner, args.vdd, args.temp)]
    if args.sweep:
        cases = [("tt", 1.80, 25), ("tt", 1.80, -40), ("tt", 1.80, 100),
                 ("ss", 1.80, 100), ("ff", 1.80, -40),
                 ("tt", 1.62, 25), ("tt", 1.98, 25)]

    results = []
    for corner, vdd, temp in cases:
        vals, log = run(deck(args.pdk, corner, vdd, temp, pins), args.ngspice)
        need = {"tr_off", "tf_off", "tr_on", "tf_on"}
        if not need <= set(vals):
            print(f"FAIL: {corner} {vdd}V {temp}C produced no measurements. "
                  f"ngspice said:\n{log[-3000:]}", file=sys.stderr)
            return 1
        d_rise = (vals["tr_on"] - vals["tr_off"]) * 1e12      # ps
        d_fall = (vals["tf_on"] - vals["tf_off"]) * 1e12
        results.append(dict(corner=corner, vdd=vdd, temp=temp,
                            tr_off_ps=vals["tr_off"] * 1e12,
                            tf_off_ps=vals["tf_off"] * 1e12,
                            tr_on_ps=vals["tr_on"] * 1e12,
                            tf_on_ps=vals["tf_on"] * 1e12,
                            d_rise_ps=d_rise, d_fall_ps=d_fall))

    tap_ps = args.tap * 1000.0
    print("| corner | V | C | chain off, rise | on, rise | delta rise | "
          "delta fall | worst, taps |")
    print("|---|---|---|---|---|---|---|---|")
    for r in results:
        worst = max(abs(r["d_rise_ps"]), abs(r["d_fall_ps"])) / tap_ps
        print(f"| {r['corner']} | {r['vdd']:.2f} | {r['temp']:.0f} | "
              f"{r['tr_off_ps']:.1f} ps | {r['tr_on_ps']:.1f} ps | "
              f"{r['d_rise_ps']:+.1f} ps | {r['d_fall_ps']:+.1f} ps | "
              f"{worst:.2f} |")

    deltas = [r["d_rise_ps"] for r in results] + [r["d_fall_ps"] for r in results]
    signs = {d > 0 for d in deltas}
    biggest = max(abs(d) for d in deltas)
    smallest = min(abs(d) for d in deltas)
    print()
    print(f"delta, worst case      {biggest:+.1f} ps   ({biggest/tap_ps:.2f} taps)")
    print(f"delta, best case       {smallest:+.1f} ps   ({smallest/tap_ps:.2f} taps)")
    print(f"sign, consistent       {'yes' if len(signs) == 1 else 'NO'}")
    print()
    if smallest / tap_ps >= 1.0:
        print("CATEGORY: resolvable measurement. The effect exceeds one tap at "
              "every corner simulated, so a single trial per configuration can "
              "read it.")
    elif biggest / tap_ps >= 1.0:
        print("CATEGORY: repeated statistical measurement. The effect exceeds "
              "one tap at some corners and not others, so the row needs a "
              "repeat count AND has to state that the repeats only help if the "
              "arrival time dithers across bin boundaries. Whether this die "
              "dithers is a measurement, not an assumption.")
    else:
        print("CATEGORY: upper bound. The effect is below one tap everywhere "
              "simulated. That is a legitimate result and the row has to be "
              "written as a bound with a preregistered confidence level, not "
              "as a measurement that failed.")
    if len(signs) != 1:
        print("\nWARNING: the sign of the effect is not the same at every "
              "corner. A mechanism whose direction depends on temperature or "
              "supply cannot be quoted as one number and the matrix row has to "
              "name the condition.")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(dict(depth=DEPTH, tap_ns=args.tap, cases=results), fh,
                      indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
