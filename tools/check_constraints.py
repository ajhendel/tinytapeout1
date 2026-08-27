#!/usr/bin/env python3
"""Check that src/timing.sdc's false paths still point at the fabric pins.

src/timing.sdc declares specific ui_in and uo_out indices asynchronous because
of what is wired to them. info.yaml is where those pins are named. Nothing
connects the two files, so remapping a pin in info.yaml would silently leave a
false path on the wrong pin, which is the worst kind of mistake here: the flow
would pass, the chip would come back, and a synchronous path would never have
been timed.

So the connection is made explicit and checked. If you remap a pin, this fails
until you update both.

Usage: tools/check_constraints.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The pin NAMES, from info.yaml, whose paths must be declared asynchronous, and
# the direction the constraint has to take.
ASYNC_FROM = {"FAB_A", "FAB_B", "OBS_SEL"}

# Ports that are not in the info.yaml pinout but are legitimately asynchronous.
# ena is Tiny Tapeout's project-select line and is static while the project is
# in use. rst_n is deliberately absent: reset recovery and removal are real
# checks that the safety controller depends on.
ASYNC_EXTRA_PORTS = {"ena"}
ASYNC_TO = {"FAB_OUT", "OBS_OUT", "LOAD_MON"}

# The one false path in this design that is not anchored to a package pin. The
# fabric reaches the safety monitor through a hand-instantiated buffer whose
# name is the only stable thing the SDC can point at, and the whole arrangement
# is worthless if the two files stop agreeing. See the long note in
# src/timing.sdc. This check exists because the failure is silent: a constraint
# that matches nothing produces no error anywhere.
ANCHOR_INSTANCE = "u_mon_iso"
ANCHOR_PIN = "u_mon_iso.u/X"

# Pin names that must stay in the timed set. These come from registers and the
# safety argument depends on them being checked at speed.
MUST_STAY_TIMED = {"SCAN_OUT", "CRC_OK", "MEAS_BUSY", "TRIPPED", "INERT",
                   "SCAN_EN", "SCAN_IN", "LOAD", "ARM", "CNT_HOLD"}


def load_pinout():
    import yaml
    with open(os.path.join(ROOT, "info.yaml")) as f:
        info = yaml.safe_load(f)
    pins = info["pinout"]
    by_name = {}
    for pin, name in pins.items():
        if name:
            by_name.setdefault(name, []).append(pin)
    return pins, by_name


def check_anchor(problems):
    sdc = open(os.path.join(ROOT, "src", "timing.sdc")).read()
    body = "\n".join(ln for ln in sdc.splitlines()
                     if not ln.lstrip().startswith("#"))
    through = re.findall(
        r"set_false_path\s+-through\s+\[get_pins\s*\{([^}]+)\}\]", body)
    through = {t.strip() for t in through}
    if ANCHOR_PIN not in through:
        problems.append(
            f"src/timing.sdc must cut the fabric-to-safety-monitor path with "
            f"set_false_path -through [get_pins {{{ANCHOR_PIN}}}]; it has "
            f"{sorted(through) or 'no -through constraints'}")

    proj = open(os.path.join(ROOT, "src", "project.v")).read()
    if not re.search(r"\bcell_buf_1\s+" + re.escape(ANCHOR_INSTANCE) + r"\s*\(",
                     proj):
        problems.append(
            f"src/project.v no longer instantiates a cell_buf_1 named "
            f"{ANCHOR_INSTANCE}, so the false path in src/timing.sdc matches "
            f"nothing and the fabric-to-monitor path is silently untimed")
    print(f"timing anchor: -through {ANCHOR_PIN}, instance {ANCHOR_INSTANCE}")


def load_false_paths():
    sdc = open(os.path.join(ROOT, "src", "timing.sdc")).read()
    # Ignore commented lines; a constraint inside the explanation is not a
    # constraint, and treating it as one would make this check pass on a file
    # that constrains nothing.
    lines = [ln for ln in sdc.splitlines() if not ln.lstrip().startswith("#")]
    body = "\n".join(lines)
    froms = set(re.findall(r"set_false_path\s+-from\s+\[get_ports\s*\{([^}]+)\}\]", body))
    tos = set(re.findall(r"set_false_path\s+-to\s+\[get_ports\s*\{([^}]+)\}\]", body))
    return {p.strip() for p in froms}, {p.strip() for p in tos}


def main() -> int:
    pins, by_name = load_pinout()
    froms, tos = load_false_paths()
    problems = []

    def port_for(name):
        got = by_name.get(name)
        if not got:
            problems.append(f"info.yaml has no pin named {name}")
            return None
        if len(got) > 1:
            problems.append(f"info.yaml names {len(got)} pins {name}: {got}")
        # info.yaml writes ui[4]; the SDC and the Verilog write ui_in[4].
        return got[0].replace("ui[", "ui_in[").replace("uo[", "uo_out[") \
                     .replace("uio[", "uio_out[")

    for name in sorted(ASYNC_FROM):
        p = port_for(name)
        if p and p not in froms:
            problems.append(
                f"{name} is on {p} and must have a false path FROM it, "
                f"but src/timing.sdc constrains from {sorted(froms)}")
    for name in sorted(ASYNC_TO):
        p = port_for(name)
        if p and p not in tos:
            problems.append(
                f"{name} is on {p} and must have a false path TO it, "
                f"but src/timing.sdc constrains to {sorted(tos)}")

    for name in sorted(MUST_STAY_TIMED):
        p = port_for(name)
        if p and (p in froms or p in tos):
            problems.append(
                f"{name} on {p} comes from a register and must stay timed, "
                f"but src/timing.sdc declares it asynchronous")

    # Nothing may be declared asynchronous that is not on the list above. An
    # extra false path is how a real timing problem gets waived by accident.
    allowed = ({port_for(n) for n in ASYNC_FROM}
               | {port_for(n) for n in ASYNC_TO}
               | ASYNC_EXTRA_PORTS)
    if "rst_n" in froms or "rst_n" in tos:
        problems.append(
            "rst_n is declared asynchronous; reset recovery and removal are "
            "real checks and the safety controller depends on them")
    for p in sorted(froms | tos):
        if p not in allowed:
            problems.append(
                f"src/timing.sdc declares {p} asynchronous but no fabric pin "
                f"maps to it; an unexplained false path waives real timing")

    check_anchor(problems)

    print(f"false paths from: {sorted(froms)}")
    print(f"false paths to:   {sorted(tos)}")
    if problems:
        print("\nCONSTRAINT CHECK FAILED")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nCONSTRAINT CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
