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
import subprocess
import sys
import textwrap

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools")


def _cell(celltype, inst, records):
    body = "\n".join(f"      {r}" for r in records)
    return (f'  (CELL (CELLTYPE "{celltype}")\n'
            f'    (INSTANCE {inst})\n'
            f'    (DELAY (ABSOLUTE\n{body}\n    ))\n  )\n')


def _iopath(frm, to, d):
    return f"(IOPATH {frm} {to} ({d}:{d}:{d}) ({d}:{d}:{d}))"


def _ic(src, dst, d):
    return f"(INTERCONNECT {src} {dst} ({d}:{d}:{d}) ({d}:{d}:{d}))"


def write_sdf(path, *, kill_flop_cq=0.30, guard_buffers=True, taps=4,
              branches=2, per_branch=2, branch_ic=0.02):
    """A miniature of src/tdc.v: a sampling tree, a kill path and a ring.

    Numbers are round so the expected answer can be worked out on paper.
    Capture is 0.10 + 0.02 + 0.08 + 0.02 = 0.22 ns from the root output.
    Kill is 0.02 + kill_flop_cq + the guard buffers + the NAND + stage 0.
    """
    cells = []
    ics = []

    root = "u_tdc.samp_rt.g4.u"
    cells.append(_cell("sky130_fd_sc_hd__buf_4", root,
                       [_iopath("A", "X", 0.10)]))

    clk_pins = []
    for b in range(branches):
        bi = f"u_tdc.sampbuf\\[{b}\\].u.g2.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_2", bi,
                           [_iopath("A", "X", 0.08)]))
        ics.append(_ic(f"{root}/X", f"{bi}/A", 0.02))
        for f in range(per_branch):
            flop = f"_1{b}{f}_"
            cells.append(_cell("sky130_fd_sc_hd__dfxtp_1", flop,
                               [_iopath("CLK", "Q", 0.25)]))
            ics.append(_ic(f"{bi}/X", f"{flop}/CLK", branch_ic))
            clk_pins.append(f"{flop}/CLK")

    # the ring kill: a flop clocked by the same root, then the guard buffers,
    # then an inverter and an AND the flow named itself, then the ring NAND
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

    nand = "u_tdc.ring_close.g2.u"
    cells.append(_cell("sky130_fd_sc_hd__nand2_2", nand,
                       [_iopath("A", "Y", 0.07), _iopath("B", "Y", 0.07)]))
    ics.append(_ic("_202_/X", f"{nand}/A", 0.02))

    prev = f"{nand}/Y"
    for t in range(taps):
        di = f"u_tdc.dl\\[{t}\\].u.g1.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_1", di,
                           [_iopath("A", "X", 0.12)]))
        ics.append(_ic(prev, f"{di}/A", 0.02))
        prev = f"{di}/X"
    ics.append(_ic(prev, f"{nand}/B", 0.02))          # close the ring

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
    r = run("tdc_race.py", sdf)
    assert r.returncode == 0, r.stdout + r.stderr
    # capture: 0.02 + 0.08 + 0.02 = 0.12 from the root output
    assert "0.1200 ns" in r.stdout, r.stdout
    # kill: 0.02 + 0.30 + 2*(0.02+0.12) + 0.02+0.06 + 0.02+0.09 + 0.02+0.07
    #       + 0.02+0.12 = 1.02
    assert "1.0200 ns" in r.stdout, r.stdout
    assert "MARGIN                +0.8500" in r.stdout, r.stdout


def test_the_race_tool_fails_when_the_kill_gets_there_first(tmp_path):
    """Sabotage: an instant kill flop, no guard buffers, and a sampling tree
    whose branch routing is long. That last one is the realistic version of this
    failure: the tree is balanced in CELLS by construction, and nothing in the
    design controls how far the placer puts the flip flops from their buffer."""
    (tmp_path / "typ").mkdir()
    sdf = write_sdf(str(tmp_path / "typ" / "x.sdf"),
                    kill_flop_cq=0.01, guard_buffers=False, branch_ic=0.60)
    r = run("tdc_race.py", sdf)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stderr


def test_the_race_tool_fails_when_the_sampling_tree_is_gone(tmp_path):
    (tmp_path / "typ").mkdir()
    sdf = write_sdf(str(tmp_path / "typ" / "x.sdf"))
    text = open(sdf).read().replace("sampbuf", "somethingelse")
    open(sdf, "w").write(text)
    r = run("tdc_race.py", sdf)
    assert r.returncode == 1
    assert "sampling tree" in r.stderr


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
        di = f"u_tdc.dl\\[{t}\\].u.g1.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_1", di,
                           [_iopath("A", "X", 0.12)]))
        ics.append(_ic(prev, f"{di}/A", 0.01))
        prev = f"{di}/X"

    n_l1 = (sites + 3) // 4
    for k in range(n_l1):
        inst = f"tapl1\\[{k}\\].u.u"
        cells.append(_cell("sky130_fd_sc_hd__mux4_1", inst,
                           [_iopath(f"A{m}", "X", 0.11) for m in range(4)]))
        for m in range(4):
            t = 4 * k + m
            ics.append(_ic(f"sites\\[{t}\\].u_site.u_drive.drv1.g1.u/Z",
                           f"{inst}/A{m}", base + trend * t))
    n_l2 = (n_l1 + 3) // 4
    for j in range(n_l2):
        inst = f"tapl2\\[{j}\\].u.u"
        cells.append(_cell("sky130_fd_sc_hd__mux4_1", inst,
                           [_iopath(f"A{i}", "X", 0.11) for i in range(4)]))
        for i in range(4):
            k = 4 * j + i
            if k < n_l1:
                ics.append(_ic(f"tapl1\\[{k}\\].u.u/X", f"{inst}/A{i}", 0.02))
    cells.append(_cell("sky130_fd_sc_hd__mux2_1", "tapl3.u",
                       [_iopath("A0", "X", 0.09), _iopath("A1", "X", 0.09)]))
    for j in range(min(2, n_l2)):
        ics.append(_ic(f"tapl2\\[{j}\\].u.u/X", f"tapl3.u/A{j}", 0.02))

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
        di = f"u_tdc.dl\\[{t}\\].u.g1.u"
        cells.append(_cell("sky130_fd_sc_hd__buf_1", di,
                           [_iopath("A", "X", 0.08)]))
        ics.append(_ic(prev, f"{di}/A", 0.004))
        prev = f"{di}/X"

    # the fixed launch and merge overhead the generator charges to every path
    for inst in ("u_char.lrt.g4.u", "u_char.lbuf\\[0\\].u.g2.u",
                 "u_char.gate\\[0\\].u.u", "u_char.merge\\[0\\].u.g4.u",
                 "u_char.merge_out.g2.u"):
        cells.append(_cell("sky130_fd_sc_hd__buf_2", inst,
                           [_iopath("A", "X", 0.06)]))

    depths = {"inv1_d2": 2, "inv1_d4": 4, "inv1_d8": 8, "inv1_d16": 16,
              "load_0": 24, "inv1_d32": 32}
    for i, name in enumerate(tr.CHAR_PATHS):
        n = depths.get(name, 8 + i)
        for k in range(n):
            cells.append(_cell(
                "sky130_fd_sc_hd__inv_1",
                f"u_char.p{i}.stage\\[{k}\\].u.g1.u",
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
