// tt_um_ajhendel_evofab
//
// The tinytapeout1 vehicle. See PLAN.md for the mission, HANDOFF.md for the
// work packages, and docs/MEASUREMENT_PROTOCOL.md for how the blocks below are
// meant to be used together.
//
// Contents
//   - N_SITES fabric sites (src/fabric_site.v), a feed-forward column with one
//     enumerated feedback edge behind a global enable
//   - the calibration strip (src/calib_macro.v), eight fixed ring oscillators
//   - the fixed characterization paths (src/char_paths.v), sixteen of them
//   - a tapped-delay-line TDC (src/tdc.v) that measures ONE transition
//   - scan chain, CRC-8 gated load, measurement window, transition counter,
//     frequency counter and the hardware safety controller
//
// THE TWO INSTRUMENTS, AND WHY THERE ARE TWO
//
// The frequency counter watches a ring and reports an average over millions of
// transitions. That makes it a joint process, voltage, temperature and
// activity covariate, which is what it is for, and it makes it useless for the
// delay of a single edge through a combinational path. The TDC measures
// exactly one edge and does not run long enough to heat anything. Every
// experiment in docs/MEASUREMENT_PROTOCOL.md names which instrument it uses.
//
// N_SITES is a parameter so that the area gate can be measured properly. Cells
// per site is the MARGINAL cost, obtained by building at several N and taking
// the slope, not by building once and dividing. Dividing charges the fixed
// infrastructure to the sites and would make the fabric look far more expensive
// than it is. See tools/area_sweep.sh and docs/AREA_GATE.md.

// Explicit timescale. Without one, a module picks up whatever default the
// compiler applies, and a delay written as 5 can land on a completely different
// time base than the testbench driving it. That silently stopped the simulation
// model of the calibration rings from oscillating at all in one harness while
// working in another.
`timescale 1ns / 1ps
`default_nettype none

// Site count. Overridable from the command line (iverilog -DN_SITES=4, or
// VERILOG_DEFINES in the LibreLane config) so the marginal-area sweep can build
// several sizes from one source. The submission value is set here, and it is
// the ONE place it is set: test/Makefile and test/test.py take it from the
// environment with this same default, and the readout at readout_sel 7 reports
// what the silicon actually has, so a mismatch fails a test rather than
// producing a plausible wrong genome.
//
// 24, on 6x2 tiles. Not 32, and the reason is in docs/AREA_GATE.md: adding the
// characterization paths, the TDC and the larger calibration strip moved about
// 650 cells into the FIXED column, which is a little over two tiles of overhead
// that no site count amortises. At 24 sites a 6x2 build projects to 29.5
// percent utilization, against the 34.8 percent that already routed clean at 8
// sites on 2x2. At 32 sites the same 6x2 projects to 35.2 percent, which is not
// a margin, it is a coincidence.
//
// The rule this follows is PLAN.md section 3's: cut sites before cutting the
// calibration strip. It is applied here to the strip's own growth, which is the
// case the rule was written for and not the case anyone expected to hit.
`ifndef N_SITES
  `define N_SITES 24
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
  localparam integer GLOBAL_W = 32;
  localparam integer TDC_TAPS = 32;

  // ------------------------------------------------- the un-isolated controls
  // Sites 1, 3, 5 and 7 are built WITHOUT drive-variant input isolation. Every
  // other site has it. See src/drive_node.v for what isolation is and why the
  // chip carries both arrangements instead of picking one.
  //
  // Two properties of this rule are deliberate.
  //
  //   - The controls are PAIRED with their neighbours, (0,1), (2,3), (4,5),
  //     (6,7), so each un-isolated site has an isolated twin that the flow had
  //     every reason to place beside it. Comparing across a die is a different
  //     and much noisier experiment.
  //   - The set does not depend on N_SITES. That keeps the marginal-area slope
  //     between the 8 and 16 site builds a pure isolated-site number, so the
  //     projection to the submission size is not a blend of two costs, and it
  //     keeps a genome addressed to site 11 meaning the same thing at every
  //     build size.
  //
  // A search that wants a uniform fabric should use sites 8 and up. A search
  // allowed to roam over all of them is a legitimate and separate experiment,
  // and the host knows which sites are which because the mask is readable at
  // readout_sel 13.
  localparam [31:0] ISO_TWIN_MASK = 32'h0000_00AA;   // 1 = un-isolated control

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
  wire                  meas_gate, meas_capture;
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
      .meas_gate(meas_gate), .meas_capture(meas_capture),
      .trans_count(trans_count));

  // Global field map. The single definition of this layout that software reads
  // is harness/evofab/genome.py; if you move a field, move it there in the same
  // commit or the harness will address the wrong bits and nothing will fail
  // loudly. window_exp and trans_exp are consumed inside scan_config and their
  // positions are duplicated there for the same reason.
  wire       fb_en       = gcfg[0];
  wire       calib_en    = gcfg[1];
  wire [2:0] calib_sel   = gcfg[4:2];
  wire       cnt_src     = gcfg[5];
  wire [3:0] readout_sel = gcfg[9:6];
  //         window_exp  = gcfg[13:10]   (scan_config)
  //         trans_exp   = gcfg[17:14]   (scan_config)
  wire       tdc_en      = gcfg[18];
  wire       tdc_src     = gcfg[19];     // 0 = characterization path, 1 = fabric
  wire       tdc_pol     = gcfg[20];     // invert the arrival edge
  wire [3:0] char_sel    = gcfg[24:21];
  wire [1:0] char_drive  = gcfg[26:25];  // drive variant for char paths 14, 15

  // ------------------------------------------------------------- TDC launch
  // Exactly one rising edge per trial, produced in the clock domain. It rises
  // one clock after the measurement window opens, which is one clock after the
  // TDC's asynchronous clear is released, so the delay line always starts from
  // a cleared sampler. It falls when the window closes.
  //
  // Gated by tdc_en, so with the TDC off nothing in src/char_paths.v switches
  // at all and a fabric measurement is not sharing its supply with it.
  reg launch;
  always @(posedge clk) begin
    if (!rst_n) launch <= 1'b0;
    else        launch <= tdc_en & meas_busy;
  end

  // ------------------------------------------------------------ the fabric
  wire [N_SITES:0] col;        // col[0] is the column input, col[i+1] site i out
  wire [N_SITES-1:0] site_mon;

  // The enumerated feedback edge. Exactly one, from the column output back to
  // the head of the column, behind fb_en and behind inert. This is the path
  // that makes the fabric able to oscillate, which is the whole reason the
  // design needs keep/dont_touch and the reason WP2 exists as a gate.
  //
  // It is a feedback edge and nothing more. It is not a coupled-oscillator
  // machine, it is not an Ising solver, and it must not be described as a
  // weaker version of one: there is no controllable coupling, no phase
  // readout, no locking guarantee and no independent enable per oscillator.
  // What it can do is oscillate, which is a capability to be characterized on
  // silicon, not a claim to be made in advance.
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

  // The column head is normally the FAB_A pin. When the TDC is measuring the
  // fabric it is the launch edge instead, so an evolved circuit can be timed by
  // the same instrument as the fixed reference paths. The multiplexer is one
  // cell and it is ALWAYS in the column, in both modes, so it contributes the
  // same constant to every fabric measurement rather than appearing only in
  // the mode being compared.
  wire fab_head;
  cell_mux2 u_fab_src (.A0(fab_a), .A1(launch), .S(tdc_en & tdc_src), .X(fab_head));
  assign col[0] = fab_head;

  genvar s;
  generate
    for (s = 0; s < N_SITES; s = s + 1) begin : sites
      fabric_site #(
          // Sites 1, 3, 5 and 7 are the un-isolated controls. See the note on
          // ISO_TWIN_MASK above.
          .ISOLATE((s < 8 && (s % 2) == 1) ? 0 : 1)
      ) u_site (
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

  // --------------------------------------------- fixed characterization paths
  wire char_out;
  char_paths u_char (
      .launch(launch), .sel(char_sel), .drive_sel(char_drive), .char_out(char_out));

  // ------------------------------------------------------------------- TDC
  // The arrival edge is either a fixed path or the fabric column, and either
  // may arrive falling rather than rising depending on how the fabric is
  // configured, so the polarity is a config bit. Without it half the fabric
  // configurations would simply be unmeasurable.
  wire tdc_stop_raw = tdc_src ? col[N_SITES] : char_out;
  wire tdc_stop;
  cell_xor2 u_tdc_pol (.A(tdc_stop_raw), .B(tdc_pol), .X(tdc_stop));

  wire [TDC_TAPS-1:0] tdc_taps;
  wire                tdc_done, tdc_valid;
  tdc #(.TAPS(TDC_TAPS)) u_tdc (
      .clk(clk), .rst_n(rst_n),
      .gate(meas_gate), .capture(meas_capture),
      .start(launch), .stop(tdc_stop),
      .taps(tdc_taps), .done(tdc_done), .valid(tdc_valid));

  // ------------------------------------------------ what the counters watch
  // Both instruments watch the same selected node. The safety monitor counts
  // activity in the system clock domain and can trip. The frequency counter is
  // clocked by the node itself and only measures.
  wire osc_sel = cnt_src ? col[N_SITES] : calib_osc;

  // u_mon_iso is a timing anchor, not logic. The safety monitor's input is
  // asynchronous by construction, which is why it goes through a three-stage
  // synchronizer, so static timing must not try to close a path from the
  // fabric to it. Saying that in the SDC needs something stable to point at,
  // and the only names that reliably survive the whole flow are the
  // hand-instantiated keep/dont_touch cells, which is what this is.
  //
  // The name is load bearing in three files at once. src/timing.sdc cuts the
  // path through it, tools/check_netlist.py fails if the cell is gone, and
  // tools/check_constraints.py fails if the two stop agreeing. That triangle
  // exists because the failure it prevents is silent: a constraint that
  // matches nothing produces no error, the flow passes, and a path that was
  // never timed comes back on a die.
  //
  // Without this the deepening column would be a real problem rather than a
  // constraint problem. At 8 sites the fabric-to-monitor path was long and met
  // timing; the column grows linearly with the site count and this path grows
  // with it, so at the submission size it would violate on a path that has no
  // reason to be timed at all.
  cell_buf_1 u_mon_iso (.A(osc_sel), .X(mon_to_safety));

  freq_counter u_freq (
      .clk(clk), .rst_n(rst_n), .osc(osc_sel),
      .gate(meas_gate), .count_en(meas_busy), .capture(meas_capture),
      .value(freq_count));

  // ---------------------------------------------------------------- readout
  wire [7:0] n_sites_w = N_SITES[7:0];
  reg  [7:0] readout;
  always @(*) begin
    case (readout_sel)
      4'd0:  readout = freq_count[7:0];
      4'd1:  readout = freq_count[15:8];
      4'd2:  readout = freq_count[23:16];
      4'd3:  readout = trans_count[7:0];
      4'd4:  readout = trans_count[15:8];
      4'd5:  readout = trans_count[23:16];
      // tdc_done is about the LAST trial; tdc_valid is about the tap register.
      // See the long note in src/tdc.v before using either one.
      4'd6:  readout = {1'b0, tdc_valid, tdc_done, tripped, meas_busy, crc_ok,
                        n_sites_w[1:0]};
      4'd7:  readout = n_sites_w;
      4'd8:  readout = tdc_taps[7:0];
      4'd9:  readout = tdc_taps[15:8];
      4'd10: readout = tdc_taps[23:16];
      4'd11: readout = tdc_taps[31:24];
      4'd12: readout = TDC_TAPS[7:0];
      // The twin mask, so the host can prove at run time that it and the chip
      // agree about which sites are the un-isolated controls. A host that has
      // this wrong would attribute an isolation effect to the wrong sites and
      // nothing else would notice.
      4'd13: readout = ISO_TWIN_MASK[7:0];
      4'd14: readout = 8'd16;          // characterization path count
      default: readout = 8'hA5;        // fixed pattern: the readout mux is alive
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
  // OBS_OUT. A scope pin. With the TDC enabled the interesting analogue node is
  // the characterization path output, because that is the edge being timed.
  assign uo_out[3] = obs_sel ? calib_osc : (tdc_en ? char_out : fb_net);
  assign uo_out[4] = meas_busy;
  assign uo_out[5] = tripped;
  assign uo_out[6] = fab_load_mon;
  assign uo_out[7] = inert;

  // gcfg[17:10] is window_exp and trans_exp, consumed inside scan_config rather
  // than here; gcfg[31:27] is spare. Both are listed so the linter can see that
  // leaving them alone at this level is deliberate.
  wire _unused = &{uio_in, gcfg[17:10], gcfg[31:27], 1'b0};

endmodule
