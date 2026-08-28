sky130 open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b
pin order  sky130_fd_sc_hd__inv_1           A VGND VNB VPB VPWR Y
pin order  sky130_fd_sc_hd__buf_1           A VGND VNB VPB VPWR X
pin order  sky130_fd_sc_hd__einvn_1         A TE_B VGND VNB VPB VPWR Z
pin order  sky130_fd_sc_hd__einvn_2         A TE_B VGND VNB VPB VPWR Z
pin order  sky130_fd_sc_hd__einvn_4         A TE_B VGND VNB VPB VPWR Z
pin order  sky130_fd_sc_hd__inv_2           A VGND VNB VPB VPWR Y
pin order  sky130_fd_sc_hd__inv_4           A VGND VNB VPB VPWR Y
pin order  sky130_fd_sc_hd__inv_8           A VGND VNB VPB VPWR Y
pin order  sky130_fd_sc_hd__inv_16          A VGND VNB VPB VPWR Y

null control: both chains disabled, the delta must be zero
  rise +0.0000 ps, fall +0.0000 ps
  PASS: the two arms are identical when configured identically

Every delta below is for the WHOLE 8 stage chain, not per stage. Per stage is one eighth of it and is in the JSON.

| corner | V | C | off, rise | on, rise | delta rise | delta fall | tap at this corner | taps |
|---|---|---|---|---|---|---|---|---|
| tt | 1.80 | 25 | 1020.3 ps | 1241.0 ps | +220.7 ps | +216.9 ps | 82.0 ps | 2.69 |
| tt | 1.80 | -40 | 1041.4 ps | 1250.8 ps | +209.5 ps | +209.0 ps | 79.9 ps | 2.62 |
| tt | 1.80 | 100 | 1008.3 ps | 1240.6 ps | +232.2 ps | +226.4 ps | 84.2 ps | 2.76 |
| tt | 1.62 | 25 | 1280.1 ps | 1532.9 ps | +252.7 ps | +255.9 ps | 102.3 ps | 2.50 |
| tt | 1.98 | 25 | 860.6 ps | 1060.0 ps | +199.4 ps | +191.7 ps | 69.6 ps | 2.87 |
| ss | 1.80 | 100 | 1541.6 ps | 1857.7 ps | +316.1 ps | +316.4 ps | 122.6 ps | 2.58 |
| ff | 1.80 | -40 | 750.2 ps | 925.8 ps | +175.6 ps | +163.1 ps | 59.8 ps | 2.93 |
| ss | 1.62 | 100 | 1945.3 ps | 2310.0 ps | +364.8 ps | +371.3 ps | 155.7 ps | 2.38 |
| ff | 1.98 | -40 | 641.9 ps | 799.5 ps | +157.6 ps | +144.4 ps | 51.4 ps | 3.07 |

delta, largest         +371.3 ps   (3.07 taps at its own corner)
delta, smallest        +144.4 ps   (2.34 taps at its own corner)
as a fraction of the disabled chain: 18.8% to 24.6%
sign, consistent       yes

The fraction is the load bearing number. A capacitance ratio effect
is scale invariant, so a nearly constant fraction across corners
whose absolute delays span twofold is evidence the mechanism is real
rather than a solver artefact. A floating node artefact would not
track the base delay.

CATEGORY: resolvable measurement. The effect exceeds one tap at every corner simulated, each measured against ITS OWN corner's tap, so a single trial per configuration can read it.

## The four ladder codes, and whether the steps are equal

| code | enables | rise | vs code 0 | step | taps |
|---|---|---|---|---|---|
| 0 | 000 | 1037.0 ps | +0.0 ps | +0.0 ps | 0.00 |
| 1 | 100 | 1125.2 ps | +88.2 ps | +88.2 ps | 1.08 |
| 2 | 110 | 1198.8 ps | +161.8 ps | +73.6 ps | 1.97 |
| 3 | 111 | 1258.7 ps | +221.7 ps | +59.8 ps | 2.70 |

The three steps are +88.2, +73.6 and +59.8 ps. Equal steps would mean the ladder does behave as added unit loads after all, which src/load_ladder.v says it does not; unequal steps are the prediction and the SHAPE of the inequality is the result.

## Which of the two mechanisms is doing the work

src/load_ladder.v names two. (a) The gate to source capacitance
faces a rail when enabled and a floating node when disabled.
(b) Enabling also makes the element drive the shared sink, so
the sink moves faster and the Miller current back through the
gate to drain capacitance rises.

Strengthening the keeper makes the sink's edge rate its own
business, so enabling the ladder barely changes it and (b)
collapses. What survives at a strong keeper is (a). One sweep,
both mechanisms, no new topology.

| keeper | delta rise | delta fall | attributed |
|---|---|---|---|
| inv_1 | +220.7 ps | +216.9 ps | both (a) and (b) |
| inv_2 | +134.7 ps | +122.2 ps |  |
| inv_4 | +90.0 ps | +72.6 ps |  |
| inv_8 | +65.6 ps | +44.6 ps |  |
| inv_16 | +35.9 ps | +24.4 ps | mostly (a) |

mechanism (a), the gate to source term: about +35.9 ps
mechanism (b), the Miller term:         about +184.8 ps

If the asymptote is near zero the effect is all Miller and the
gate to source half of the comment in src/load_ladder.v is
wrong. If it is near the whole delta the Miller half is wrong.
Either way the comment gets corrected rather than defended.

wrote spice_ladder.json
