"""The SDF gate tools, against a synthetic SDF written here on purpose.

WHY SYNTHETIC

These tools only ever see a real SDF inside CI, on a machine that has just spent
half an hour building the design. That is the worst possible place to find out
that a regular expression stopped matching, because the symptom is a check that
finds nothing and says so politely while the build goes green.

So the structures the tools look for are written out here in miniature, with
delays chosen so the right answer is known by hand, and the tools are made to
produce that answer. Then the same structures are broken on purpose and the
tools are made to fail. A gate that has never been seen to fail is not a gate.
"""

import os
import re
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools")


def _esc(inst):
    """Escape a hierarchical instance name the way OpenSTA writes it.

    THE FIXTURE HAS TO USE THE REAL ENCODING OR IT PROVES NOTHING.

    The first version of this file wrote INTERCONNECT endpoints as `inst/pin`,
    which is the form an IOPATH record implies but NOT the form OpenSTA emits.
    It emits `inst.pin`, with every dot already inside the hierarchical name
    escaped as a backslash-dot, and brackets escaped too. Because the fixture
    used a convention nothing else uses, the parser passed every test here and
    connected nothing at all on a real SDF.
    """
    out = inst.replace(".", "\\.").replace("[", "\\[").replace("]", "\\]")
    return out


def _cell(celltype, inst, records):
    body = "\n".join(f"      {r}" for r in records)
    return (f'  (CELL (CELLTYPE "{celltype}")\n'
            f'    (INSTANCE {_esc(inst)})\n'
            f'    (DELAY (ABSOLUTE\n{body}\n    ))\n  )\n')


def _iopath(frm, to, d, fall=None):
    """Rise and fall are DIFFERENT by default, and that is the point.

    The first fixture used the same number for both, so it could not detect that
    the parser was dropping the fall list entirely and reporting every delay as
    the rise delay. A fixture whose two halves are identical cannot catch a bug
    that confuses them.
    """
    f = d * 1.3 if fall is None else fall
    return f"(IOPATH {frm} {to} ({d}:{d}:{d}) ({f}:{f}:{f}))"


def _ic(src, dst, d):
    """src and dst are given as `inst/pin` and written as OpenSTA writes them."""
    def conv(p):
        inst, pin = p.rsplit("/", 1)
        return f"{_esc(inst)}.{pin}"
    f = d * 1.3
    return (f"(INTERCONNECT {conv(src)} {conv(dst)} "
            f"({d}:{d}:{d}) ({f}:{f}:{f}))")


def write_sdf(path, *, kill_flop_cq=0.30, guard_buffers=True,
              branches=2, per_branch=2, branch_ic=0.02, causal_kill=False,
              skew=0.0, skew_branches=()):
    """A miniature of src/tdc.v: a sampling tree, a kill path and a ring.

    Every delay line stage drives the DATA pin of the flip flop that samples it,
    because that is what the race analysis has to follow: the kill reaches stage
    0 long before stage 31, so each stage has to be matched to its own flip flop
    rather than to the worst one anywhere in the tree. An earlier version of
    this fixture left the line and the flops unconnected, and could not exercise
    that at all.

    Numbers are round so the expected answer can be worked out on paper.
    """
    taps = branches * per_branch
    cells = []
    ics = []

    root = "u_tdc.samp_rt.g4.u"
    cells.append(_cell("sky130_fd_sc_hd__buf_4", root,
                       [_iopath("A", "X", 0.10)]))

    # the ring: NAND plus `taps` buffers, closed back on itself
    nand = "u_tdc.ring_close.g2.u"
    cells.append(_cell("sky130_fd_sc_hd__nand2_2", nand,
                       [_iopath("A", "Y", 0.07), _iopath("B", "Y", 0.07)]))
    prev = f"{nand}/Y"
    stage_out = {}
    for t in range(taps):
        di = f"u_tdc.dl[{t}].u.g1.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_1", di,
                           [_iopath("A", "X", 0.12)]))
        ics.append(_ic(prev, f"{di}/A", 0.02))
        prev = f"{di}/X"
        stage_out[t] = prev
    ics.append(_ic(prev, f"{nand}/B", 0.02))          # close the ring

    # the sampling tree, and one flop per tap plus one fired flag per branch
    for b in range(branches):
        bi = f"u_tdc.sampbuf[{b}].u.g2.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_2", bi,
                           [_iopath("A", "X", 0.08)]))
        # `skew` is what an unbalanced repeater looks like in the timing: one
        # branch further from the arrival edge than another. Which branch it
        # lands on decides whether the converter loses resolution or stops
        # being a thermometer code, and the placer picks.
        ics.append(_ic(f"{root}/X", f"{bi}/A",
                       0.02 + (skew if b in skew_branches else 0.0)))
        for f in range(per_branch + 1):
            flop = f"_1{b}{f}_"
            cells.append(_cell("sky130_fd_sc_hd__dfxtp_1", flop,
                               [_iopath("CLK", "Q", 0.25)]))
            ics.append(_ic(f"{bi}/X", f"{flop}/CLK", branch_ic))
            if f < per_branch:                 # the last one is the fired flag
                t = b * per_branch + f
                if t in stage_out:
                    ics.append(_ic(stage_out[t], f"{flop}/D", 0.01))

    # the kill: either its own flop clocked by the root (the old racing
    # arrangement) or driven from the fired flags (the causal one)
    if causal_kill:
        tail_src = f"_1{branches-1}{per_branch}_/Q"
    else:
        cells.append(_cell("sky130_fd_sc_hd__dfxtp_1", "_200_",
                           [_iopath("CLK", "Q", kill_flop_cq)]))
        ics.append(_ic(f"{root}/X", "_200_/CLK", 0.02))
        tail_src = "_200_/Q"
    if guard_buffers:
        for i in (0, 1):
            gi = f"u_tdc.kill_b{i}.g1.u"
            cells.append(_cell("sky130_fd_sc_hd__buf_1", gi,
                               [_iopath("A", "X", 0.12)]))
            ics.append(_ic(tail_src, f"{gi}/A", 0.02))
            tail_src = f"{gi}/X"
    cells.append(_cell("sky130_fd_sc_hd__inv_1", "_201_",
                       [_iopath("A", "Y", 0.06)]))
    ics.append(_ic(tail_src, "_201_/A", 0.02))
    cells.append(_cell("sky130_fd_sc_hd__and2_1", "_202_",
                       [_iopath("A", "X", 0.09)]))
    ics.append(_ic("_201_/Y", "_202_/A", 0.02))
    ics.append(_ic("_202_/X", f"{nand}/A", 0.02))

    top = _cell("tt_um_ajhendel_evofab", "", ics)
    with open(path, "w") as fh:
        fh.write(textwrap.dedent('''\
            (DELAYFILE
              (SDFVERSION "3.0")
              (DESIGN "tt_um_ajhendel_evofab")
              (TIMESCALE 1ns)
            '''))
        fh.write("".join(cells))
        fh.write(top)
        fh.write(")\n")
    return path


def run(tool, *argv):
    return subprocess.run([sys.executable, os.path.join(TOOLS, tool), *argv],
                          capture_output=True, text=True)


def test_the_race_tool_finds_the_two_paths_and_passes(tmp_path):
    (tmp_path / "typ").mkdir()
    sdf = write_sdf(str(tmp_path / "typ" / "x.sdf"))
    # The fixture builds 2 branches of 2 flops, so 4 clock pins in all, which
    # the tool reads as `taps` + one fired flag per branch.
    r = run("tdc_race.py", sdf, "--branches", "2", "--taps", "4")
    assert r.returncode == 0, r.stdout + r.stderr
    # Worked out by hand from the fixture's own delays, which is the point:
    # the capture is taken at MAX, so it uses the fall numbers, which _iopath
    # makes 1.3 times the rise. From the root OUTPUT (the last node the two
    # paths share) that is 1.3 * (0.02 + 0.08 + 0.02) = 0.156.
    assert "0.1560 ns" in r.stdout, r.stdout
    # The kill is taken at MIN, so it uses the rise numbers:
    # 0.02 + 0.30 + 2*(0.02+0.12) + 0.02+0.06 + 0.02+0.09 + 0.02+0.07
    #      + 0.02+0.12 = 1.02
    assert "1.0200 ns" in r.stdout, r.stdout
    assert "MARGIN                +0.8140" in r.stdout, r.stdout
    # and the two sides must be taken from OPPOSITE bounds, or the margin is
    # not a margin. If both used the same bound these would be equal.
    assert "0.1200 ns" not in r.stdout, (
        "the capture was taken at the rise delay, so it is not the worst case")


def test_the_race_tool_fails_when_the_kill_gets_there_first(tmp_path):
    """Sabotage: an instant kill flop, no guard buffers, and a sampling tree
    whose branch routing is long. That last one is the realistic version of this
    failure: the tree is balanced in CELLS by construction, and nothing in the
    design controls how far the placer puts the flip flops from their buffer."""
    (tmp_path / "typ").mkdir()
    sdf = write_sdf(str(tmp_path / "typ" / "x.sdf"),
                    kill_flop_cq=0.01, guard_buffers=False, branch_ic=0.60)
    r = run("tdc_race.py", sdf, "--branches", "2", "--taps", "4")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stderr


def test_the_race_tool_fails_when_the_sampling_tree_is_gone(tmp_path):
    (tmp_path / "typ").mkdir()
    sdf = write_sdf(str(tmp_path / "typ" / "x.sdf"))
    text = open(sdf).read().replace("sampbuf", "somethingelse")
    open(sdf, "w").write(text)
    r = run("tdc_race.py", sdf, "--branches", "2", "--taps", "4")
    assert r.returncode == 1
    assert "sampling tree" in r.stderr or "branch buffers" in r.stderr


def test_the_race_tool_fails_on_a_file_that_is_not_an_sdf(tmp_path):
    p = tmp_path / "not.sdf"
    p.write_text("hello\n")
    r = run("tdc_race.py", str(p))
    assert r.returncode == 2


def write_tap_sdf(path, *, sites=8, base=0.11, trend=0.0, taps=4):
    """A miniature of the per-site stop selector, with a settable trend.

    `trend` is nanoseconds of extra wire per tap index. Zero is the design's
    intent: three cells deep for every input and no systematic dependence on
    which input. Anything else is the failure this gate exists to catch, and it
    is a failure the design cannot prevent, because nothing here places wires.
    """
    cells, ics = [], []
    # a delay line, so the tool has a tap delay to quote the answer against
    prev = "u_tdc.ring_close.g2.u/Y"
    cells.append(_cell("sky130_fd_sc_hd__nand2_2", "u_tdc.ring_close.g2.u",
                       [_iopath("A", "Y", 0.07)]))
    for t in range(taps):
        di = f"u_tdc.dl[{t}].u.g1.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_1", di,
                           [_iopath("A", "X", 0.12)]))
        ics.append(_ic(prev, f"{di}/A", 0.01))
        prev = f"{di}/X"

    n_l1 = (sites + 3) // 4
    for k in range(n_l1):
        inst = f"tapl1[{k}].u.u"
        cells.append(_cell("sky130_fd_sc_hd__mux4_1", inst,
                           [_iopath(f"A{m}", "X", 0.11) for m in range(4)]))
        for m in range(4):
            t = 4 * k + m
            ics.append(_ic(f"sites[{t}].u_site.u_drive.drv1.g1.u/Z",
                           f"{inst}/A{m}", base + trend * t))
    n_l2 = (n_l1 + 3) // 4
    for j in range(n_l2):
        inst = f"tapl2[{j}].u.u"
        cells.append(_cell("sky130_fd_sc_hd__mux4_1", inst,
                           [_iopath(f"A{i}", "X", 0.11) for i in range(4)]))
        for i in range(4):
            k = 4 * j + i
            if k < n_l1:
                ics.append(_ic(f"tapl1[{k}].u.u/X", f"{inst}/A{i}", 0.02))
    cells.append(_cell("sky130_fd_sc_hd__mux2_1", "tapl3.u",
                       [_iopath("A0", "X", 0.09), _iopath("A1", "X", 0.09)]))
    for j in range(min(2, n_l2)):
        ics.append(_ic(f"tapl2[{j}].u.u/X", f"tapl3.u/A{j}", 0.02))

    top = _cell("tt_um_ajhendel_evofab", "", ics)
    with open(path, "w") as fh:
        fh.write('(DELAYFILE\n  (SDFVERSION "3.0")\n  (TIMESCALE 1ns)\n')
        fh.write("".join(cells))
        fh.write(top)
        fh.write(")\n")
    return path


def test_the_stop_tree_tool_passes_a_flat_tree(tmp_path):
    (tmp_path / "typ").mkdir()
    sdf = write_tap_sdf(str(tmp_path / "typ" / "x.sdf"), sites=8, trend=0.0)
    r = run("stop_tree.py", sdf, "--sites", "8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "+0.000 taps/site" in r.stdout, r.stdout
    assert "taps found            8 of 8" in r.stdout


def test_the_stop_tree_tool_fails_a_tree_that_trends_with_the_tap(tmp_path):
    """Sabotage: make the wire to input t grow with t.

    This is the one that matters. Every reading would still be repeatable, the
    per-site series would still be monotone, every test in the repository would
    still pass, and the published per-site cost would be wrong by the trend.
    """
    (tmp_path / "typ").mkdir()
    sdf = write_tap_sdf(str(tmp_path / "typ" / "x.sdf"), sites=8, trend=0.05)
    r = run("stop_tree.py", sdf, "--sites", "8")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "trends" in r.stderr and "taps per site" in r.stderr


def test_the_stop_tree_tool_fails_when_the_tree_is_not_there(tmp_path):
    (tmp_path / "typ").mkdir()
    sdf = write_tap_sdf(str(tmp_path / "typ" / "x.sdf"), sites=8)
    text = open(sdf).read().replace("tapl1", "gone")   # read, THEN truncate
    open(sdf, "w").write(text)
    r = run("stop_tree.py", sdf, "--sites", "8")
    assert r.returncode == 1
    assert "stop selector tree" in r.stderr


def test_prereg_generates_every_file_from_a_build(tmp_path):
    """The pre-registration generator, end to end on a synthetic build.

    It runs once a year, on the submission commit, under time pressure, and its
    output is the thing the whole model-versus-silicon claim rests on. That is
    the worst possible combination for a script nobody has run.
    """
    sys.path.insert(0, TOOLS)
    import tdc_range as tr

    cells, ics = [], []
    prev = "u_tdc.ring_close.g2.u/Y"
    cells.append(_cell("sky130_fd_sc_hd__nand2_2", "u_tdc.ring_close.g2.u",
                       [_iopath("A", "Y", 0.07)]))
    for t in range(32):
        di = f"u_tdc.dl[{t}].u.g1.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_1", di,
                           [_iopath("A", "X", 0.08)]))
        ics.append(_ic(prev, f"{di}/A", 0.004))
        prev = f"{di}/X"

    # the fixed launch and merge overhead the generator charges to every path
    for inst in ("u_char.lrt.g4.u", "u_char.lbuf[0].u.g2.u",
                 "u_char.gate[0].u.u", "u_char.merge[0].u.g4.u",
                 "u_char.merge_out.g2.u"):
        cells.append(_cell("sky130_fd_sc_hd__buf_2", inst,
                           [_iopath("A", "X", 0.06)]))

    from evofab.genome import DEPTH_SERIES
    depths = dict((n, d) for d, n in DEPTH_SERIES)
    depths["load_0"] = 16          # the repeat point, same depth, second name
    for i, name in enumerate(tr.CHAR_PATHS):
        n = depths.get(name, 8 + i)
        for k in range(n):
            cells.append(_cell(
                "sky130_fd_sc_hd__inv_1",
                f"u_char.p{i}.stage[{k}].u.g1.u",
                [_iopath("A", "Y", 0.05 + 0.001 * i)]))

    sdf = tmp_path / "tt" / "x.sdf"
    (tmp_path / "tt").mkdir()
    with open(sdf, "w") as fh:
        fh.write('(DELAYFILE\n  (SDFVERSION "3.0")\n  (TIMESCALE 1ns)\n')
        fh.write("".join(cells))
        fh.write(_cell("tt_um_ajhendel_evofab", "", ics))
        fh.write(")\n")

    out = tmp_path / "gen"
    r = run("prereg.py", str(sdf), "--out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr

    for f in ("tdc.md", "char_paths.md", "depth_series.md",
              "series_and_pairs.md"):
        text = (out / f).read_text()
        assert "Generated by" in text and "Model layer" in text, f
        assert "Falsified by" in text or "Category" in text or "RULES.md" in text, f

    depth = (out / "depth_series.md").read_text()
    assert "per stage delay, the slope" in depth
    assert "worst residual" in depth

    pairs = (out / "series_and_pairs.md").read_text()
    assert "NOT YET RUN" in pairs, (
        "with no SPICE result the ladder row must say so rather than quietly "
        "inheriting the extraction number it cannot use")

    # and with a SPICE result, the category has to be chosen
    import json
    sp = tmp_path / "spice.json"
    sp.write_text(json.dumps({"cases": [
        {"corner": "tt", "vdd": 1.8, "temp": 25,
         "d_rise_ps": 12.0, "d_fall_ps": -9.0}]}))
    r = run("prereg.py", str(sdf), "--out", str(out), "--spice", str(sp))
    assert r.returncode == 0, r.stdout + r.stderr
    pairs = (out / "series_and_pairs.md").read_text()
    assert "Category: upper bound" in pairs, pairs[-1500:]


def test_the_race_tool_fails_when_half_the_tree_was_optimised_away(tmp_path):
    """A smaller tree makes this gate's own margin look BETTER, which is why
    the size has to be gated and not merely printed. With three of four
    branches gone the capture is shorter, the margin is wider, and a tool that
    only measured would report a healthier race on a broken converter."""
    (tmp_path / "typ").mkdir()
    sdf = write_sdf(str(tmp_path / "typ" / "x.sdf"), branches=1, per_branch=2)
    r = run("tdc_race.py", sdf, "--branches", "2", "--taps", "4")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "branch buffers, expected 2" in r.stderr, r.stderr


def test_the_race_tool_fails_when_capture_registers_are_missing(tmp_path):
    (tmp_path / "typ").mkdir()
    sdf = write_sdf(str(tmp_path / "typ" / "x.sdf"), branches=2, per_branch=1)
    r = run("tdc_race.py", sdf, "--branches", "2", "--taps", "4")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "flip flops, expected 6" in r.stderr, r.stderr


def test_the_race_tool_sees_the_causal_kill_as_a_larger_margin(tmp_path):
    """The design change this analysis forced, checked as a change.

    With the kill on its own flip flop clocked by the arrival edge, the two
    paths start together and the margin is whatever the routing happened to
    give. With the kill taken from the branches' own fired flags it cannot
    begin until every branch has clocked, so the margin includes a whole
    clock-to-Q that the racing arrangement did not have.
    """
    (tmp_path / "raced").mkdir()
    (tmp_path / "causal").mkdir()
    # Guard buffers off in BOTH, so the only difference between the two is
    # where the kill is started from.
    raced = write_sdf(str(tmp_path / "raced" / "x.sdf"), kill_flop_cq=0.05,
                      guard_buffers=False, branch_ic=0.35)
    causal = write_sdf(str(tmp_path / "causal" / "x.sdf"), causal_kill=True,
                       guard_buffers=False, branch_ic=0.35)

    def margin(p):
        r = run("tdc_race.py", p, "--branches", "2", "--taps", "4")
        for line in r.stdout.splitlines():
            if line.startswith("MARGIN"):
                return float(line.split()[1])
        raise AssertionError(r.stdout + r.stderr)

    m_raced, m_causal = margin(raced), margin(causal)
    assert m_causal > m_raced, (
        f"the causal kill gave {m_causal:+.4f} ns and the raced one "
        f"{m_raced:+.4f} ns; the change did not buy what it was made for")
    assert m_raced < 0.10, (
        "the raced fixture was supposed to be the tight case and is not, so "
        "this test is not comparing what it says it is")


# ---------------------------------------------------------------- tdc_bins.py
#
# The quantity these three cover is the one that was measured by nothing until
# the build of 2026-08-28 put a 5.08 tap hole in the middle of the converter.
# A tap's threshold is the line delay to it MINUS the sampling delay to it, and
# both halves were being checked separately by tools that never subtracted them.


def test_the_bin_tool_passes_a_balanced_tree(tmp_path):
    sdf = write_sdf(str(tmp_path / "b.sdf"), branches=2, per_branch=2)
    r = run("tdc_bins.py", sdf, "--taps", "4")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_a_late_low_branch_is_a_wide_bin_and_fails(tmp_path):
    # The repeater lands on the LOW half. The code stays monotone and the bin
    # at the branch boundary opens up. This is the arrangement the real build
    # shipped with, and it passed every other gate in the repository.
    sdf = write_sdf(str(tmp_path / "w.sdf"), branches=2, per_branch=2,
                    skew=0.30, skew_branches=(0,))
    r = run("tdc_bins.py", sdf, "--taps", "4")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "nominal taps wide" in r.stderr
    assert "NOT a thermometer code" not in r.stderr


def test_a_late_high_branch_is_not_a_thermometer_code_and_fails(tmp_path):
    # The same repeater, the same delay, the other half. Nothing about the
    # design chooses which of these two happens.
    sdf = write_sdf(str(tmp_path / "n.sdf"), branches=2, per_branch=2,
                    skew=0.30, skew_branches=(1,))
    r = run("tdc_bins.py", sdf, "--taps", "4")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "NOT a thermometer code" in r.stderr


def test_the_bin_tool_fails_on_a_broken_delay_line(tmp_path):
    # A chain the parser cannot walk reports a SHORTER line, which makes every
    # bin look narrower and this gate look better. It has to fail instead.
    sdf = write_sdf(str(tmp_path / "g.sdf"), branches=2, per_branch=2)
    text = open(sdf).read()
    # ESCAPED, the way the fixture writes it. The first version of this line
    # used the unescaped name, matched nothing, and asserted against a file
    # it had not modified.
    text = text.replace("u_tdc\\.dl\\[2\\]", "u_tdc\\.dl\\[9\\]")
    open(sdf, "w").write(text)
    r = run("tdc_bins.py", sdf, "--taps", "4")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stderr


def test_the_bin_tool_fails_when_no_tap_is_sampled(tmp_path):
    # Every flop still there, none of them connected to the line it samples.
    sdf = write_sdf(str(tmp_path / "u.sdf"), branches=2, per_branch=2)
    text = open(sdf).read()
    # The D pin appears as `_100_.D` in an INTERCONNECT record, not `/D`.
    text = re.sub(r'^.*INTERCONNECT.*\.D .*\n', "", text, flags=re.M)
    open(sdf, "w").write(text)
    r = run("tdc_bins.py", sdf, "--taps", "4")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "not sampled" in r.stderr or "no sampling flip flop" in r.stderr


def test_the_bin_tool_fails_on_a_file_that_is_not_an_sdf(tmp_path):
    p = tmp_path / "x.sdf"
    p.write_text("this is not an SDF\n")
    r = run("tdc_bins.py", str(p))
    assert r.returncode == 2


# ------------------------------------------------------------ char_offsets.py

def write_char_sdf(path, *, branch_skew=0.0, skew_branch=4, en_inv_delay=0.05,
                   merge_delay=0.05,
                   drop_root=False, drop_path=None, npaths=20,
                   series=((8, 2), (9, 4), (10, 8), (11, 16), (19, 32))):
    """A miniature of src/char_paths.v: launch tree, chains, one-hot merge.

    The launch tree is the point. Twenty paths hang off five branch buffers,
    four each, and the depth series puts its four short points on branch 2 and
    its 32 stage point on branch 4. `branch_skew` is what a per-branch delay
    difference looks like, and putting it on branch 4 is what moves the SLOPE
    rather than the intercept.
    """
    cells, ics = [], []

    # a delay line, so the tool has a tap to quote against
    for i in range(32):
        cells.append(_cell("sky130_fd_sc_hd__buf_1", f"u_tdc.dl[{i}].u.g1.u",
                           [_iopath("A", "X", 0.10)]))

    # When the root is gone it is gone from the INTERCONNECT records too. An
    # earlier version of this fixture dropped only the CELL, so every record
    # still named the pin, the tool still found it, and the sabotage was inert.
    root = "_merged_away_" if drop_root else "u_char.lrt.g4.u"
    cells.append(_cell("sky130_fd_sc_hd__buf_4", root,
                       [_iopath("A", "X", 0.05)]))
    for j in range(5):
        bi = f"u_char.lbuf[{j}].u.g2.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_2", bi,
                           [_iopath("A", "X", 0.04)]))
        ics.append(_ic(f"{root}/X", f"{bi}/A",
                       0.01 + (branch_skew if j == skew_branch else 0.0)))
    depth = dict(series)
    for k in range(npaths):
        gi = f"u_char.gate[{k}].u.u"
        cells.append(_cell("sky130_fd_sc_hd__and2_1", gi,
                           [_iopath("A", "X", 0.06), _iopath("B", "X", 0.06)]))
        if k != drop_path:
            ics.append(_ic(f"u_char.lbuf[{k // 4}].u.g2.u/X", f"{gi}/A", 0.01))
        for stg in range(depth.get(k, 2)):
            cells.append(_cell("sky130_fd_sc_hd__inv_1",
                               f"u_char.p{k}.stage[{stg}].u.g1.u",
                               [_iopath("A", "Y", 0.03)]))
        # the merge element, and beside it the enable inverter whose /A pin is
        # the trap: a tool that searched for "an /A pin under merge[k]" could
        # pick either.
        # THE ENABLE INVERTER IS EMITTED FIRST, on purpose. The parser keeps
        # insertion order, so a tool that asks for "an /A pin under merge[k]"
        # and takes the first hit gets THIS one. Emitting it second made the
        # trap unreachable and the test inert, which is exactly the failure it
        # was written to catch.
        cells.append(_cell("sky130_fd_sc_hd__inv_1",
                           f"u_char.merge[{k}].u.en_inv.g1.u",
                           [_iopath("A", "Y", en_inv_delay)]))
        mi = f"u_char.merge[{k}].u.g4.u"
        cells.append(_cell("sky130_fd_sc_hd__einvn_4", mi,
                           [_iopath("A", "Z", merge_delay)]))
        ics.append(_ic(f"{mi}/Z", "u_char.merge_out.g2.u/A", 0.02))
    cells.append(_cell("sky130_fd_sc_hd__inv_2", "u_char.merge_out.g2.u",
                       [_iopath("A", "Y", 0.03)]))

    with open(path, "w") as fh:
        fh.write(textwrap.dedent('''\
            (DELAYFILE
              (SDFVERSION "3.0")
              (DESIGN "tt_um_ajhendel_evofab")
              (TIMESCALE 1ns)
            '''))
        fh.write("".join(cells))
        fh.write(_cell("tt_um_ajhendel_evofab", "", ics))
        fh.write(")\n")
    return path


def test_char_offsets_passes_a_balanced_launch_tree(tmp_path):
    sdf = write_char_sdf(str(tmp_path / "c.sdf"))
    r = run("char_offsets.py", sdf)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_a_slow_launch_branch_biases_the_depth_series_slope(tmp_path):
    # Branch 4 carries the 32 stage point and nothing else in the series, so a
    # delay there lands on the longest lever arm. This is the real topology.
    sdf = write_char_sdf(str(tmp_path / "s.sdf"),
                         branch_skew=0.60, skew_branch=4)
    r = run("char_offsets.py", sdf)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "bias the depth series slope" in r.stderr


def test_which_branch_is_slow_flips_the_sign_of_the_bias(tmp_path):
    # Branch 4 carries only the 32 stage point; branch 2 carries the other
    # four. With five points those two are complements, so the same delay on
    # either produces the SAME magnitude and the OPPOSITE sign. Worth pinning
    # because the obvious intuition, that loading the four short points matters
    # less, is wrong, and a tool that reported only a spread would say nothing
    # about the direction the unit moves.
    a = write_char_sdf(str(tmp_path / "a.sdf"), branch_skew=0.60, skew_branch=4)
    b = write_char_sdf(str(tmp_path / "b.sdf"), branch_skew=0.60, skew_branch=2)

    def bias(p):
        out = run("char_offsets.py", p).stdout
        line = [x for x in out.splitlines() if x.startswith("slope bias")][0]
        return float(line.split()[2])

    assert bias(a) > 0 and bias(b) < 0, (bias(a), bias(b))
    assert abs(abs(bias(a)) - abs(bias(b))) < 0.02, (bias(a), bias(b))


def test_char_offsets_does_not_measure_the_enable_inverter(tmp_path):
    # The einvn wrapper has a second /A pin, on its enable inverter, and a tool
    # that asks for "an /A pin under merge[k]" can pick either. Asserting a
    # bound on the answer did not catch it, because picking the wrong pin makes
    # the merge term SHORTER rather than absurd. So the fixture is built twice
    # with the enable inverter at two very different delays: the data path did
    # not move between them, so a tool reading the data path must report the
    # same number, and one reading the enable path cannot.
    def offset(**kw):
        tag = "_".join(f"{k}{v}" for k, v in kw.items())
        sdf = write_char_sdf(str(tmp_path / f"e{tag}.sdf"), **kw)
        r = run("char_offsets.py", sdf)
        assert r.returncode == 0, r.stdout + r.stderr
        line = [x for x in r.stdout.splitlines()
                if x.startswith("per-path offset")][0]
        return float(line.split()[2])

    # Moving the ENABLE inverter must not move the answer.
    assert offset(en_inv_delay=0.05) == offset(en_inv_delay=5.0)
    # Moving the DATA pin must, by exactly its own change. A tool reading the
    # enable pin instead reports the merge element's own delay as zero, so this
    # is the assertion that fails when the wrong pin is picked. Sorted order
    # puts `en_inv` ahead of `g4`, so the wrong pin is the one a first-hit
    # lookup returns.
    a = offset(merge_delay=0.05)
    b = offset(merge_delay=0.40)
    assert abs((b - a) - 0.35 * 1.3 * 1000) < 1.0, (a, b)


def test_char_offsets_fails_without_the_launch_root(tmp_path):
    sdf = write_char_sdf(str(tmp_path / "r.sdf"), drop_root=True)
    r = run("char_offsets.py", sdf)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "launch tree root" in r.stderr


def test_char_offsets_fails_when_a_path_is_unreachable(tmp_path):
    # A path the launch edge cannot reach would otherwise shorten the table and
    # leave the remaining nineteen looking well behaved.
    sdf = write_char_sdf(str(tmp_path / "u.sdf"), drop_path=7)
    r = run("char_offsets.py", sdf)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "not reachable" in r.stderr


# ------------------------------------------------------------- slew_range.py

CHECKS_HEAD = """
===========================================================================
 report_check_types -max_slew -max_cap -max_fanout -violators
============================================================================
======================= {corner} Corner ===================================

max slew

Pin                                   Limit         Slew       Slack
---------------------------------------------------------------------
"""


def write_checks(path, pins, corner="nom_ss_100C_1v60"):
    """A miniature checks.rpt. `pins` is [(name, slew ns)]."""
    body = CHECKS_HEAD.format(corner=corner)
    for name, slew in pins:
        body += (f"{name:<38} {0.75:.6f} {slew:.6f} "
                 f"{0.75 - slew:.6f} (VIOLATED)\n")
    body += "\nmax fanout\n\nNo violations found.\n"
    with open(path, "w") as fh:
        fh.write(body)
    return path


def test_slew_gate_passes_when_measured_nodes_are_inside_the_table(tmp_path):
    rpt = write_checks(str(tmp_path / "checks.rpt"),
                       [("u_char.merge_out.g2.u/A", 1.318),
                        ("sites[12].u_site.route_mux.u/A0", 1.136),
                        ("u_calib.ro5.stage[5].u.drv1.g1.u/Z", 1.008)])
    r = run("slew_range.py", rpt)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_a_control_node_past_the_limit_is_reported_and_not_gated(tmp_path):
    # The rst_n and site `live` distribution chains have gone past 1.5 ns on
    # real builds. Nothing is quoted against them, so they are reported.
    rpt = write_checks(str(tmp_path / "checks.rpt"),
                       [("fanout158/A", 1.617),
                        ("u_char.merge_out.g2.u/A", 1.318)])
    r = run("slew_range.py", rpt)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1.617" in r.stdout


def test_a_measured_node_past_the_limit_fails(tmp_path):
    # The same slew, on a node a delay IS quoted against.
    rpt = write_checks(str(tmp_path / "checks.rpt"),
                       [("u_char.merge_out.g2.u/A", 1.617)])
    r = run("slew_range.py", rpt)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "extrapolation" in r.stderr


def test_the_tdc_is_gated_like_everything_else(tmp_path):
    rpt = write_checks(str(tmp_path / "checks.rpt"),
                       [("u_tdc.dl[7].u.g1.u/X", 1.55)])
    r = run("slew_range.py", rpt)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "TDC" in r.stderr


def test_the_slew_gate_fails_when_it_finds_nothing_to_check(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    r = run("slew_range.py", str(d))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "not asked" in r.stderr


def test_the_slew_gate_does_not_read_the_fanout_section(tmp_path):
    # max fanout follows max slew in the same file and its middle column is a
    # COUNT, not a time. Reading past the section boundary would turn a fanout
    # of 13 into a 13 ns slew and fail every build for the wrong reason.
    rpt = str(tmp_path / "checks.rpt")
    write_checks(rpt, [("u_char.merge_out.g2.u/A", 1.318)])
    with open(rpt, "a") as fh:
        fh.write("u_tdc.dl[0].u.g1.u/X                   10.000000 "
                 "13.000000 -3.000000 (VIOLATED)\n")
    r = run("slew_range.py", rpt)
    assert r.returncode == 0, r.stdout + r.stderr
