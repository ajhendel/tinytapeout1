#!/usr/bin/env python3
"""Documents, checked against the design instead of against nobody.

WHY THIS IS A GATE AND NOT A PROOFREAD

Three of the four defects found in this design's reviews were found by reading,
and every one of them had been stated wrongly in a document first. A wrong
number in prose does not fail a test; it becomes what the next reader believes.
The specific ones already found here were a site count that stayed at 24 after
the chip dropped to 20, a duplicated status paragraph carrying two different
timing numbers, arithmetic that did not multiply, a comment about an 84 ns chain
in a design whose chain is shorter, and four claims that overreached.

So the things a machine can check are checked by a machine.

WHAT IS CHECKED

  arithmetic     every "a x b = c" and "a + b = c" written in prose has to be
                 true. This is cheap and it caught one.
  site count     a claim about how many sites the chip HAS must match the RTL.
                 Only claim shapes are matched ("N configurable sites", "ships
                 at N sites"), not every sentence containing a number and the
                 word site, because most of those are measurements of builds at
                 other sizes and are correct.
  retractions    phrases this project has retracted must not come back. Each
                 one is here because it was written, published to the repository
                 and then withdrawn, and the cost of it reappearing is not a
                 typo, it is a claim.
  constants      docs/CONSTANTS.md has to agree with the RTL, via
                 tools/gen_constants.py --check.

WHAT IS NOT CHECKED, DELIBERATELY

Whether a sentence is true. That is what review is for. This tool exists to stop
review from spending its attention on arithmetic.

HANDOFF.md is exempt from the claim checks and not from the arithmetic. It is a
dated log of what was believed on the day, and rewriting it to agree with today
would destroy the only record of what the reviews actually changed. Its entries
are wrong on purpose, in the same way a lab notebook is.

A retracted phrase is allowed on a line that is retracting it or citing someone
else using it, and the marker for that is a negation or a citation in the same
line. That is a heuristic, and a determined sentence can get past it. It is here
to catch the phrase drifting back in through a rewrite, which is how it would
actually happen.

USAGE

    tools/doc_audit.py [--fix-none]
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEXT = (".md", ".v", ".py", ".yaml", ".sdc")
SKIP = ("test/sim_build", ".git", "__pycache__", "build/", "docs/sweeps",
        "tools/doc_audit.py")

# Retracted claims. Each was written in this repository and then withdrawn, and
# the reason is in HANDOFF.md next to the date it was withdrawn.
# A line that negates the phrase, or cites someone else using it, is allowed.
ALLOWED = re.compile(
    r"\bnot\b|\bno\b|\bnever\b|\bnothing\b|retract|withdraw|wrong|"
    r"must not|cannot|does not|do not|stale|prior art|github\.com|"
    r"WobblyBits|doc_audit|\bsaid\b|\bcalled\b", re.I)

# Retracted claims. Each was written in this repository and then withdrawn, and
# the reason is in HANDOFF.md next to the date it was withdrawn.
RETRACTED = [
    (r"switchab\w* capacitance", "the ladder does not switch a capacitance in; "
     "the A inputs are permanently connected. See src/load_ladder.v"),
    (r"selectable capacitance", "same as switchable capacitance"),
    (r"gate deletion", "the sabotage field injects faults at a site OUTPUT; it "
     "does not delete gates"),
    (r"pick your (own )?transistor width", "the fabric selects among "
     "prefabricated drive variants; it does not set a width"),
    (r"\bIsing\b", "the single feedback edge is a feedback edge. There is no "
     "controllable coupling, no phase readout and no locking guarantee"),
    (r"per-block undervolt|independent(ly)? undervolt", "there is one supply "
     "and no per-block control of it"),
    (r"nobody has (ever )?(done|built|tried)", "a novelty sentence needs a "
     "closed row in docs/PRIOR_ART.md, not an adverb"),
    (r"200 configurations? (per|a) second", "withdrawn; see docs/THROUGHPUT.md"),
]

# Only CLAIM shapes. "the 24 site column measured 84 ns" is a measurement of a
# build that existed and is not a claim about this one.
SITE_CLAIM = re.compile(
    r"(\d+)[- ](?:serial )?configurable sites?\b"
    r"|ships? (?:at|with) (\d+)[- ]sites?\b"
    r"|(?:chip|design|fabric) (?:has|carries) (\d+)[- ]sites?\b"
    r"|frozen at (\d+)[- ]sites?\b", re.I)

# HANDOFF.md is a dated log; its entries are wrong on purpose, see the note
# above. docs/PRIOR_ART.md is the file whose job is to name other people's work,
# so a retracted phrase in it is a citation. tools/tt_index_sweep.py holds the
# search keywords that FIND that work.
CLAIM_EXEMPT = ("HANDOFF.md", "docs/PRIOR_ART.md", "tools/tt_index_sweep.py")

# Only whole expressions. Matching a fragment of "48 + 12*20 + 8 = 296" as
# "20 + 8 = 296" reports a correct line as broken, and a checker that cries wolf
# gets switched off.
_LEAD = r"(?<![\w.*+/×x-])"
_TAIL = r"(?![\d.]|\s*[*+/×-]\s*\d)"
ARITH_MUL = re.compile(_LEAD + r"(\d[\d,]*)\s*(?:x|\*|×)\s*(\d[\d,]*)\s*=\s*(\d[\d,]*)" + _TAIL)
ARITH_ADD = re.compile(_LEAD + r"(\d[\d,]*)\s*\+\s*(\d[\d,]*)\s*=\s*(\d[\d,]*)" + _TAIL)


def files():
    for base, dirs, names in os.walk(ROOT):
        rel = os.path.relpath(base, ROOT)
        if any(s.rstrip("/") in rel.replace(os.sep, "/") for s in SKIP):
            dirs[:] = []
            continue
        for n in sorted(names):
            if n.endswith(TEXT):
                p = os.path.join(base, n)
                r = os.path.relpath(p, ROOT)
                if any(s in r for s in SKIP):
                    continue
                yield r, p


def num(s):
    return int(s.replace(",", ""))


def blocks(text):
    """(first line number, one line of text) per paragraph.

    Paragraph and not line. Prose in this repository is hard wrapped at about
    eighty columns, so a claim about the site count routinely straddles a line
    break, and a line based checker walks straight past it. That is not
    hypothetical: "and 24 | configurable sites" sat in docs/EXPERIMENT_MATRIX.md
    through the first version of this tool, which reported the file clean.
    """
    out, cur, start = [], [], 1
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip():
            if not cur:
                start = i
            cur.append(line.strip())
        elif cur:
            out.append((start, " ".join(cur)))
            cur = []
    if cur:
        out.append((start, " ".join(cur)))
    return out


def near(text, m, span=60):
    a = max(0, m.start() - span)
    b = min(len(text), m.end() + span)
    return ("..." if a else "") + text[a:b] + ("..." if b < len(text) else "")


def main():
    n_sites = int(re.search(r"`define N_SITES (\d+)",
                            open(os.path.join(ROOT, "src/project.v")).read()).group(1))
    problems = []

    for rel, path in files():
        text = open(path, errors="replace").read()
        for i, line in blocks(text):
            for a, b, c in ARITH_MUL.findall(line):
                if num(a) * num(b) != num(c):
                    problems.append(f"{rel}:~{i}  {a} x {b} = {c} is "
                                    f"{num(a)*num(b)}")
            for a, b, c in ARITH_ADD.findall(line):
                if num(a) + num(b) != num(c):
                    problems.append(f"{rel}:~{i}  {a} + {b} = {c} is "
                                    f"{num(a)+num(b)}")
            if rel in CLAIM_EXEMPT:
                continue
            for pat, why in RETRACTED:
                if re.search(pat, line, re.I) and not ALLOWED.search(line):
                    m = re.search(pat, line, re.I)
                    problems.append(f"{rel}:~{i}  retracted phrasing "
                                    f"/{pat}/: {why}\n      {near(line, m)}")
            for m in SITE_CLAIM.finditer(line):
                got = next(g for g in m.groups() if g)
                if num(got) != n_sites:
                    problems.append(
                        f"{rel}:~{i}  claims {m.group(0).strip()!r} and the RTL "
                        f"says {n_sites}.\n      {near(line, m)}")

    rc = subprocess.run([sys.executable,
                         os.path.join(ROOT, "tools", "gen_constants.py"),
                         "--check"])
    if rc.returncode != 0:
        problems.append("docs/CONSTANTS.md has drifted; see above")

    if problems:
        print(f"\n{len(problems)} documentation problems:\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print("\nNone of these break a simulation. All of them are what the "
              "next reader will believe.", file=sys.stderr)
        return 1
    print("documentation audit clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
