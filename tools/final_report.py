#!/usr/bin/env python3
"""One report over one build, and one exit code. The submission gate.

WHY ONE REPORT

Everything this repository checks is already checked somewhere: the tests check
the logic, the netlist check checks the structure, the range and race and stop
tree tools check the instrument, the doc audit checks the prose. They run in
different jobs, produce different artifacts, and are read by whoever remembers
to look.

A submission is a single decision taken once, on a single commit, and it should
rest on a single artifact that either says yes or says which gate said no. Not
because the individual checks are insufficient, but because "did all of them run
on THIS commit, against THIS build" is a question nobody can answer by reading
six job logs, and it is the question that matters on the day.

WHAT IT DOES NOT DO

It does not decide the site count, and it does not decide whether to submit.
Those are judgements with money attached. It reports what the build says so that
the judgement is made against the build rather than against a memory of it.

USAGE

    tools/final_report.py <artifact dir> [--sites 20] [--json report.json]

The artifact directory is whatever Tiny Tapeout's CI produced: the GDS logs,
which carry the DEF and the SDF, and the submission, which carries the netlist.
It is searched rather than navigated, because the layout of that directory is
not ours and has changed.
"""

import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")

# name, required, what a failure means
GATES = []


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def pick_metrics(root):
    """LibreLane writes several metrics files; take the fullest one."""
    best, best_n = None, -1
    for p in glob.glob(os.path.join(root, "**", "metrics.json"), recursive=True):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        if isinstance(d, dict) and len(d) > best_n:
            best, best_n = d, len(d)
    return best


# Physical implementation gates, as (metric, test, description). Anything the
# metrics file does not carry is reported as MISSING and fails, because a gate
# that cannot be evaluated has not passed.
PHYSICAL = [
    ("route__drc_errors", lambda v: v == 0, "DRC clean"),
    ("antenna__violating__nets", lambda v: v == 0, "antenna clean"),
    ("timing__setup__ws", lambda v: v >= 0, "setup worst slack nonnegative"),
    ("timing__hold__ws", lambda v: v >= 0, "hold worst slack nonnegative"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifacts")
    ap.add_argument("--sites", type=int, default=int(os.environ.get("N_SITES", 20)))
    ap.add_argument("--util-limit", type=float, default=0.33,
                    help="utilization above which the site count is re-gated")
    ap.add_argument("--json")
    args = ap.parse_args()

    results = []

    def gate(name, ok, detail, required=True):
        results.append(dict(name=name, ok=bool(ok), required=required,
                            detail=detail.strip()))

    print("# Submission report")
    print()
    print(f"artifacts   {args.artifacts}")
    print(f"sites       {args.sites}")
    print()

    # ------------------------------------------------------ source side
    for name, cmd in [
        ("constants agree with the RTL",
         [sys.executable, f"{TOOLS}/gen_constants.py", "--check"]),
        ("documentation audit",
         [sys.executable, f"{TOOLS}/doc_audit.py"]),
        ("timing constraints still point at real pins",
         [sys.executable, f"{TOOLS}/check_constraints.py"]),
    ]:
        rc, out = run(cmd)
        gate(name, rc == 0, out)

    # ------------------------------------------------------ the build
    metrics = pick_metrics(args.artifacts)
    if metrics is None:
        gate("build metrics found", False,
             "no metrics.json anywhere under the artifact directory. Nothing "
             "physical can be gated without it.")
    else:
        for key, test, desc in PHYSICAL:
            if key not in metrics:
                gate(desc, False, f"the build did not report {key}")
            else:
                v = metrics[key]
                gate(desc, test(v), f"{key} = {v}")
        util = metrics.get("design__instance__utilization")
        area = metrics.get("design__instance__area__stdcell")
        if util is None:
            gate("utilization reported", False, "no utilization in the metrics")
        else:
            gate(f"utilization at or below {args.util_limit:.0%}",
                 util <= args.util_limit,
                 f"{util:.4f} of the die, {area} um2 of standard cells. Above "
                 f"the limit the site count is re-gated, NOT the instrument.")

    # ------------------------------------------------------ the netlist
    nl = sorted(glob.glob(os.path.join(args.artifacts, "**", "*.nl.v"),
                          recursive=True)) or \
         sorted(glob.glob(os.path.join(args.artifacts, "**", "*netlist*.v"),
                          recursive=True))
    if nl:
        gate("gate level netlist present", True, nl[-1])
    else:
        gate("gate level netlist present", False,
             "no netlist in the artifacts; the structural check runs in the "
             "test workflow against a yosys build and is not repeated here")

    # ------------------------------------------------------ the instrument
    sdfs = sorted(glob.glob(os.path.join(args.artifacts, "**", "*.sdf"),
                            recursive=True))
    sdfs = [p for p in sdfs if "stapostpnr" in p] or sdfs
    if not sdfs:
        gate("extracted timing found", False,
             "no SDF under the artifact directory. Every instrument gate below "
             "depends on it and none of them ran.")
    else:
        gate("extracted timing found", True,
             f"{len(sdfs)} corners: "
             + ", ".join(sorted({os.path.basename(os.path.dirname(p))
                                 for p in sdfs})))
        for sdf in sdfs:
            corner = os.path.basename(os.path.dirname(sdf))
            for label, cmd in [
                (f"TDC range, {corner}",
                 [sys.executable, f"{TOOLS}/tdc_range.py", sdf]),
                (f"capture beats the ring kill, {corner}",
                 [sys.executable, f"{TOOLS}/tdc_race.py", sdf]),
                (f"stop selector has no trend with tap index, {corner}",
                 [sys.executable, f"{TOOLS}/stop_tree.py", sdf,
                  "--sites", str(args.sites)]),
                (f"thermometer code monotone and bins uniform, {corner}",
                 [sys.executable, f"{TOOLS}/tdc_bins.py", sdf]),
            ]:
                rc, out = run(cmd)
                gate(label, rc == 0, out)

    # ------------------------------------------------------ placement
    defs = sorted(glob.glob(os.path.join(args.artifacts, "**", "*.def"),
                            recursive=True), key=os.path.getsize)
    if defs:
        rc, out = run([sys.executable, f"{TOOLS}/check_placement.py", defs[-1]])
        # A report, not a gate. A clustered placement is a fact about the build
        # that has to be written down, not a reason to refuse the build.
        gate("placement report", rc == 0, out, required=False)
    else:
        gate("placement report", False, "no DEF in the artifacts", required=False)

    # ------------------------------------------------------------ verdict
    print("| gate | required | result |")
    print("|---|---|---|")
    for r in results:
        print(f"| {r['name']} | {'yes' if r['required'] else 'report'} | "
              f"{'pass' if r['ok'] else '**FAIL**'} |")
    print()
    for r in results:
        if not r["ok"] or not r["required"]:
            print(f"### {r['name']}")
            print()
            print("```")
            print(r["detail"][:6000])
            print("```")
            print()

    failed = [r for r in results if r["required"] and not r["ok"]]
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(dict(sites=args.sites, gates=results,
                           failed=[r["name"] for r in failed]), fh, indent=2)

    if failed:
        print(f"**{len(failed)} required gates failed. This build is not a "
              f"submission.**")
        for r in failed:
            print(f"- {r['name']}")
        return 1
    print("**Every required gate passed on this build.** What is left is the "
          "judgement with money attached, which is not this tool's.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
