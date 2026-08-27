// Hand-instantiated sky130_fd_sc_hd cell wrappers.
//
// Why wrappers exist. The evolvable fabric's whole point is that the genome
// selects the ELECTRICAL realization, so the synthesizer must not be allowed to
// resize, merge or rewrite these cells. Every wrapper carries keep and
// dont_touch, and every wrapper is keep_hierarchy so the boundary survives.
//
// SIM path. When SIM is defined (RTL simulation via test/Makefile) the wrappers
// collapse to behavioral equivalents, because the PDK cell models are not
// available in a plain iverilog run and because the fabric contains a deliberate
// combinational loop that an event simulator cannot settle. Gate-level
// simulation after the GDS build exercises the real cells. This split follows
// the recipe used by the sky130 Tiny Tapeout ring-oscillator projects.
//
// Port names verified against
// github.com/google/skywater-pdk-libs-sky130_fd_sc_hd/cells/<cell>/*.v
//   inv    (A, Y)      nand2 (A, B, Y)   nor2  (A, B, Y)
//   and2   (A, B, X)   or2   (A, B, X)   xor2  (A, B, X)   xnor2 (A, B, Y)
//   mux2   (A0, A1, S, X)                mux4  (A0..A3, S0, S1, X)
//   einvn  (A, TE_B, Z)  tri-state inverter, negative enable
//   ebufn  (A, TE_B, Z)  tri-state buffer,   negative enable
//   buf    (A, X)
//   conb   (HI, LO)

// Explicit timescale. Without one, a module picks up whatever default the
// compiler applies, and a delay written as 5 can land on a completely different
// time base than the testbench driving it. That silently stopped the simulation
// model of the calibration rings from oscillating at all in one harness while
// working in another.
`timescale 1ns / 1ps
`default_nettype none

// SIM PROPAGATION DELAYS
//
// The SIM branches below carry small propagation delays. They are NOT models of
// the cells, no measurement may ever be taken from them, and their absolute
// values mean nothing. They exist for one reason: src/tdc.v measures a delay by
// racing an edge down a delay line, and with zero-delay primitives every
// configuration produces the identical capture, so the converter's plumbing,
// its tap ordering and its select decode would all be untestable before
// silicon. With delays, a wrong tap order or an unreached path fails a test.
//
// The tri-state inverter is deliberately LEFT at zero delay. Several of them
// resolve onto one node, and giving a resolved multi-driver net a delay invites
// simulator-only contention transients that would be indistinguishable from a
// real design fault. The one thing in this file that must not produce
// mysterious X values is the thing the whole fabric is built from.
//
// Gate-level simulation after the GDS build uses the real cell models.

// ---------------------------------------------------------------- inverter
module cell_inv #(parameter DRIVE = 1) (input wire A, output wire Y);
`ifdef SIM
  // SIM carries a small propagation delay. It is NOT a model of the cell and
  // no measurement may be taken from it. It exists because the TDC in
  // src/tdc.v measures a delay, and a delay line built from zero-delay
  // primitives captures the same value for every configuration, so the TDC's
  // plumbing would be untestable and a broken tap ordering would look correct.
  // The numbers are ordered the way the real variants are ordered and nothing
  // more. Gate-level simulation after the GDS build uses the real cells.
  localparam real SIM_TD =
      (DRIVE == 1) ? 0.040 : (DRIVE == 2) ? 0.032 : (DRIVE == 4) ? 0.028 : 0.026;
  assign #(SIM_TD) Y = ~A;
`else
  generate
    if (DRIVE == 1) begin : g1
      (* keep, dont_touch *) sky130_fd_sc_hd__inv_1 u (.A(A), .Y(Y));
    end else if (DRIVE == 2) begin : g2
      (* keep, dont_touch *) sky130_fd_sc_hd__inv_2 u (.A(A), .Y(Y));
    end else if (DRIVE == 4) begin : g4
      (* keep, dont_touch *) sky130_fd_sc_hd__inv_4 u (.A(A), .Y(Y));
    end else begin : g8
      (* keep, dont_touch *) sky130_fd_sc_hd__inv_8 u (.A(A), .Y(Y));
    end
  endgenerate
`endif
endmodule

// ------------------------------------------------------------------- buffer
// Used by the TDC delay line in src/tdc.v and nowhere else. A delay line has
// to be non-inverting per stage, because taps of alternating polarity turn the
// thermometer code into something that needs a per-tap polarity table to read,
// and a wrong table is indistinguishable from a broken line.
module cell_buf #(parameter DRIVE = 1) (input wire A, output wire X);
`ifdef SIM
  // See the note on cell_inv. SIM delay, not a cell model.
  localparam real SIM_TD =
      (DRIVE == 1) ? 0.055 : (DRIVE == 2) ? 0.045 : (DRIVE == 4) ? 0.038 : 0.034;
  assign #(SIM_TD) X = A;
`else
  generate
    if (DRIVE == 1) begin : g1
      (* keep, dont_touch *) sky130_fd_sc_hd__buf_1 u (.A(A), .X(X));
    end else if (DRIVE == 2) begin : g2
      (* keep, dont_touch *) sky130_fd_sc_hd__buf_2 u (.A(A), .X(X));
    end else if (DRIVE == 4) begin : g4
      (* keep, dont_touch *) sky130_fd_sc_hd__buf_4 u (.A(A), .X(X));
    end else begin : g8
      (* keep, dont_touch *) sky130_fd_sc_hd__buf_8 u (.A(A), .X(X));
    end
  endgenerate
`endif
endmodule

// ---------------------------------------------- buffer, fixed drive, no generate
// Identical to cell_buf with DRIVE 1 except that it contains no generate block,
// so the flattened instance name of the cell inside is <instance>.u and not
// <instance>.g1.u. That matters for exactly one instance in this design,
// u_mon_iso in src/project.v, whose name src/timing.sdc points at. Going
// through the parameterised wrapper would put the drive variant's generate
// label inside the name, so changing the drive of a timing anchor would move a
// constraint, which is precisely the silent drift the anchor exists to prevent.
module cell_buf_1 (input wire A, output wire X);
`ifdef SIM
  assign #(0.055) X = A;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__buf_1 u (.A(A), .X(X));
`endif
endmodule

// ------------------------------------------------------------- two-input NAND
module cell_nand2 #(parameter DRIVE = 1) (input wire A, input wire B, output wire Y);
`ifdef SIM
  localparam real SIM_TD = (DRIVE == 1) ? 0.045 : (DRIVE == 2) ? 0.036 : 0.031;
  assign #(SIM_TD) Y = ~(A & B);
`else
  generate
    if (DRIVE == 1) begin : g1
      (* keep, dont_touch *) sky130_fd_sc_hd__nand2_1 u (.A(A), .B(B), .Y(Y));
    end else if (DRIVE == 2) begin : g2
      (* keep, dont_touch *) sky130_fd_sc_hd__nand2_2 u (.A(A), .B(B), .Y(Y));
    end else begin : g4
      (* keep, dont_touch *) sky130_fd_sc_hd__nand2_4 u (.A(A), .B(B), .Y(Y));
    end
  endgenerate
`endif
endmodule

module cell_nor2 (input wire A, input wire B, output wire Y);
`ifdef SIM
  assign #(0.042) Y = ~(A | B);
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__nor2_1 u (.A(A), .B(B), .Y(Y));
`endif
endmodule

module cell_and2 (input wire A, input wire B, output wire X);
`ifdef SIM
  assign #(0.060) X = A & B;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__and2_1 u (.A(A), .B(B), .X(X));
`endif
endmodule

module cell_or2 (input wire A, input wire B, output wire X);
`ifdef SIM
  assign #(0.058) X = A | B;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__or2_1 u (.A(A), .B(B), .X(X));
`endif
endmodule

module cell_xor2 (input wire A, input wire B, output wire X);
`ifdef SIM
  assign #(0.075) X = A ^ B;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__xor2_1 u (.A(A), .B(B), .X(X));
`endif
endmodule

module cell_xnor2 (input wire A, input wire B, output wire Y);
`ifdef SIM
  assign #(0.072) Y = ~(A ^ B);
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__xnor2_1 u (.A(A), .B(B), .Y(Y));
`endif
endmodule

// ------------------------------------------------------------------ muxes
module cell_mux2 (input wire A0, input wire A1, input wire S, output wire X);
`ifdef SIM
  assign #(0.070) X = S ? A1 : A0;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__mux2_1 u (.A0(A0), .A1(A1), .S(S), .X(X));
`endif
endmodule

module cell_mux4 (input wire A0, input wire A1, input wire A2, input wire A3,
                  input wire S0, input wire S1, output wire X);
`ifdef SIM
  assign #(0.110) X = S1 ? (S0 ? A3 : A2) : (S0 ? A1 : A0);
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__mux4_1 u
      (.A0(A0), .A1(A1), .A2(A2), .A3(A3), .S0(S0), .S1(S1), .X(X));
`endif
endmodule

// ----------------------------------------------------- tri-state inverter
// This is the site's output driver and the load-ladder element. DRIVE is the
// genome-selected drive variant. TE_B is active low, so EN is inverted here to
// keep the callers readable; the inversion is a real cell and is counted.
module cell_einvn #(parameter DRIVE = 1)
    (input wire A, input wire EN, output wire Z);
`ifdef SIM
  assign Z = EN ? ~A : 1'bz;
`else
  wire te_b;
  cell_inv #(.DRIVE(1)) en_inv (.A(EN), .Y(te_b));
  generate
    if (DRIVE == 1) begin : g1
      (* keep, dont_touch *) sky130_fd_sc_hd__einvn_1 u (.A(A), .TE_B(te_b), .Z(Z));
    end else if (DRIVE == 2) begin : g2
      (* keep, dont_touch *) sky130_fd_sc_hd__einvn_2 u (.A(A), .TE_B(te_b), .Z(Z));
    end else if (DRIVE == 4) begin : g4
      (* keep, dont_touch *) sky130_fd_sc_hd__einvn_4 u (.A(A), .TE_B(te_b), .Z(Z));
    end else begin : g8
      (* keep, dont_touch *) sky130_fd_sc_hd__einvn_8 u (.A(A), .TE_B(te_b), .Z(Z));
    end
  endgenerate
`endif
endmodule
