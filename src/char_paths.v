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
//     0  inv_1 x12 into a FIXED load                   drive series
//     1  inv_2 x12 into the same fixed load            drive series
//     2  inv_4 x12 into the same fixed load            drive series
//     3  inv_8 x12 into the same fixed load            drive series
//     4  inv_1 x16, 0 sinks per stage                  load series
//     5  inv_1 x16, 1 sink  per stage                  load series
//     6  inv_1 x16, 2 sinks per stage                  load series
//     7  inv_1 x16, 4 sinks per stage                  load series
//     8  inv_1  x2, unloaded                           depth series
//     9  inv_1  x4, unloaded                           depth series
//    10  inv_1  x8, unloaded                           depth series
//    11  inv_1 x16, unloaded                           depth series
//    12  nand2_1 x8                                    cell type, drive 1
//    13  nand2_4 x8                                    cell type, drive 4
//    14  mux4_1 x4                                     the route/function muxes
//    15  drive_node x4, ISOLATE = 1                    the site's output stage
//    16  drive_node x4, ISOLATE = 0                    the same, un-isolated
//    17  inv_1 x8 + load_ladder, enables tied LOW      the ladder mechanism
//    18  inv_1 x8 + load_ladder, enables tied HIGH     the same, other state
//    19  inv_1 x32, unloaded                           depth series, lever arm
//
// THE DRIVE AND LOAD SERIES ARE SHAPED DIFFERENTLY ON PURPOSE, and the reason
// is the single most useful thing extraction told us about this block. A drive
// series has to hold the LOAD fixed while the driver varies, or the driver and
// its load scale together and nothing moves; see char_drive_series below for
// what that mistake measured. A load series has to hold the DRIVER fixed while
// the load varies, which is the plain inverter chain with sinks hung on it.
// They are not the same structure and an earlier version of this file used one
// structure for both.
//
// Paths 8, 9, 10, 11 and 19 are the same cell at five depths, 2, 4, 8, 16 and
// 32, and path 4 adds a sixth at 24. A straight line through them gives the per-stage delay AND the fixed
// offset contributed by the launch gate, the select merge and the TDC input.
// Every other path in this file is quoted against that offset rather than
// pretending it does not exist.
//
// Five points and a 16:1 lever arm, not two points. Two points give a slope
// with no way to check that the relationship is linear, and if it is not linear
// the offset is not a constant and nothing else here can be quoted. The depth
// 32 point was added after the first build's SDF showed that the depth 2 to 16
// series spanned only 0.53 ns, about four taps of the converter, which is a
// thin lever arm for a slope everything else is quoted against.
//
// Paths 17 and 18 are the second matched pair. They are the same inverter chain
// carrying the same load ladder from src/load_ladder.v, differing ONLY in
// whether its enables are tied high or low. Their difference is the ladder
// mechanism with the configurable fabric removed from around it. Liberty
// predicts that difference to be exactly zero, because the format has one
// capacitance number per pin and cannot express an enable-dependent one, so
// this pair is a direct test of a place where one model layer is structurally
// unable to be right. See src/load_ladder.v.
//
// Paths 15 and 16 are the first matched pair. They differ in exactly one thing,
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
// stage: twenty paths all fed from one launch net would burn twenty paths'
// worth of current and put nineteen paths' worth of supply disturbance into
// every measurement, which is precisely the confound the measurement exists to
// avoid.
//
// THE OUTPUT IS MERGED ON A TRI-STATE NODE, NOT THROUGH A MULTIPLEXER. A 20:1
// mux tree is three levels of mux4_1, and the first build's SDF measured that
// tree plus the launch gate at 1.404 ns typical and 3.203 ns slow, which was 37
// to 45 percent of the converter's whole span spent on getting the signal out.
// Since exactly one path is ever launched, the merge only has to be one-hot,
// which is one tri-state level. Same discipline as the drive stage, same
// structural check in tools/check_netlist.py, about a nanosecond cheaper.

`timescale 1ns / 1ps
`default_nettype none

// -------------------------------------------------------------- inverter chain
module char_inv_chain #(
    parameter integer DRIVE = 1,
    parameter integer DEPTH = 8,   // must be even
    parameter integer LOAD  = 0    // COUNT of inv_1 sinks on every stage output
) (
    input  wire in,
    output wire out
);
  wire [DEPTH:0] n;
  assign n[0] = in;
  genvar i, q;
  generate
    for (i = 0; i < DEPTH; i = i + 1) begin : stage
      cell_inv #(.DRIVE(DRIVE)) u (.A(n[i]), .Y(n[i+1]));
      for (q = 0; q < LOAD; q = q + 1) begin : ld
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

// ----------------------------------------------------- drive series, done right
// A DRIVER OF VARYING STRENGTH INTO A LOAD THAT DOES NOT VARY.
//
// The first version of this block got the drive series wrong in a way that no
// test could see and only extraction revealed. It was char_inv_chain at four
// drive variants, which makes every stage the same size, so the driver AND the
// load it drives both scale with the variant and the delay barely moves. The
// post place-and-route SDF of the built chip measured 54, 45, 46 and 49
// picoseconds per stage for drive 1, 2, 4 and 8: a 76 picosecond spread across
// an eightfold change in drive, NOT MONOTONIC, against a converter tap of 121
// picoseconds. The chip's headline drive experiment could not have produced a
// result, and the structure, not the instrument, was the reason.
//
// Here the driver varies and its load does not. Each stage is
//
//     inv_DRIVE  ->  [ SINKS dummy inv_1 loads  +  one inv_8 restorer ]
//
// so the measured driver always faces SINKS*C(inv_1) + C(inv_8), identical for
// every variant. The restorer is deliberately the strongest inverter in the
// set, because it has to drive the NEXT stage's inv_DRIVE input, which is the
// one load that does still vary; making the restorer strong keeps that
// back-term small instead of letting it cancel the effect being measured. The
// term is not zero, it is not subtracted by assumption, and it is small and
// modellable, which is the most that can be said honestly.
//
// Two inversions per stage, so the chain is non-inverting for any STAGES.
module char_drive_series #(
    parameter integer DRIVE  = 1,
    parameter integer STAGES = 12,
    parameter integer SINKS  = 2
) (
    input  wire in,
    output wire out
);
  wire [STAGES:0] n;
  assign n[0] = in;
  genvar i, q;
  generate
    for (i = 0; i < STAGES; i = i + 1) begin : stage
      wire mid;
      cell_inv #(.DRIVE(DRIVE)) drv (.A(n[i]), .Y(mid));
      for (q = 0; q < SINKS; q = q + 1) begin : sink
        wire y;
        cell_inv #(.DRIVE(1)) u (.A(mid), .Y(y));
        wire unused_sink = y;
      end
      cell_inv #(.DRIVE(8)) rest (.A(mid), .Y(n[i+1]));
    end
  endgenerate
  assign out = n[STAGES];
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

// ------------------------------------------------------- load-ladder replica
// An inverter chain carrying the fabric's own load ladder on every stage, with
// the ladder enables tied to a compile-time constant. Two of these, one with
// LEN all zero and one with LEN all ones, differ in NOTHING except the enable
// state, so their delay difference is the ladder mechanism with the
// configurable fabric taken away from around it.
//
// The enables are constants, and the tri-state enable inside cell_einvn goes
// through a keep/dont_touch inverter, so what reaches TE_B is a real net driven
// to a rail rather than a folded constant. tools/check_netlist.py checks that
// distinction and would fail if the flow ever collapsed it.
module char_ladder_chain #(
    parameter integer DEPTH = 8,    // must be even
    parameter [2:0]   LEN   = 3'b000
) (
    input  wire in,
    output wire out
);
  wire [DEPTH:0] n;
  assign n[0] = in;
  genvar i;
  generate
    for (i = 0; i < DEPTH; i = i + 1) begin : stage
      cell_inv #(.DRIVE(1)) u (.A(n[i]), .Y(n[i+1]));
      wire mon;
      load_ladder ld (.node(n[i+1]), .en(LEN), .mon(mon));
      // Deliberately unused. The ladder's reach is witnessed in the fabric, not
      // here; here the ladder exists only to be a load.
      wire unused_mon = mon;
    end
  endgenerate
  assign out = n[DEPTH];
endmodule

// --------------------------------------------------------------------- block C
module char_paths (
    input  wire       launch,       // one rising edge per trial, clk domain
    input  wire [4:0] sel,          // which path is measured
    input  wire [1:0] drive_sel,    // drive variant for paths 15 and 16
    output wire       char_out
);

  localparam integer NPATHS = 20;

  // One-hot decode. Ordinary synthesized logic on purpose: it is static during
  // a measurement and is not in the timed path. The GATE it drives is a real
  // cell, because that one IS in the path.
  //
  // Codes at or above NPATHS clamp to path 0. Without the clamp those codes
  // would leave the tri-state merge below with no driver at all, and a floating
  // node on a real die is an undefined input to whatever observes it.
  wire [4:0]  sel_c = (sel < NPATHS[4:0]) ? sel : 5'd0;
  wire [NPATHS-1:0] en;
  assign en = {{(NPATHS-1){1'b0}}, 1'b1} << sel_c;

  // Balanced launch distribution, built by hand for the same reason as the
  // TDC's sampling tree in src/tdc.v. Twenty launch gates on one net would be
  // buffered by the resizer into a tree of whatever shape satisfied max fanout,
  // and paths on a deeper branch would launch later than paths on a shallower
  // one. That difference is a per-path offset, and a per-path offset is exactly
  // what the depth series CANNOT extract: the series recovers a COMMON offset
  // by fitting a line through five different paths, so an offset that varies
  // between those five lands in the fitted slope and corrupts the per-stage
  // delay itself.
  //
  // One root, five branches, four launch gates each. Every path is the same
  // number of gates from the launch register. Wire delay is still the placer's
  // decision and is still in the residual; this removes the part that was ours.
  wire lroot;
  cell_buf #(.DRIVE(4)) lrt (.A(launch), .X(lroot));

  wire [4:0] lbr;
  genvar j;
  generate
    for (j = 0; j < 5; j = j + 1) begin : lbuf
      cell_buf #(.DRIVE(2)) u (.A(lroot), .X(lbr[j]));
    end
  endgenerate

  // Per-path launch gate. Only the selected path sees an edge.
  wire [NPATHS-1:0] g;
  genvar k;
  generate
    for (k = 0; k < NPATHS; k = k + 1) begin : gate
      cell_and2 u (.A(lbr[k/4]), .B(en[k]), .X(g[k]));
    end
  endgenerate

  // Drive-variant one-hot for the two drive replicas. Constant-free: every bit
  // is a decoded net, so no tri-state enable in the replicas is constant
  // folded and tools/check_netlist.py can still do its job.
  wire [3:0] den;
  assign den[0] = (drive_sel == 2'd0);
  assign den[1] = (drive_sel == 2'd1);
  assign den[2] = (drive_sel == 2'd2);
  assign den[3] = (drive_sel == 2'd3);

  wire [NPATHS-1:0] o;

  // Drive series: the driver varies, the load does not.
  char_drive_series #(.DRIVE(1), .STAGES(12), .SINKS(2)) p0 (.in(g[0]), .out(o[0]));
  char_drive_series #(.DRIVE(2), .STAGES(12), .SINKS(2)) p1 (.in(g[1]), .out(o[1]));
  char_drive_series #(.DRIVE(4), .STAGES(12), .SINKS(2)) p2 (.in(g[2]), .out(o[2]));
  char_drive_series #(.DRIVE(8), .STAGES(12), .SINKS(2)) p3 (.in(g[3]), .out(o[3]));

  // Load series: the load varies, the driver does not. Sixteen stages, which
  // extraction says separates zero sinks from four by about seven converter
  // taps; twenty-four was the first choice and bought nothing but area. Path 4
  // is also the depth 16 point measured a second time under a different name,
  // and it is deliberately not deduplicated: two names for one measurement is a
  // free repeatability check.
  char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(0)) p4 (.in(g[4]), .out(o[4]));
  char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(1)) p5 (.in(g[5]), .out(o[5]));
  char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(2)) p6 (.in(g[6]), .out(o[6]));
  char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(4)) p7 (.in(g[7]), .out(o[7]));

  // Depth series.
  char_inv_chain #(.DRIVE(1), .DEPTH(2),  .LOAD(0)) p8  (.in(g[8]),  .out(o[8]));
  char_inv_chain #(.DRIVE(1), .DEPTH(4),  .LOAD(0)) p9  (.in(g[9]),  .out(o[9]));
  char_inv_chain #(.DRIVE(1), .DEPTH(8),  .LOAD(0)) p10 (.in(g[10]), .out(o[10]));
  char_inv_chain #(.DRIVE(1), .DEPTH(16), .LOAD(0)) p11 (.in(g[11]), .out(o[11]));

  char_nand_chain #(.DRIVE(1), .DEPTH(8)) p12 (.in(g[12]), .en(en[12]), .out(o[12]));
  char_nand_chain #(.DRIVE(4), .DEPTH(8)) p13 (.in(g[13]), .en(en[13]), .out(o[13]));

  // Depth 4, not 8. At depth 8 the first build's SDF put this path at 5.28 ns
  // typical against a 3.835 ns converter span, so it saturated and returned all
  // ones. The ring in src/tdc.v now removes saturation as a failure mode, but a
  // REFERENCE path should sit inside one ring period so that nothing the other
  // paths are quoted against depends on the coarse counter.
  char_mux_chain  #(.DEPTH(4))            p14 (.in(g[14]), .en(en[14]), .out(o[14]));

  char_drive_chain #(.ISOLATE(1), .DEPTH(4)) p15 (.in(g[15]), .den(den), .out(o[15]));
  char_drive_chain #(.ISOLATE(0), .DEPTH(4)) p16 (.in(g[16]), .den(den), .out(o[16]));

  char_ladder_chain #(.DEPTH(8), .LEN(3'b000)) p17 (.in(g[17]), .out(o[17]));
  char_ladder_chain #(.DEPTH(8), .LEN(3'b111)) p18 (.in(g[18]), .out(o[18]));

  // The long end of the depth series. Also the reason every code the clamp can
  // produce has a real driver on the merge rather than a floating node.
  char_inv_chain #(.DRIVE(1), .DEPTH(32), .LOAD(0)) p19 (.in(g[19]), .out(o[19]));

  // ------------------------------------------------------- one-hot tri-state merge
  // Not a multiplexer tree. Exactly one path is ever launched, so the merge
  // only has to be one-hot, and one tri-state level replaces three levels of
  // mux4_1 that the first build's SDF measured at about a nanosecond typical
  // and 2.4 ns slow. That nanosecond was being spent on every single reading.
  //
  // Every element inverts, so the merge inverts, so the final inverter puts the
  // polarity back and every path stays non-inverting end to end.
  wire char_raw;
  generate
    for (k = 0; k < NPATHS; k = k + 1) begin : merge
      cell_einvn #(.DRIVE(4)) u (.A(o[k]), .EN(en[k]), .Z(char_raw));
    end
  endgenerate
  cell_inv #(.DRIVE(2)) merge_out (.A(char_raw), .Y(char_out));

endmodule
