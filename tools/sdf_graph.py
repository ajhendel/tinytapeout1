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
# Anchored at end of line, because an IOPATH record carries TWO delay lists,
# rise and fall, and each is parenthesised. A pattern that stopped at the first
# balanced-looking close swallowed the rise list and left the fall list without
# its closing paren, so the triple regex below never matched it. Every delay
# this module reported was then the RISE delay, silently, and the rise-against-
# fall column of tools/stop_tree.py read exactly 0.0000 ns at every corner,
# which is what gave it away.
IOPATH = re.compile(r'\(IOPATH\s+(\S+)\s+(\S+)\s+(.*?)\)\s*$', re.M)
INTERCONNECT = re.compile(r'\(INTERCONNECT\s+(\S+)\s+(\S+)\s+(.*?)\)\s*$', re.M)
TRIPLE = re.compile(r'\(([-\d.]*):([-\d.]*):([-\d.]*)\)')


def _unescape(name):
    return name.replace("\\", "").strip()


def _split_pin(raw):
    """`instance.pin` -> the same `instance/pin` form an IOPATH record gives.

    THIS IS THE WHOLE REASON THE FIRST VERSION OF THIS MODULE CONNECTED NOTHING.

    An IOPATH record names its instance and its pins separately, so a pin from
    one is assembled here as `inst` + `/` + `pin`. An INTERCONNECT record names
    both ends as a single string, and OpenSTA joins them with a DOT while
    escaping the dots that are already inside the hierarchical name. So the same
    physical pin arrives as

        u_tdc.samp_rt.genblk1.genblk1.g4.u/X      from IOPATH
        u_tdc\\.samp_rt\\.genblk1\\.genblk1\\.g4\\.u.X    from INTERCONNECT

    Those are different strings, so cell arcs and wire arcs landed in disjoint
    halves of the graph and no path crossed between them. Every search returned
    nothing, and the tools that use this module correctly refused to pass, which
    is the only reason it was found rather than shipped.

    The split has to happen BEFORE unescaping, because after unescaping there is
    no way to tell a separator dot from a dot inside a name.
    """
    for i in range(len(raw) - 1, -1, -1):
        if raw[i] == "." and (i == 0 or raw[i - 1] != "\\"):
            return f"{_unescape(raw[:i])}/{raw[i + 1:].strip()}"
    return _unescape(raw)


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
                a, z = _split_pin(src), _split_pin(dst)
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

    def in_worst(self, pin):
        """(rise, fall) of the SLOWEST route into `pin`, over every driver.

        Not the sole driver. A fabric site's output is a one-hot tri-state node
        with four drive variants on it, so asking for exactly one driver there
        returns nothing and a tool that treats that as "no wire" silently drops
        the routing term. Which is the term that matters: equal logical depth
        already removes the cell contribution's dependence on the selected
        input, and routing is all that is left to put a trend into a fit.

        Returns None only when nothing at all drives the pin, which is a real
        fault and should be reported as one.
        """
        srcs = self.ins.get(pin, {})
        if not srcs:
            return None
        rf = [self.detail.get((a, pin)) for a in srcs]
        rf = [x for x in rf if x]
        if not rf:
            return None
        return max(r for r, _ in rf), max(f for _, f in rf)

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

    def slowest(self, start, stop_at):
        """Longest MAX-delay path from `start` to every pin `stop_at` accepts.

        The capture side of a race has to be taken at its worst, and it is not
        a fixed number of hops: this flow inserts fanout repeaters, so the
        hand-built two level sampling tree came back as root, repeater, branch,
        flop. A tool that assumed the hop count would have found nothing here,
        and one that assumed it loosely would have found the wrong path.

        Terminates because it never expands OUT of a pin `stop_at` accepts, and
        on this design every route into the ring's own cycle passes through a
        flip flop clock pin. Returns {pin: (delay, path)}.
        """
        best = {}
        order = []
        seen = set()

        def visit(node, stack):
            if node in seen or node in stack:
                return
            stack.add(node)
            if not stop_at(node):
                for nxt in self.edges.get(node, {}):
                    visit(nxt, stack)
            stack.discard(node)
            seen.add(node)
            order.append(node)

        visit(start, set())
        dist = {start: (0.0, None)}
        for node in reversed(order):
            if node not in dist or stop_at(node):
                continue
            d, _ = dist[node]
            for nxt, (_lo, hi) in self.edges.get(node, {}).items():
                if nxt not in dist or d + hi > dist[nxt][0]:
                    dist[nxt] = (d + hi, node)
        out = {}
        for node, (d, _) in dist.items():
            if node != start and stop_at(node):
                path, cur = [], node
                while cur is not None:
                    path.append(cur)
                    cur = dist[cur][1]
                out[node] = (d, list(reversed(path)))
        return out

    def distances(self, start):
        """{pin: min delay} from `start` to everything reachable. Dijkstra.

        One pass instead of one search per target, because the race has to be
        asked TAP BY TAP: the kill reaches delay line stage i later than stage
        0, so comparing every sampling flop against stage 0 charges each flop
        with a corruption that cannot reach it yet.
        """
        best = {start: 0.0}
        q = [(0.0, start)]
        while q:
            d, node = heapq.heappop(q)
            if d > best.get(node, float("inf")):
                continue
            for nxt, (lo, _hi) in self.edges.get(node, {}).items():
                nd = d + lo
                if nd < best.get(nxt, float("inf")):
                    best[nxt] = nd
                    heapq.heappush(q, (nd, nxt))
        return best

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
