#!/usr/bin/env python3
"""A timing graph out of an SDF, shared by the tools that ask races questions.

WHY A GRAPH AND NOT A GREP

tools/tdc_range.py sums named cells, because the things it measures are chains
of cells we instantiated by hand and can name. The two questions this module
serves are not like that. Both of them cross logic the flow synthesised and
named itself: the flip flop that holds the ring kill, the inverter and the AND
that stand between it and the ring, the sampling flip flops at the ends of the
tree. None of those have names we chose, and matching on names the tool did not
promise to keep is how a check quietly stops checking.

So the SDF is read as what it is, a graph of pins. IOPATH records are edges
inside a cell, INTERCONNECT records are edges between them, and a path through
the design is a path through the graph. Then the question "does the capture beat
the kill" becomes a shortest path against a longest path, which is a question
that does not care what anything is called.

The delays are triples, min:typ:max. Both bounds are kept, because a race is the
only kind of question where using the same number for both sides is wrong: the
slow side has to be taken slow and the fast side fast, or the margin reported is
one that no die has to honour.
"""

import heapq
import re

CELL = re.compile(r'\(CELL\s*\(CELLTYPE\s*"([^"]+)"\)\s*\(INSTANCE\s*([^)]*)\)(.*?)\n\s*\)\n',
                  re.S)
IOPATH = re.compile(r'\(IOPATH\s+(\S+)\s+(\S+)\s+([^)]*\)[^)]*)\)')
INTERCONNECT = re.compile(r'\(INTERCONNECT\s+(\S+)\s+(\S+)\s+(.*?)\)\s*$', re.M)
TRIPLE = re.compile(r'\(([-\d.]*):([-\d.]*):([-\d.]*)\)')


def _unescape(name):
    return name.replace("\\", "").strip()


def _triples(body):
    """Every triple in the record, in order. SDF writes rise first, then fall."""
    out = []
    for m in TRIPLE.finditer(body):
        vals = [abs(float(g)) for g in m.groups() if g not in ("", None)]
        if vals:
            out.append((min(vals), max(vals)))
    return out


def _bounds(body):
    """(min, max) over every number in every triple in this record, in ns.

    Rise and fall are separate triples and either can be the one that matters,
    so both are folded in. Empty fields, which SDF allows, are skipped rather
    than read as zero.
    """
    vals = []
    for m in TRIPLE.finditer(body):
        for g in m.groups():
            if g not in ("", None):
                vals.append(abs(float(g)))
    if not vals:
        return None
    return min(vals), max(vals)


class SdfGraph:
    """Pins as nodes, IOPATH and INTERCONNECT as edges."""

    def __init__(self, text):
        self.edges = {}          # src pin -> {dst pin: (min, max)}
        self.ins = {}            # dst pin -> {src pin: (min, max)}
        # (src, dst) -> (rise max, fall max). Kept apart from `edges` because a
        # race cares about the worst transition and a systematic offset study
        # cares about which transition it was; folding them loses that.
        self.detail = {}
        self.cells = {}          # instance -> celltype
        self.n_iopath = 0
        self.n_interconnect = 0
        for celltype, inst, body in CELL.findall(text):
            inst = _unescape(inst)
            if inst:
                self.cells[inst] = celltype
            for frm, to, rec in IOPATH.findall(body):
                b = _bounds(rec)
                if b is None:
                    continue
                # An IOPATH edge is only meaningful attached to an instance.
                a, z = f"{inst}/{_unescape(frm)}", f"{inst}/{_unescape(to)}"
                self._add(a, z, b)
                self._detail(a, z, _triples(rec))
                self.n_iopath += 1
            for src, dst, rec in INTERCONNECT.findall(body):
                b = _bounds(rec)
                if b is None:
                    continue
                a, z = _unescape(src), _unescape(dst)
                self._add(a, z, b)
                self._detail(a, z, _triples(rec))
                self.n_interconnect += 1

    def _add(self, a, b, w):
        cur = self.edges.setdefault(a, {}).get(b)
        if cur is None:
            self.edges[a][b] = w
        else:
            self.edges[a][b] = (min(cur[0], w[0]), max(cur[1], w[1]))
        self.ins.setdefault(b, {})[a] = self.edges[a][b]

    def _detail(self, a, b, triples):
        if not triples:
            return
        rise = triples[0][1]
        fall = triples[1][1] if len(triples) > 1 else rise
        cur = self.detail.get((a, b))
        if cur is None:
            self.detail[(a, b)] = (rise, fall)
        else:
            self.detail[(a, b)] = (max(cur[0], rise), max(cur[1], fall))

    def edge(self, a, b):
        """(rise max, fall max) for one edge, or None."""
        return self.detail.get((a, b))

    def sole_driver(self, pin):
        """The one pin that drives `pin`, or None if there is not exactly one."""
        srcs = self.ins.get(pin, {})
        if len(srcs) != 1:
            return None
        return next(iter(srcs))

    # ------------------------------------------------------------- queries
    def pins(self, *needles):
        """Every pin whose name contains all of the needles."""
        seen = set()
        for a, outs in self.edges.items():
            for p in (a, *outs):
                if all(n in p for n in needles):
                    seen.add(p)
        return sorted(seen)

    def fastest(self, start, is_target):
        """Shortest MIN-delay path from `start` to any pin `is_target` accepts.

        Dijkstra, so the ring's own loop is harmless: the search reaches the
        target and stops rather than going round.

        Returns (delay, path) or (None, None).
        """
        best = {start: 0.0}
        prev = {}
        q = [(0.0, start)]
        while q:
            d, node = heapq.heappop(q)
            if d > best.get(node, float("inf")):
                continue
            if node != start and is_target(node):
                path, cur = [], node
                while cur is not None:
                    path.append(cur)
                    cur = prev.get(cur)
                return d, list(reversed(path))
            for nxt, (lo, _hi) in self.edges.get(node, {}).items():
                nd = d + lo
                if nd < best.get(nxt, float("inf")):
                    best[nxt] = nd
                    prev[nxt] = node
                    heapq.heappush(q, (nd, nxt))
        return None, None

    def hop_max(self, src, dst):
        e = self.edges.get(src, {}).get(dst)
        return None if e is None else e[1]

    def out_max(self, src, filt=lambda p: True):
        """Worst single hop out of `src` to a pin the filter accepts."""
        outs = [(hi, p) for p, (_lo, hi) in self.edges.get(src, {}).items()
                if filt(p)]
        if not outs:
            return None, None
        hi, p = max(outs)
        return hi, p


def load(path):
    with open(path, errors="replace") as fh:
        return SdfGraph(fh.read())
