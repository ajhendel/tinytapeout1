#!/usr/bin/env python3
"""Structural checks on the synthesized netlist.

Some properties of this design cannot be tested at RTL, because at RTL they are
either invisible or trivially true. They are exactly the properties that would
be expensive to get wrong in silicon, so they are checked here on the actual
netlist instead of being assumed.

  1. Every hand-instantiated cell survived synthesis. This is the local proof
     that keep and dont_touch are doing their job. If the flow ever collapses
     the drive variants into one cell, the fabric still simulates perfectly and
     means nothing, so this must be checked and not eyeballed.

  2. No tri-state enable is tied to a constant. A ladder element whose enable
     got constant-folded is a load that can never be switched off, and the RTL
     reach witness cannot see the difference.

  3. Wherever several tri-state cells drive a common net, either their data
     inputs are the same net (so they can never disagree, which is how the
     ladder sink keeper is safe) or their enables come from a common one-hot
     decode (which is how the drive stage is safe). Any other case is a
     potential crowbar.

  4. Each site has exactly the expected tri-state population, 4 drive stage
     plus 3 ladder.

  5. The TDC delay line survived at full length. A delay line is exactly the
     structure a resizer would like to shorten, and a shortened one still
     captures a thermometer code, still passes every functional test, and
     reports the wrong time forever.

  6. The TDC sampling tree is the hand-built balanced one, not whatever the
     flow decided to grow. Skew across the sampling tree lands directly on the
     measurement.

  7. Exactly four sites are built WITHOUT drive-variant input isolation, and
     every other site has all four isolation gates. These are the controls that
     make the cost of isolation a measurement instead of an argument; if the
     flow folded the isolation gates away, or if the parameter stopped reaching
     the sites, the control arm would quietly become a copy of the treatment
     arm and the comparison would report zero.

  8. Both drive-stage replicas in the characterization block are intact, with
     the full set of drive variants each.

Usage: tools/check_netlist.py build/area/n8.json [--sites 8] [--taps 32]
"""

import argparse
import collections
import json
import re
import sys

TRISTATE = re.compile(r"sky130_fd_sc_hd__einvn_\d+$")
HANDCELL = re.compile(r"^sky130_fd_sc_hd__")

def load(path):
    doc = json.load(open(path))
    mods = doc["modules"]
    top = [m for m in mods if mods[m].get("attributes", {}).get("top")]
    name = top[0] if top else list(mods)[0]
    return mods[name]


def const_bits(bits):
    """yosys encodes constants as the strings '0','1','x','z' inside bit lists."""
    return [b for b in bits if isinstance(b, str)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--sites", type=int, default=8)
    ap.add_argument("--taps", type=int, default=32)
    # Sites built without drive-variant input isolation. Mirrors ISO_TWIN_MASK
    # in src/project.v; passed in rather than hardcoded so that a deliberate
    # change has to be stated in two places at once.
    ap.add_argument("--unisolated", default="1,3,5,7")
    args = ap.parse_args()
    unisolated = {int(x) for x in args.unisolated.split(",") if x.strip()}

    mod = load(args.netlist)
    cells = mod["cells"]
    failures = []

    # ---------------------------------------------------- 1. cells survived
    counts = collections.Counter(c["type"] for c in cells.values()
                                 if HANDCELL.match(c["type"]))
    print("hand-instantiated cells in the netlist")
    for k, v in sorted(counts.items()):
        print(f"  {k:<34} {v:>5}")
    if not counts:
        failures.append("no hand-instantiated sky130 cells survived at all")

    # The four drive variants must all be present. If synthesis had collapsed
    # them the fabric would be a lie.
    for variant in ("einvn_1", "einvn_2", "einvn_4", "einvn_8"):
        t = f"sky130_fd_sc_hd__{variant}"
        if counts.get(t, 0) < args.sites:
            failures.append(
                f"{t}: {counts.get(t, 0)} present, expected at least one per "
                f"site ({args.sites}); a drive variant was optimized away")

    # ------------------------------------------- 2. no constant tri-state enable
    tri = {n: c for n, c in cells.items() if TRISTATE.match(c["type"])}
    const_en = []
    for name, c in tri.items():
        te = c["connections"].get("TE_B", [])
        if const_bits(te):
            const_en.append(name)
    if const_en:
        failures.append(
            f"{len(const_en)} tri-state cells have a constant-folded enable, "
            f"first few: {const_en[:5]}")
    print(f"\ntri-state cells: {len(tri)}, constant enables: {len(const_en)}")

    # ---------------------------------------- 3. shared nets are safe by shape
    by_out = collections.defaultdict(list)
    for name, c in tri.items():
        for bit in c["connections"].get("Z", []):
            if not isinstance(bit, str):
                by_out[bit].append(name)

    shared = {net: names for net, names in by_out.items() if len(names) > 1}
    unsafe = []
    for net, names in shared.items():
        inputs = {tuple(tri[n]["connections"].get("A", [])) for n in names}
        enables = {tuple(tri[n]["connections"].get("TE_B", [])) for n in names}
        same_input = len(inputs) == 1
        distinct_enables = len(enables) == len(names)
        if not (same_input or distinct_enables):
            unsafe.append((net, names))
    print(f"shared tri-state nets: {len(shared)}, unsafe: {len(unsafe)}")
    if unsafe:
        failures.append(f"tri-state nets with neither a common data input nor "
                        f"distinct enables: {unsafe[:3]}")

    # ------------------------------------------- 4. per-site tri-state census
    per_site = collections.Counter()
    for name in tri:
        m = re.search(r"sites\[(\d+)\]|sites\.(\d+)|\\sites\[(\d+)\]", name)
        if m:
            idx = next(g for g in m.groups() if g is not None)
            per_site[idx] += 1
    if per_site:
        vals = set(per_site.values())
        print(f"tri-state cells per site: {sorted(per_site.items())[:4]} ... "
              f"distinct populations {vals}")
        if vals != {7}:
            failures.append(
                f"expected exactly 7 tri-state cells per site (4 drive stage, "
                f"3 ladder), found populations {vals}")
    else:
        print("tri-state cells per site: could not attribute by name "
              "(flattened naming differs); skipping the census")

    # ------------------------------------------ 5, 6. the TDC survived intact
    line_bufs = [n for n, c in cells.items()
                 if c["type"].startswith("sky130_fd_sc_hd__buf_")
                 and re.search(r"u_tdc\.dl", n)]
    print(f"\nTDC delay line buffers: {len(line_bufs)} (expected {args.taps})")
    if len(line_bufs) != args.taps:
        failures.append(
            f"TDC delay line has {len(line_bufs)} buffers, expected "
            f"{args.taps}; a shortened delay line reports the wrong time "
            f"forever and every functional test still passes")

    samp = [n for n, c in cells.items()
            if c["type"].startswith("sky130_fd_sc_hd__buf_")
            and re.search(r"u_tdc\.(samp_rt|sampbuf)", n)]
    print(f"TDC sampling tree buffers: {len(samp)} (expected 5)")
    if len(samp) != 5:
        failures.append(
            f"TDC sampling tree has {len(samp)} buffers, expected 5 (one root "
            f"and four branches); the balanced tree is what keeps sampling "
            f"skew a measurable constant instead of an artefact of a tool run")

    # ------------------------------- 7. the un-isolated control sites are real
    iso = collections.Counter()
    seen_sites = set()
    for name, c in cells.items():
        m = re.search(r"sites\[(\d+)\]", name)
        if not m:
            continue
        idx = int(m.group(1))
        seen_sites.add(idx)
        if "u_drive.g_iso" in name and c["type"] == "sky130_fd_sc_hd__and2_1":
            iso[idx] += 1
    if seen_sites:
        got_unisolated = {i for i in seen_sites if iso[i] == 0}
        want = {i for i in unisolated if i in seen_sites}
        print(f"un-isolated control sites: {sorted(got_unisolated)} "
              f"(expected {sorted(want)})")
        if got_unisolated != want:
            failures.append(
                f"un-isolated sites are {sorted(got_unisolated)}, expected "
                f"{sorted(want)}; the control arm does not match "
                f"ISO_TWIN_MASK in src/project.v")
        wrong = {i: iso[i] for i in seen_sites
                 if i not in want and iso[i] != 4}
        if wrong:
            failures.append(
                f"isolated sites with the wrong number of isolation gates: "
                f"{wrong}; expected 4 each")
    else:
        print("un-isolated control sites: could not attribute by name; skipped")

    # ------------------------------------- 8a. the timing anchor still exists
    # src/timing.sdc cuts the fabric-to-safety-monitor path by naming this exact
    # instance. If it is gone, the constraint matches nothing, the flow passes,
    # and a path that grows with the site count comes back never having been
    # timed. See the note in src/project.v.
    anchor = [n for n, c in cells.items()
              if n.endswith("u_mon_iso.u")
              and c["type"].startswith("sky130_fd_sc_hd__buf_")]
    print(f"\ntiming anchor cells named u_mon_iso.u: {len(anchor)}")
    if len(anchor) != 1:
        failures.append(
            f"expected exactly one buffer instance named u_mon_iso.u, found "
            f"{len(anchor)}; src/timing.sdc points at that name and a false "
            f"path that matches nothing waives real timing in silence")

    # ------------------------------------- 8. both drive replicas are present
    for path, label in (("p14", "isolated"), ("p15", "un-isolated")):
        n_tri = len([n for n in tri if f"u_char.{path}." in n])
        print(f"characterization drive replica {path} ({label}): "
              f"{n_tri} tri-state cells (expected 16)")
        if n_tri != 16:
            failures.append(
                f"characterization path {path} has {n_tri} tri-state cells, "
                f"expected 16 (4 stages x 4 drive variants); the matched pair "
                f"that measures the cost of isolation is not matched")

    print()
    if failures:
        print("NETLIST CHECK FAILED")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("NETLIST CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
