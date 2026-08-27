// One site of the evolvable electrical-realization fabric.
//
// The genome selects the ELECTRICAL realization, not only the truth table.
// Twelve config bits per site, matching the budget in docs/THROUGHPUT.md.
//
//   cfg[2:0]   function select  (pre-stage function, see table below)
//   cfg[4:3]   drive select     (output stage einvn_1 / _2 / _4 / _8)
//   cfg[6:5]   load ladder      (0 = switch parasitic only, then +1, +2, +4)
//   cfg[9:7]   sabotage mode    (none, stuck0, stuck1, bypassA, bypassB, invert)
//   cfg[11:10] route select     (A input source)
//
// Structure, in order along the path.
//
//   A, B -> function bank -> 8:1 function mux -> sabotage mux -> drive stage
//                                                                    |
//                                                  load ladder ------+-> OUT
//
// Two things about this arrangement are deliberate and load bearing.
//
// 1. The drive stage is LAST. If the drive variants were muxed, the mux output
//    would drive the load and the drive selection would be electrically
//    invisible except as an extra stage delay. Here the four drive variants are
//    tri-state inverters that drive the site output node directly, one-hot, so
//    the selected variant really is what drives the node and the load ladder.
//    The output is therefore the INVERSION of the selected pre-stage function.
//    Function table after the inverting output stage:
//      000 NAND2 -> AND2     001 NOR2  -> OR2      010 XOR2 -> XNOR2
//      011 XNOR2 -> XOR2     100 A     -> NOT A    101 B    -> NOT B
//      110 AND2  -> NAND2    111 OR2   -> NOR2
//
// 2. The load ladder elements hang on the site output node with their inputs
//    permanently connected. Enabling an element does not connect a capacitor,
//    it makes an already-present input switch and drive its own sink. So the
//    disabled state is REDUCED loading, never zero loading, exactly as recorded
//    in PLAN.md section 2. Both states must be characterized. Never describe
//    the ladder-0 state as unloaded.
//
// Drive select is decoded one-hot in hardware so tri-state contention on the
// output node is structurally impossible, not merely avoided by convention.
//
// 3. The drive stage lives in src/drive_node.v, and so does the argument about
//    what the tri-state arrangement does and does not buy. Read it before
//    changing anything here. The short version: putting the variants on the
//    output node settles the OUTPUT side, and says nothing about the input
//    side. ISOLATE controls the input side. Most sites are isolated; a named
//    minority are not, on purpose, so the difference is measurable on the die
//    instead of argued in a comment.

// Explicit timescale. Without one, a module picks up whatever default the
// compiler applies, and a delay written as 5 can land on a completely different
// time base than the testbench driving it. That silently stopped the simulation
// model of the calibration rings from oscillating at all in one harness while
// working in another.
`timescale 1ns / 1ps
`default_nettype none

module fabric_site #(
    // 1 gates each drive variant's input with its own enable, so the three
    // unselected variants do not switch. 0 is the deliberately un-isolated
    // control arrangement. See src/drive_node.v for the full argument and
    // src/char_paths.v paths 14 and 15 for the matched fixed measurement of
    // the difference.
    parameter integer ISOLATE = 1
) (
    input  wire        a_prev,      // output of the previous site in the column
    input  wire        a_pi,        // primary input A
    input  wire        a_fb,        // the enumerated feedback edge
    input  wire        b_in,        // primary input B
    input  wire        inert,       // safety override, forces the site inert
    input  wire [11:0] cfg,
    output wire        out,
    output wire        load_mon     // observable proving the ladder is reached
);

  // ------------------------------------------------------------ route select
  wire a_in;
  cell_mux4 route_mux (
      .A0(a_prev), .A1(a_pi), .A2(a_fb), .A3(1'b1),
      .S0(cfg[10]), .S1(cfg[11]), .X(a_in));

  // ---------------------------------------------------------- function bank
  wire f_nand, f_nor, f_xor, f_xnor, f_and, f_or;
  cell_nand2 #(.DRIVE(1)) u_nand (.A(a_in), .B(b_in), .Y(f_nand));
  cell_nor2               u_nor  (.A(a_in), .B(b_in), .Y(f_nor));
  cell_xor2               u_xor  (.A(a_in), .B(b_in), .X(f_xor));
  cell_xnor2              u_xnor (.A(a_in), .B(b_in), .Y(f_xnor));
  cell_and2               u_and  (.A(a_in), .B(b_in), .X(f_and));
  cell_or2                u_or   (.A(a_in), .B(b_in), .X(f_or));

  wire f_lo, f_hi, f_sel;
  cell_mux4 fmux_lo (.A0(f_nand), .A1(f_nor), .A2(f_xor), .A3(f_xnor),
                     .S0(cfg[0]), .S1(cfg[1]), .X(f_lo));
  cell_mux4 fmux_hi (.A0(a_in),  .A1(b_in),  .A2(f_and), .A3(f_or),
                     .S0(cfg[0]), .S1(cfg[1]), .X(f_hi));
  cell_mux2 fmux     (.A0(f_lo), .A1(f_hi), .S(cfg[2]), .X(f_sel));

  // -------------------------------------------------------------- sabotage
  // Modes 6 and 7 alias to none, so an unprogrammed field is inert.
  //   0 none      1 stuck-at-0   2 stuck-at-1   3 bypass A
  //   4 bypass B  5 invert       6,7 none
  wire       sab_inv;
  wire [1:0] sab_lo_sel = cfg[8:7];
  wire       sab_lo, sab_hi, sab_out;
  cell_inv #(.DRIVE(1)) u_sabinv (.A(f_sel), .Y(sab_inv));
  cell_mux4 sab_lo_mux (.A0(f_sel), .A1(1'b0), .A2(1'b1), .A3(a_in),
                        .S0(sab_lo_sel[0]), .S1(sab_lo_sel[1]), .X(sab_lo));
  cell_mux4 sab_hi_mux (.A0(b_in), .A1(sab_inv), .A2(f_sel), .A3(f_sel),
                        .S0(sab_lo_sel[0]), .S1(sab_lo_sel[1]), .X(sab_hi));
  cell_mux2 sab_mux    (.A0(sab_lo), .A1(sab_hi), .S(cfg[9]), .X(sab_out));

  // ---------------------------------------------------- drive stage, one hot
  // Inert does NOT mean "all enables low". A fully tri-stated node floats, and
  // a floating node on a real die is an undefined input to whatever observes
  // it, plus a crowbar risk in the sinks. Inert instead forces the weakest
  // driver on with a constant input, so the node sits at a known level, exactly
  // one driver is ever active, and contention is structurally impossible rather
  // than merely conventionally avoided.
  wire       live = ~inert;
  wire [3:0] den;
  assign den[0] = (live & ~cfg[4] & ~cfg[3]) | inert;
  assign den[1] =  live & ~cfg[4] &  cfg[3];
  assign den[2] =  live &  cfg[4] & ~cfg[3];
  assign den[3] =  live &  cfg[4] &  cfg[3];

  wire drv_in;
  cell_and2 u_inert_gate (.A(sab_out), .B(live), .X(drv_in));

  drive_node #(.ISOLATE(ISOLATE)) u_drive (.d(drv_in), .den(den), .z(out));

  // ------------------------------------------------------------ load ladder
  // Ladder code 0 enables nothing, 1 enables L1, 2 enables L1+L2, 3 enables all.
  //
  // Every ladder element is a tri-state inverter whose INPUT is permanently on
  // the site output node. Enabling one does not connect a capacitor, it makes an
  // already-connected input drive its own output. So ladder 0 is REDUCED
  // loading and never zero loading, exactly as recorded in PLAN.md section 2,
  // and both states have to be characterized.
  //
  // The permanently enabled keeper is not decoration. Without it, the shared
  // sink node floats whenever the ladder is off, and a floating gate input on a
  // real die is a static-current path, not merely an X in simulation. Every
  // element here inverts the same node, so they can never disagree and the
  // shared node can never see contention.
  wire ld_en1 = live & (cfg[6] | cfg[5]);
  wire ld_en2 = live & cfg[6];
  wire ld_en4 = live & cfg[6] & cfg[5];

  wire sk;
  cell_inv   #(.DRIVE(1))              ld_keep (.A(out), .Y(sk));
  cell_einvn #(.DRIVE(1)) ld1 (.A(out), .EN(ld_en1), .Z(sk));
  cell_einvn #(.DRIVE(2)) ld2 (.A(out), .EN(ld_en2), .Z(sk));
  cell_einvn #(.DRIVE(4)) ld4 (.A(out), .EN(ld_en4), .Z(sk));

  wire sk_buf;
  cell_inv #(.DRIVE(1)) snk (.A(sk), .Y(sk_buf));

  // load_mon witnesses that the ladder field is decoded and that the decode
  // reaches this site. It cannot witness that the enables reach the einvn TE_B
  // pins, because on a correct design every ladder element drives the same
  // logic value; that connection is checked structurally on the synthesized
  // netlist by tools/check_netlist.py, and electrically on the die by the
  // delay difference between ladder 0 and ladder 3.
  wire m1, m2;
  cell_xor2 mon_a (.A(sk_buf), .B(ld_en1), .X(m1));
  cell_xor2 mon_b (.A(m1),     .B(ld_en2), .X(m2));
  cell_xor2 mon_c (.A(m2),     .B(ld_en4), .X(load_mon));

endmodule
