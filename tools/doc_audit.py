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
# Matched as PATH COMPONENTS, not as substrings. ".git" as a substring also
# matches ".github", so the workflows were in scope by intent and out of scope
# in fact: files() returned nothing under .github at all. The artifact
# directories are here because CI downloads a copy of this repository into them
# and the audit then reported the copy.
SKIP = {"sim_build", ".git", "__pycache__", "build", "sweeps",
        "artifacts", "submission", "runs", "node_modules"}
SKIP_FILES = ("tools/doc_audit.py",)

# Retracted claims. Each was written in this repository and then withdrawn, and
# the reason is in HANDOFF.md next to the date it was withdrawn.
# A retracted phrase is allowed where the sentence around it is retracting it
# or citing someone else using it.
#
# THE WINDOW IS THE POINT. This started as a whole-line test and then paragraph
# mode arrived, which quietly turned it into a whole-PARAGRAPH test: measured on
# this repository, the pattern below matches 40 percent of all paragraphs and
# exempted every single paragraph containing a retracted phrase. The rule could
# no longer fire at all. A fresh claim two sentences away from an unrelated
# "not" would have been reported as clean.
#
# So the exemption is searched in a window of ALLOWED_WINDOW characters either
# side of the match, which is about a sentence, and the tool prints how often it
# fires so that it going inert again is visible rather than silent.
# There are TWO reasons a retracted phrase may legitimately appear, and they
# have different scopes, which is why one pattern could not serve both.
#
# A RETRACTION is a property of the sentence: "this is not an Ising machine".
# Searched in a window around the match, because a "not" three sentences away
# is not retracting anything.
#
# A CITATION is a property of the paragraph: a passage whose subject is someone
# else's published work, which this repository is required to enumerate rather
# than avoid mentioning. Searched over the whole paragraph, because the marker
# that makes it a citation (a repository URL, a project name, a pointer to
# docs/PRIOR_ART.md) is often nowhere near the phrase itself.
NEGATION = re.compile(
    r"\bnot\b|\bnever\b|\bnothing\b|retract|withdraw|\bwrong\b|"
    r"no longer|must not|cannot|does not|do not|\bno claim\b", re.I)
CITATION = re.compile(r"github\.com|WobblyBits|prior art|PRIOR_ART|"
                      r"\bet al\b|its own authors", re.I)
NEGATION_WINDOW = 120

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
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for n in sorted(names):
            if not n.endswith(TEXT):
                continue
            p = os.path.join(base, n)
            r = os.path.relpath(p, ROOT).replace(os.sep, "/")
            if r in SKIP_FILES:
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
    exempted = [0]
    scanned = 0

    for rel, path in files():
        scanned += 1
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
                if CITATION.search(line):
                    exempted[0] += len(re.findall(pat, line, re.I))
                    continue
                for m in re.finditer(pat, line, re.I):
                    window = line[max(0, m.start() - NEGATION_WINDOW):
                                  m.end() + NEGATION_WINDOW]
                    if NEGATION.search(window):
                        exempted[0] += 1
                        continue
                    problems.append(f"{rel}:~{i}  retracted phrasing "
                                    f"/{pat}/: {why}\n      {near(line, m)}")
                    break
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

    print(f"scanned {scanned} files; {exempted[0]} retracted phrases exempted "
          f"as citations or retractions")
    if problems:
        print(f"\n{len(problems)} documentation problems:\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print("\nNone of these break a simulation. All of them are what the "
              "next reader will believe.", file=sys.stderr)
        return 1
    print(f"documentation audit clean over {scanned} files, "
          f"{exempted[0]} retracted phrases exempted as citations or "
          f"retractions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
