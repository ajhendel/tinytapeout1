#!/usr/bin/env python3
"""Enumerate every Tiny Tapeout project ever taped out and keyword-classify it.

Why this exists. docs/PRIOR_ART.md forbids any novelty sentence until its row is
CLOSED by enumeration rather than by a proxy search. Step 2 of the sweep protocol
is "sweep the Tiny Tapeout project index across all shuttles". This script is that
step, made reproducible, so a later session can re-run it against new shuttles and
see exactly what changed.

Data source is the public Tiny Tapeout index API at https://index.tinytapeout.com/.
The root document lists every shuttle; <shuttle-id>.json lists that shuttle's
projects with title, author, description, tiles, analog pins and repo URL.

Usage
    python3 tools/tt_index_sweep.py --out /tmp/ttsweep          # fetch and report
    python3 tools/tt_index_sweep.py --out /tmp/ttsweep --offline # reuse cache

Note the API rejects the default urllib user agent with HTTP 403, so we set one.
"""

import argparse
import collections
import json
import os
import re
import sys
import urllib.request

ROOT = "https://index.tinytapeout.com/"
UA = "tinytapeout1-prior-art-sweep/1.0 (+https://github.com/ajhendel/tinytapeout1)"

# One regex per prior-art theme. Keys match the row topics in docs/PRIOR_ART.md.
KEYWORDS = {
    "RO": r"ring[ -]?osc|\bRO\b|oscillator",
    "PUF": r"\bpuf\b|unclonable",
    "TRNG": r"\btrng\b|\brng\b|random number|entropy source|true random",
    "EVOLVE": r"evolv|genetic algorithm|evolutionary|darwin|hill.?climb|fitness function",
    "CHARACTERIZE": (r"characteriz|characteris|process monitor|\bPVT\b|corner monitor|"
                     r"silicon valid|model valid|delay measur"),
    "ISING": r"ising|max-?cut|annealer|annealing|qubo|combinatorial optim",
    "PBIT": r"p-?bit|probabilistic bit|stochastic comput|bayesian|boltzmann|gibbs",
    "TDC": r"\btdc\b|time-to-digital|delay line|carry chain|vernier",
    "FAULT": r"fault inject|stuck-?at|sabotage|mutation|fault toleran|\bTMR\b|radiation",
    "RESERVOIR": r"reservoir|neuromorph|spiking|\bSNN\b|memristor",
    "ANALOG": r"analog|opamp|op-amp|\badc\b|\bdac\b|comparator|bandgap|current starv",
    "SELFTEST": r"self-?test|\bBIST\b|scan chain|jtag",
    "AGING": r"temperature sensor|thermal|aging|degradation|\bNBTI\b",
    "DRIVE": (r"drive strength|cell variant|standard cell.{0,20}mux|sizing|"
              r"buffer chain|inverter chain|load(ing)? ladder"),
    "COUPLED": r"coupl",
}


def fetch(url, path, offline):
    if offline or (os.path.exists(path) and os.path.getsize(path) > 100):
        if not os.path.exists(path):
            sys.exit(f"offline but no cache at {path}")
        return json.load(open(path))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    open(path, "wb").write(data)
    return json.loads(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="cache and report directory")
    ap.add_argument("--offline", action="store_true", help="use cached json only")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    root = fetch(ROOT, os.path.join(args.out, "_root.json"), args.offline)
    shuttles = root["shuttles"]

    hits = collections.defaultdict(list)
    total = 0
    per_shuttle = []
    for s in shuttles:
        sid = s["id"]
        doc = fetch(f"{ROOT}{sid}.json", os.path.join(args.out, f"{sid}.json"), args.offline)
        projects = doc.get("projects", [])
        per_shuttle.append((sid, s.get("pdk"), len(projects)))
        for p in projects:
            total += 1
            blob = " ".join(str(p.get(k, "")) for k in
                            ("title", "description", "author", "repo")).lower()
            for theme, rx in KEYWORDS.items():
                if re.search(rx, blob):
                    hits[theme].append((sid, p.get("title", ""), p.get("author", ""),
                                        p.get("repo", ""), p.get("description", "")))

    print(f"index updated {root.get('updated')}")
    print(f"shuttles {len(shuttles)}  projects swept {total}")
    for sid, pdk, n in per_shuttle:
        print(f"  {sid:10s} {str(pdk):16s} {n:5d}")
    for theme in KEYWORDS:
        rows = hits[theme]
        print(f"\n===== {theme}: {len(rows)} hits =====")
        for sid, title, author, repo, desc in rows:
            print(f"  [{sid}] {title} | {author}")
            print(f"        {repo}")
            print(f"        {re.sub(r'[ \t\n]+', ' ', desc)[:300]}")


if __name__ == "__main__":
    main()
