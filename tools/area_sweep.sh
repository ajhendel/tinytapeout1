#!/usr/bin/env bash
# Marginal cells per fabric site.
#
# The number that matters for the area gate is the MARGINAL cost of a site, not
# the total divided by the site count. Dividing charges the fixed infrastructure
# (scan chain, CRC, safety controller, counters, calibration strip) to the sites
# and makes the fabric look far more expensive than it is. So build at several
# site counts and take the slope.
#
# This runs yosys locally against blackbox stubs, which is light and gives an
# exact count of the hand-instantiated cells, because those are fixed by
# construction rather than chosen by synthesis. It does NOT give area. Area
# comes from the LibreLane run in Tiny Tapeout's GitHub Actions, which is the
# authoritative number and costs this machine nothing.
#
# Usage: tools/area_sweep.sh [outdir]

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/build/area}"
mkdir -p "$OUT"

for N in 1 2 4 8 16; do
  yosys -q -p "
    read_verilog -sv $ROOT/tools/sky130_blackbox.v
    read_verilog -sv -DN_SITES=$N $ROOT/src/cells.v $ROOT/src/fabric_site.v \
                     $ROOT/src/calib_macro.v $ROOT/src/scan_config.v \
                     $ROOT/src/freq_counter.v $ROOT/src/project.v
    hierarchy -top tt_um_ajhendel_evofab
    synth -top tt_um_ajhendel_evofab -flatten
    write_json $OUT/n$N.json
    tee -o $OUT/n$N.txt stat
  " > "$OUT/n$N.log" 2>&1 || { echo "yosys failed for N=$N, see $OUT/n$N.log"; exit 1; }
done

python3 - "$OUT" <<'PY'
import json, re, sys, os
out = sys.argv[1]
rows = []
for n in (1, 2, 4, 8, 16):
    txt = open(os.path.join(out, f"n{n}.txt")).read()
    cells = {}
    for line in txt.splitlines():
        m = re.match(r"\s+(\d+)\s+(\S+)\s*$", line)
        if m:
            cells[m.group(2)] = int(m.group(1))
    sky = {k: v for k, v in cells.items() if k.startswith("sky130_")}
    other = {k: v for k, v in cells.items() if k.startswith("$_")}
    rows.append((n, sum(sky.values()), sum(other.values()), sky))

print(f"{'N_SITES':>8} {'hand cells':>11} {'generic':>9} {'total':>7}")
for n, s, o, _ in rows:
    print(f"{n:>8} {s:>11} {o:>9} {s+o:>7}")

# Slope between the two largest builds is the marginal cost per site.
(n1, s1, o1, _), (n2, s2, o2, _) = rows[-2], rows[-1]
mh = (s2 - s1) / (n2 - n1)
mg = (o2 - o1) / (n2 - n1)
fixed_h = s2 - mh * n2
fixed_g = o2 - mg * n2
print()
print(f"marginal hand cells per site : {mh:.2f}")
print(f"marginal generic cells/site  : {mg:.2f}   (config registers and decode)")
print(f"fixed hand cells             : {fixed_h:.0f}   (calibration strip)")
print(f"fixed generic cells          : {fixed_g:.0f}   (scan, CRC, safety, counters)")
print()
for target in (32, 48, 64):
    print(f"projected total cells at {target:>2} sites: "
          f"{fixed_h + fixed_g + (mh + mg) * target:.0f}")
print()
print("Per-cell breakdown of the hand-instantiated fabric at the largest build:")
for k, v in sorted(rows[-1][3].items(), key=lambda kv: -kv[1]):
    print(f"  {k:<32} {v:>6}")
PY
