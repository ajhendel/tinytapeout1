// tt_um_ajhendel_evofab
//
// WP2 trial vehicle for the tinytapeout1 evolvable electrical-realization
// fabric. See PLAN.md for the mission and HANDOFF.md for the work packages.
//
// Contents
//   - N_SITES fabric sites (src/fabric_site.v), a feed-forward column with one
//     enumerated feedback edge behind a global enable
//   - one fixed calibration macro (src/calib_macro.v), four ring oscillators
//   - scan chain, CRC-8 gated load, measurement window, transition counter and
//     the hardware safety controller (src/scan_config.v)
//
// N_SITES is a parameter so that the area gate can be measured properly. Cells
// per site is the MARGINAL cost, obtained by building at several N and taking
// the slope, not by building once and dividing. Dividing charges the fixed
// infrastructure to the sites and would make the fabric look far more expensive
// than it is. See tools/area_sweep.sh and docs/THROUGHPUT.md.

`default_nettype none

// Site count. Overridable from the command line (iverilog -DN_SITES=4, or
// VERILOG_DEFINES in the LibreLane config) so the marginal-area sweep can build
// several sizes from one source. The submission value is set here.
`ifndef N_SITES
  `define N_SITES 8
`endif

module tt_um_ajhendel_evofab (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  localparam integer N_SITES  = `N_SITES;
  localparam integer GLOBAL_W = 16;

  // -------------------------------------------------------------- pin naming
  wire scan_en    = ui_in[0];
  wire scan_in    = ui_in[1];
  wire load       = ui_in[2];
  wire arm        = ui_in[3] & ena;
  wire fab_a      = ui_in[4];
  wire fab_b      = ui_in[5];
  wire obs_sel    = ui_in[6];
  wire cnt_hold   = ui_in[7];

  // --------------------------------------------------------------- infra
  wire                  scan_out, crc_ok, inert, tripped, meas_busy;
  wire [GLOBAL_W-1:0]   gcfg;
  wire [12*N_SITES-1:0] scfg;
  wire [23:0]           trans_count;
  wire [23:0]           freq_count;
  wire                  mon_to_safety;

  scan_config #(.N_SITES(N_SITES), .GLOBAL_W(GLOBAL_W)) u_cfg (
      .clk(clk), .rst_n(rst_n),
      .scan_en(scan_en), .scan_in(scan_in), .load(load), .arm(arm),
      .fab_mon(mon_to_safety),
      .scan_out(scan_out), .crc_ok(crc_ok),
      .gcfg(gcfg), .scfg(scfg),
      .inert(inert), .tripped(tripped), .meas_busy(meas_busy),
      .trans_count(trans_count));

  wire       fb_en      = gcfg[0];
  wire       calib_en   = gcfg[1];
  wire [1:0] calib_sel  = gcfg[3:2];
  wire       cnt_src    = gcfg[4];
  wire [2:0] readout_sel = gcfg[7:5];

  // ------------------------------------------------------------ the fabric
  wire [N_SITES:0] col;        // col[0] is the column input, col[i+1] site i out
  wire [N_SITES-1:0] site_mon;

  // The enumerated feedback edge. Exactly one, from the column output back to
  // the head of the column, behind fb_en and behind inert. This is the path
  // that makes the fabric able to oscillate, which is the whole reason the
  // design needs keep/dont_touch and the reason WP2 exists as a gate.
  wire fb_raw, fb_net;
`ifdef SIM
  // An event simulator cannot settle the loop. In SIM the edge is registered,
  // which turns the ring into a clocked oscillator so that everything around it
  // (scan, CRC, window, transition counter, trip) is still testable.
  reg fb_q;
  always @(posedge clk) begin
    if (!rst_n) fb_q <= 1'b0;
    else fb_q <= fb_raw;
  end
  assign fb_net = fb_q;
`else
  assign fb_net = fb_raw;
`endif
  cell_nand2 #(.DRIVE(1)) u_fb_gate (
      .A(col[N_SITES]), .B(fb_en & ~inert), .Y(fb_raw));

  assign col[0] = fab_a;

  genvar s;
  generate
    for (s = 0; s < N_SITES; s = s + 1) begin : sites
      fabric_site u_site (
          .a_prev(col[s]),
          .a_pi(fab_a),
          .a_fb(fb_net),
          .b_in(fab_b),
          .inert(inert),
          // Chain order is [GLOBAL][SITE 0][SITE 1]...[SITE N-1][CRC], shifted
          // MSB first, so site 0 sits in the HIGH bits of scfg. Indexing this
          // the obvious way instead would silently reverse the genome and every
          // per-site experiment would address the wrong site.
          .cfg(scfg[12*(N_SITES-1-s) +: 12]),
          .out(col[s+1]),
          .load_mon(site_mon[s]));
    end
  endgenerate

  // Reduce the per-site ladder observables to one bit. This is the reach
  // witness for the load ladder; sweeping the ladder field must move it.
  // OR, not XOR. With every site configured alike, an XOR over an even number
  // of sites cancels to a constant and the witness silently stops witnessing.
  wire fab_load_mon = |site_mon;

  // ------------------------------------------------------ calibration strip
  wire calib_osc;
  calib_macro u_calib (.en(calib_en & ~inert), .sel(calib_sel), .osc_out(calib_osc));

  // ------------------------------------------------ what the counters watch
  // Both instruments watch the same selected node. The safety monitor counts
  // activity in the system clock domain and can trip. The frequency counter is
  // clocked by the node itself and only measures.
  wire osc_sel = cnt_src ? col[N_SITES] : calib_osc;
  assign mon_to_safety = osc_sel;

  freq_counter u_freq (
      .clk(clk), .rst_n(rst_n), .osc(osc_sel), .gate(meas_busy),
      .value(freq_count));

  // ---------------------------------------------------------------- readout
  wire [7:0] n_sites_w = N_SITES[7:0];
  reg  [7:0] readout;
  always @(*) begin
    case (readout_sel[1:0])
      2'd0: readout = readout_sel[2] ? trans_count[7:0]  : freq_count[7:0];
      2'd1: readout = readout_sel[2] ? trans_count[15:8]  : freq_count[15:8];
      2'd2: readout = readout_sel[2] ? trans_count[23:16] : freq_count[23:16];
      default: readout = {3'b000, tripped, meas_busy, crc_ok, n_sites_w[1:0]};
    endcase
  end

  reg [7:0] readout_held;
  always @(posedge clk) begin
    if (!rst_n) readout_held <= 8'h00;
    else if (!cnt_hold) readout_held <= readout;
  end

  assign uio_out = readout_held;
  assign uio_oe  = 8'hFF;      // readout bus is output only on this vehicle

  assign uo_out[0] = scan_out;
  assign uo_out[1] = crc_ok;
  assign uo_out[2] = col[N_SITES];
  assign uo_out[3] = obs_sel ? calib_osc : fb_net;
  assign uo_out[4] = meas_busy;
  assign uo_out[5] = tripped;
  assign uo_out[6] = fab_load_mon;
  assign uo_out[7] = inert;

  wire _unused = &{uio_in, gcfg[15:8], 1'b0};

endmodule
