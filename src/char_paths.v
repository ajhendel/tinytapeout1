// Fixed, non-oscillating characterization paths. Block C.
//
// WHY THIS BLOCK EXISTS
//
// The calibration strip in src/calib_macro.v is made of ring oscillators, and
// a ring oscillator is the wrong instrument for two of the things this chip
// needs to know. A ring reports an average over millions of transitions, so it
// cannot report a single edge, and it self-heats while it runs, so its own
// measurement changes the thing it measures. Neither problem is fatal for a
// PVT monitor, which is what rings are good at, and both are fatal for a
// reference against which a combinational delay is claimed.
//
// So the chip carries a second, quieter instrument: fixed paths that carry
// exactly one transition per trial, measured by the TDC in src/tdc.v. Nothing
// in this file is configurable except which path is selected, because a
// configurable reference is not a reference.
//
// THE INFERENCE CHAIN THIS BLOCK IS BUILT TO SUPPORT
//
//     individual library cells
//        -> fixed paths of known cells and known loading      (this file)
//        -> configurable sites of the same cells              (fabric_site.v)
//        -> evolved circuits made of those sites
//
// Every step is a claim that the next thing up behaves like the thing below it
// plus something identifiable. Without the middle rung, a disagreement between
// the models and an evolved circuit has nowhere to be localized: it could be
// the cell models, the extraction, the configurability, or the search. With
// it, the disagreement can be attributed.
//
// THE PATH TABLE
//
//   idx  structure                                     what it isolates
//   ---  --------------------------------------------  ----------------------
//     0  inv_1  x8, unloaded                           drive series, reference
//     1  inv_2  x8, unloaded                           drive series
//     2  inv_4  x8, unloaded                           drive series
//     3  inv_8  x8, unloaded                           drive series
//     4  inv_1  x8, one inv_1 sink per stage           load cost at drive 1
//     5  inv_2  x8, one inv_1 sink per stage           load cost at drive 2
//     6  inv_4  x8, one inv_1 sink per stage           load cost at drive 4
//     7  inv_8  x8, one inv_1 sink per stage           load cost at drive 8
//     8  inv_1  x2, unloaded                           depth series
//     9  inv_1  x4, unloaded                           depth series
//    10  inv_1 x16, unloaded                           depth series
//    11  nand2_1 x8                                    cell type, drive 1
//    12  nand2_4 x8                                    cell type, drive 4
//    13  mux4_1 x8                                     the route/function muxes
//    14  drive_node x4, ISOLATE = 1                    the site's output stage
//    15  drive_node x4, ISOLATE = 0                    the same, un-isolated
//
// Paths 0, 8, 9 and 10 are the same cell at four depths. A straight line
// through them gives the per-stage delay AND the fixed offset contributed by
// the launch gate, the sixteen-way select tree and the TDC input. Every other
// path in this file is quoted against that offset rather than pretending it
// does not exist. This is the reason the depth series is four points and not
// two: two points give a slope with no way to check that the relationship is
// linear, and if it is not linear the offset is not a constant and nothing
// else here can be quoted.
//
// Paths 14 and 15 are the matched pair. They differ in exactly one thing,
// whether each drive variant's input is gated by its own enable, and they are
// built from the same module the fabric sites are built from. The cost of
// input isolation is therefore a measurement on this die and not an argument.
//
// EVERY PATH IS NON-INVERTING END TO END, so a rising launch produces a rising
// arrival and the TDC never has to be told which polarity to expect. Every
// depth in the table above is even for that reason. Do not add an odd one.
//
// ONLY THE SELECTED PATH SWITCHES. The launch edge is gated per path by a
// one-hot decode of the select field. This is the same lesson as the drive
// stage: sixteen paths all fed from one launch net would burn sixteen paths'
// worth of current and put fifteen paths' worth of supply disturbance into
// every measurement, which is precisely the confound the measurement exists to
// avoid.

`timescale 1ns / 1ps
`default_nettype none

// -------------------------------------------------------------- inverter chain
module char_inv_chain #(
    parameter integer DRIVE = 1,
    parameter integer DEPTH = 8,   // must be even
    parameter integer LOAD  = 0    // inv_1 sinks hung on every stage output
) (
    input  wire in,
    output wire out
);
  wire [DEPTH:0] n;
  assign n[0] = in;
  genvar i;
  generate
    for (i = 0; i < DEPTH; i = i + 1) begin : stage
      cell_inv #(.DRIVE(DRIVE)) u (.A(n[i]), .Y(n[i+1]));
      if (LOAD != 0) begin : ld
        wire sink;
        cell_inv #(.DRIVE(1)) l (.A(n[i+1]), .Y(sink));
        // Deliberately unused. keep/dont_touch on the wrapper is what stops
        // this being swept away, and the load it presents is the whole point.
        wire unused_sink = sink;
      end
    end
  endgenerate
  assign out = n[DEPTH];
endmodule

// ------------------------------------------------------------------ NAND chain
// B is driven by the path enable rather than by a constant, so the cell is a
// real two-input gate with a real second input net rather than something the
// flow could reason about as an inverter.
module char_nand_chain #(
    parameter integer DRIVE = 1,
    parameter integer DEPTH = 8    // must be even
) (
    input  wire in,
    input  wire en,
    output wire out
);
  wire [DEPTH:0] n;
  assign n[0] = in;
  genvar i;
  generate
    for (i = 0; i < DEPTH; i = i + 1) begin : stage
      cell_nand2 #(.DRIVE(DRIVE)) u (.A(n[i]), .B(en), .Y(n[i+1]));
    end
  endgenerate
  assign out = n[DEPTH];
endmodule

// ------------------------------------------------------------------- mux chain
// A0 carries the signal and the other three inputs are static, which is how
// the route and function muxes inside a site are actually used. Tying all four
// inputs to the same net would have put four times the input capacitance on
// the driver and measured a mux nobody builds.
module char_mux_chain #(
    parameter integer DEPTH = 8    // must be even; mux4 is non-inverting
) (
    input  wire in,
    input  wire en,
    output wire out
);
  wire [DEPTH:0] n;
  assign n[0] = in;
  genvar i;
  generate
    for (i = 0; i < DEPTH; i = i + 1) begin : stage
      cell_mux4 u (.A0(n[i]), .A1(en), .A2(1'b0), .A3(1'b1),
                   .S0(1'b0), .S1(1'b0), .X(n[i+1]));
    end
  endgenerate
  assign out = n[DEPTH];
endmodule

// --------------------------------------------------------- drive-stage replica
// Four site output stages in series, built from the same drive_node module the
// fabric uses. DEPTH is even so the chain is non-inverting; drive_node inverts.
module char_drive_chain #(
    parameter integer ISOLATE = 1,
    parameter integer DEPTH   = 4   // must be even
) (
    input  wire       in,
    input  wire [3:0] den,
    output wire       out
);
  wire [DEPTH:0] n;
  assign n[0] = in;
  genvar i;
  generate
    for (i = 0; i < DEPTH; i = i + 1) begin : stage
      drive_node #(.ISOLATE(ISOLATE)) u (.d(n[i]), .den(den), .z(n[i+1]));
    end
  endgenerate
  assign out = n[DEPTH];
endmodule

// --------------------------------------------------------------------- block C
module char_paths (
    input  wire       launch,       // one rising edge per trial, clk domain
    input  wire [3:0] sel,          // which path is measured
    input  wire [1:0] drive_sel,    // drive variant for paths 14 and 15
    output wire       char_out
);

  // One-hot decode. Ordinary synthesized logic on purpose: it is static during
  // a measurement and is not in the timed path. The GATE it drives is a real
  // cell, because that one IS in the path.
  wire [15:0] en;
  assign en = 16'd1 << sel;

  // Balanced launch distribution, built by hand for the same reason as the
  // TDC's sampling tree in src/tdc.v. Sixteen launch gates on one net would be
  // buffered by the resizer into a tree of whatever shape satisfied max fanout,
  // and paths on a deeper branch would launch later than paths on a shallower
  // one. That difference is a per-path offset, and a per-path offset is exactly
  // what the depth series CANNOT extract: the series recovers a COMMON offset
  // by fitting a line through four different paths, so an offset that varies
  // between those four paths lands in the fitted slope and corrupts the
  // per-stage delay itself.
  //
  // One root, four branches, four launch gates each. Every path is the same
  // number of gates from the launch register. Wire delay is still the placer's
  // decision and is still in the residual; this removes the part that was ours.
  wire lroot;
  cell_buf #(.DRIVE(4)) lrt (.A(launch), .X(lroot));

  wire [3:0] lbr;
  genvar j;
  generate
    for (j = 0; j < 4; j = j + 1) begin : lbuf
      cell_buf #(.DRIVE(2)) u (.A(lroot), .X(lbr[j]));
    end
  endgenerate

  // Per-path launch gate. Only the selected path sees an edge.
  wire [15:0] g;
  genvar k;
  generate
    for (k = 0; k < 16; k = k + 1) begin : gate
      cell_and2 u (.A(lbr[k/4]), .B(en[k]), .X(g[k]));
    end
  endgenerate

  // Drive-variant one-hot for the two replica paths. Constant-free: every bit
  // is a decoded net, so no tri-state enable in the replicas is constant
  // folded and tools/check_netlist.py can still do its job.
  wire [3:0] den;
  assign den[0] = (drive_sel == 2'd0);
  assign den[1] = (drive_sel == 2'd1);
  assign den[2] = (drive_sel == 2'd2);
  assign den[3] = (drive_sel == 2'd3);

  wire [15:0] o;

  char_inv_chain #(.DRIVE(1), .DEPTH(8),  .LOAD(0)) p0  (.in(g[0]),  .out(o[0]));
  char_inv_chain #(.DRIVE(2), .DEPTH(8),  .LOAD(0)) p1  (.in(g[1]),  .out(o[1]));
  char_inv_chain #(.DRIVE(4), .DEPTH(8),  .LOAD(0)) p2  (.in(g[2]),  .out(o[2]));
  char_inv_chain #(.DRIVE(8), .DEPTH(8),  .LOAD(0)) p3  (.in(g[3]),  .out(o[3]));

  char_inv_chain #(.DRIVE(1), .DEPTH(8),  .LOAD(1)) p4  (.in(g[4]),  .out(o[4]));
  char_inv_chain #(.DRIVE(2), .DEPTH(8),  .LOAD(1)) p5  (.in(g[5]),  .out(o[5]));
  char_inv_chain #(.DRIVE(4), .DEPTH(8),  .LOAD(1)) p6  (.in(g[6]),  .out(o[6]));
  char_inv_chain #(.DRIVE(8), .DEPTH(8),  .LOAD(1)) p7  (.in(g[7]),  .out(o[7]));

  char_inv_chain #(.DRIVE(1), .DEPTH(2),  .LOAD(0)) p8  (.in(g[8]),  .out(o[8]));
  char_inv_chain #(.DRIVE(1), .DEPTH(4),  .LOAD(0)) p9  (.in(g[9]),  .out(o[9]));
  char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(0)) p10 (.in(g[10]), .out(o[10]));

  char_nand_chain #(.DRIVE(1), .DEPTH(8)) p11 (.in(g[11]), .en(en[11]), .out(o[11]));
  char_nand_chain #(.DRIVE(4), .DEPTH(8)) p12 (.in(g[12]), .en(en[12]), .out(o[12]));
  char_mux_chain  #(.DEPTH(8))            p13 (.in(g[13]), .en(en[13]), .out(o[13]));

  char_drive_chain #(.ISOLATE(1), .DEPTH(4)) p14 (.in(g[14]), .den(den), .out(o[14]));
  char_drive_chain #(.ISOLATE(0), .DEPTH(4)) p15 (.in(g[15]), .den(den), .out(o[15]));

  // Sixteen to one, two mux4 levels. The tree is in the measured path and is
  // the same two levels for every path, so it lands in the fixed offset the
  // depth series extracts. It is not subtracted by assumption anywhere.
  wire [3:0] lvl;
  cell_mux4 m0 (.A0(o[0]),  .A1(o[1]),  .A2(o[2]),  .A3(o[3]),
                .S0(sel[0]), .S1(sel[1]), .X(lvl[0]));
  cell_mux4 m1 (.A0(o[4]),  .A1(o[5]),  .A2(o[6]),  .A3(o[7]),
                .S0(sel[0]), .S1(sel[1]), .X(lvl[1]));
  cell_mux4 m2 (.A0(o[8]),  .A1(o[9]),  .A2(o[10]), .A3(o[11]),
                .S0(sel[0]), .S1(sel[1]), .X(lvl[2]));
  cell_mux4 m3 (.A0(o[12]), .A1(o[13]), .A2(o[14]), .A3(o[15]),
                .S0(sel[0]), .S1(sel[1]), .X(lvl[3]));
  cell_mux4 mf (.A0(lvl[0]), .A1(lvl[1]), .A2(lvl[2]), .A3(lvl[3]),
                .S0(sel[2]), .S1(sel[3]), .X(char_out));

endmodule
