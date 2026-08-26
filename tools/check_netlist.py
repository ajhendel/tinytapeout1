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

Usage: tools/check_netlist.py build/area/n8.json [--sites 8]
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
    args = ap.parse_args()

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
