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
//   conb   (HI, LO)

`default_nettype none

// ---------------------------------------------------------------- inverter
module cell_inv #(parameter DRIVE = 1) (input wire A, output wire Y);
`ifdef SIM
  assign Y = ~A;
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

// ------------------------------------------------------------- two-input NAND
module cell_nand2 #(parameter DRIVE = 1) (input wire A, input wire B, output wire Y);
`ifdef SIM
  assign Y = ~(A & B);
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
  assign Y = ~(A | B);
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__nor2_1 u (.A(A), .B(B), .Y(Y));
`endif
endmodule

module cell_and2 (input wire A, input wire B, output wire X);
`ifdef SIM
  assign X = A & B;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__and2_1 u (.A(A), .B(B), .X(X));
`endif
endmodule

module cell_or2 (input wire A, input wire B, output wire X);
`ifdef SIM
  assign X = A | B;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__or2_1 u (.A(A), .B(B), .X(X));
`endif
endmodule

module cell_xor2 (input wire A, input wire B, output wire X);
`ifdef SIM
  assign X = A ^ B;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__xor2_1 u (.A(A), .B(B), .X(X));
`endif
endmodule

module cell_xnor2 (input wire A, input wire B, output wire Y);
`ifdef SIM
  assign Y = ~(A ^ B);
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__xnor2_1 u (.A(A), .B(B), .Y(Y));
`endif
endmodule

// ------------------------------------------------------------------ muxes
module cell_mux2 (input wire A0, input wire A1, input wire S, output wire X);
`ifdef SIM
  assign X = S ? A1 : A0;
`else
  (* keep, dont_touch *) sky130_fd_sc_hd__mux2_1 u (.A0(A0), .A1(A1), .S(S), .X(X));
`endif
endmodule

module cell_mux4 (input wire A0, input wire A1, input wire A2, input wire A3,
                  input wire S0, input wire S1, output wire X);
`ifdef SIM
  assign X = S1 ? (S0 ? A3 : A2) : (S0 ? A1 : A0);
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
