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
//   - the fixed characterization paths (src/char_paths.v), twenty of them
//   - a ring-mode tapped-delay-line TDC (src/tdc.v) that measures ONE
//     transition, with a per-site tap so it can measure part of the column
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
// 20, on 6x2 tiles. Not 32, and the reason is in docs/AREA_GATE.md: adding the
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
  `define N_SITES 20
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
  localparam integer GLOBAL_W = 48;
  localparam integer SITE_W   = 12;
  localparam integer TDC_TAPS = 32;

  // Bumped whenever anything a host has to know about changes shape: a field
  // moves, a readout slot changes meaning, or an instrument's output changes
  // encoding. Readable at readout_sel 20, so a host talking to an unfamiliar
  // die finds out rather than assuming. Version 2 is the Gray coded coarse
  // count and the four-way TDC stop source.
  localparam [7:0] INSTR_VERSION = 8'd2;

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
  wire [SITE_W*N_SITES-1:0] scfg;
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
  wire [1:0] cnt_src     = gcfg[6:5];   // 0 calib ring, 1 fabric column, 2 TDC ring
  wire [4:0] readout_sel = gcfg[11:7];
  //         window_exp  = gcfg[15:12]  (scan_config)
  //         trans_exp   = gcfg[19:16]  (scan_config)
  wire       tdc_en      = gcfg[20];
  //         gcfg[21]    RETIRED. It was a one bit tdc_src. The field grew to
  //                     two and was moved whole rather than split across the
  //                     word, because a field in two pieces is a field someone
  //                     eventually reads half of. Nothing drives it and nothing
  //                     reads it; it is in the spare list below.
  wire       tdc_pol     = gcfg[22];    // invert the arrival edge
  wire [4:0] char_sel    = gcfg[27:23];
  wire [1:0] char_drive  = gcfg[29:28]; // drive variant for char paths 15, 16
  wire [4:0] tdc_tap     = gcfg[34:30]; // which site output stops the TDC
  wire       tdc_freerun = gcfg[35];    // let the ring run, to measure its period
  // 0 characterization path, 1 fabric tap, 2 calibration ring, 3 external pin.
  // See the stop source block below for what the last two are for.
  wire [1:0] tdc_src     = gcfg[37:36];

  // ------------------------------------------------------------- TDC launch
  // Exactly one rising edge per trial, produced in the clock domain. It rises
  // one clock after the measurement window opens, which is one clock after the
  // TDC's asynchronous clear is released, so the delay line always starts from
  // a cleared sampler. It falls when the window closes.
  //
  // Gated by tdc_en, so with the TDC off nothing in src/char_paths.v switches
  // at all and a fabric measurement is not sharing its supply with it.
  // The configuration registers and the measurement window open on the SAME
  // clock edge, so at the start of every trial the fabric is still settling
  // into its new configuration and every site output is transitioning. Arming
  // the converter then captures the settling transient rather than the launched
  // edge, and reports it as a successful measurement.
  //
  // So the window is divided. Eight clocks of settling with the sampler held in
  // reset, then arm, then four more clocks, then launch. At 20 ns that is 160 ns
  // of settling. The reference for how long is enough is the 24 site build,
  // whose whole column extracted at about 84 ns at the typical corner; this
  // column is shorter than that one and the margin is therefore larger than the
  // one the number was chosen against. The counter saturates rather than
  // rolling over, so a longer window cannot silently shorten it.
  //
  // tdc_wait is cleared by meas_gate rather than meas_busy on purpose: the gate
  // stays high through the readout tail, so the armed signal does too, so the
  // capture is not cleared out from under the transfer.
  reg [3:0] tdc_wait;
  always @(posedge clk) begin
    if (!rst_n || !meas_gate)   tdc_wait <= 4'd0;
    else if (tdc_wait != 4'd15) tdc_wait <= tdc_wait + 4'd1;
  end
  wire tdc_armed = (tdc_wait >= 4'd8);

  reg launch;
  always @(posedge clk) begin
    if (!rst_n) launch <= 1'b0;
    else        launch <= tdc_en & meas_busy & (tdc_wait >= 4'd12);
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
  cell_mux2 u_fab_src (.A0(fab_a), .A1(launch), .S(tdc_en & (tdc_src == 2'd1)), .X(fab_head));
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
          .cfg(scfg[SITE_W*(N_SITES-1-s) +: SITE_W]),
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

  // -------------------------------------------------- the per-site stop tap
  // The TDC's arrival edge can come from ANY site's output, not only the end of
  // the column. Without this the only fabric measurement available is one number
  // for the whole column, and on the 24 site build the SDF put that number at
  // about 84 ns against a converter that resolves 0.12 ns; the interesting
  // quantity, the cost of one site, would have been buried in it.
  //
  // Sweeping the tap gives a per-site delay series, and the per-site delay comes
  // out as the SLOPE, exactly the way the characterization block's depth series
  // works. That is the measurement this chip exists to make.
  //
  // The tree is BALANCED, three cells deep for every input, padded to 32. That
  // is not tidiness. An unbalanced tree would put a different mux delay on
  // different taps, and a per-tap offset lands directly in the fitted slope,
  // which is the one number the whole fabric experiment produces.
  //
  // The cost is one mux4 input hanging on every site's output node. It is the
  // same on every site and in every configuration, so it moves the absolute
  // delay and cancels in the slope. It is not free and it is not hidden: a site
  // output on this chip carries the four drive variants, the load ladder, the
  // next site's route mux AND this tap.
  wire [31:0] tap_in;
  genvar t;
  generate
    for (t = 0; t < 32; t = t + 1) begin : tapsel
      // Pad with the column output rather than a constant: every input of the
      // tree must be a real driven net so that no code selects a dead branch.
      assign tap_in[t] = (t < N_SITES) ? col[t+1] : col[N_SITES];
    end
  endgenerate

  wire [7:0] tap_l1;
  wire [1:0] tap_l2;
  wire       tap_out;
  generate
    for (t = 0; t < 8; t = t + 1) begin : tapl1
      cell_mux4 u (.A0(tap_in[4*t]), .A1(tap_in[4*t+1]),
                   .A2(tap_in[4*t+2]), .A3(tap_in[4*t+3]),
                   .S0(tdc_tap[0]), .S1(tdc_tap[1]), .X(tap_l1[t]));
    end
    for (t = 0; t < 2; t = t + 1) begin : tapl2
      cell_mux4 u (.A0(tap_l1[4*t]), .A1(tap_l1[4*t+1]),
                   .A2(tap_l1[4*t+2]), .A3(tap_l1[4*t+3]),
                   .S0(tdc_tap[2]), .S1(tdc_tap[3]), .X(tap_l2[t]));
    end
  endgenerate
  cell_mux2 tapl3 (.A0(tap_l2[0]), .A1(tap_l2[1]), .S(tdc_tap[4]), .X(tap_out));

  // ------------------------------------------------------------------- TDC
  // The arrival edge is either a fixed path or a tap on the fabric column, and
  // either may arrive falling rather than rising depending on how the fabric is
  // configured, so the polarity is a config bit. Without it half the fabric
  // configurations would simply be unmeasurable.
  // THE TWO ASYNCHRONOUS STOP SOURCES, AND WHAT THEY ARE FOR
  //
  // Bin width calibration by code density needs a stop whose phase relative to
  // the launch edge is UNIFORM, and neither of the first two sources is. A
  // fixed characterization path arrives at the same place in the line every
  // time, so it exercises one bin and says nothing about the other 31. A
  // fabric configuration arrives wherever that configuration puts it, and the
  // distribution over random configurations is unknown, which is not the same
  // thing as uniform and must not be used as though it were.
  //
  // A free running calibration ring is uncorrelated with the TDC's own ring by
  // construction: different structure, different length, no common gate. So the
  // arrival phase walks the whole period and the histogram of fine codes is the
  // bin width map. That is the one honest code density source on this chip.
  //
  // The gating matters as much as the source. The sampler is released eight
  // clocks before the launch so the fabric can settle, and a free running ring
  // would trip it during that window every time. ANDing the ring with the
  // launch does not fix it either: whenever the ring happens to be high when
  // the launch rises, the AND produces an edge at the launch instant, which is
  // a fixed reading masquerading as a random one for half of all trials.
  //
  // So the async sources are edge armed instead. This flip flop is held cleared
  // while the launch is low and set by the first rising edge of the source
  // after it, which is exactly one edge per trial at a phase uniform over the
  // source's period. It sits outside the path of sources 0 and 1 and adds
  // nothing to them.
  //
  // Source 3 is the SCAN_IN pin. It is not a spare pin, it is a pin that is
  // already ignored during a measurement: the scan chain only listens to it
  // while scan_en is high, and scan_en is low for the whole window. An external
  // stop needs board timing nobody should trust at 100 ps, so it is here for
  // deliberate stimulus and for bring-up, not for quoting a delay against.
  wire async_raw;
  cell_mux2 u_async_src (.A0(calib_osc), .A1(scan_in), .S(tdc_src[0]), .X(async_raw));
  reg async_stop;
  always @(posedge async_raw or negedge launch) begin
    if (!launch) async_stop <= 1'b0;
    else         async_stop <= 1'b1;
  end

  // One four way cell rather than a chain of twos, so that every source carries
  // the SAME select delay. An unequal select tree would put a different fixed
  // offset on the characterization paths than on the fabric taps, and those two
  // are quoted against each other.
  wire tdc_stop_raw;
  cell_mux4 u_tdc_src (.A0(char_out), .A1(tap_out), .A2(async_stop), .A3(async_stop),
                       .S0(tdc_src[0]), .S1(tdc_src[1]), .X(tdc_stop_raw));
  wire tdc_stop;
  cell_xor2 u_tdc_pol (.A(tdc_stop_raw), .B(tdc_pol), .X(tdc_stop));

  wire [TDC_TAPS-1:0] tdc_taps;
  wire [7:0]          tdc_gray;
  wire                tdc_done, tdc_valid, tdc_ring;
  tdc #(.TAPS(TDC_TAPS)) u_tdc (
      .clk(clk), .rst_n(rst_n),
      .armed(tdc_armed), .capture(meas_capture),
      .start(launch), .stop(tdc_stop), .freerun(tdc_freerun),
      .taps(tdc_taps), .wrap_gray(tdc_gray), .ring(tdc_ring),
      .done(tdc_done), .valid(tdc_valid));

  // ------------------------------------------------ what the counters watch
  // Both instruments watch the same selected node. The safety monitor counts
  // activity in the system clock domain and can trip. The frequency counter is
  // clocked by the node itself and only measures.
  // 0 the calibration strip, 1 the fabric column, 2 the TDC's own ring. The
  // third is how the ring's period gets measured rather than assumed, which is
  // what keeps the coarse count in units of a measured interval.
  reg osc_sel;
  always @(*) begin
    case (cnt_src)
      2'd1:    osc_sel = col[N_SITES];
      2'd2:    osc_sel = tdc_ring;
      default: osc_sel = calib_osc;
    endcase
  end

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
      5'd0:  readout = freq_count[7:0];
      5'd1:  readout = freq_count[15:8];
      5'd2:  readout = freq_count[23:16];
      5'd3:  readout = trans_count[7:0];
      5'd4:  readout = trans_count[15:8];
      5'd5:  readout = trans_count[23:16];
      // tdc_done is about the LAST trial; tdc_valid is about the tap register.
      // See the long note in src/tdc.v before using either one.
      5'd6:  readout = {1'b0, tdc_valid, tdc_done, tripped, meas_busy, crc_ok,
                        n_sites_w[1:0]};
      5'd7:  readout = n_sites_w;
      5'd8:  readout = tdc_taps[7:0];
      5'd9:  readout = tdc_taps[15:8];
      5'd10: readout = tdc_taps[23:16];
      5'd11: readout = tdc_taps[31:24];
      5'd12: readout = TDC_TAPS[7:0];
      // The twin mask, so the host can prove at run time that it and the chip
      // agree about which sites are the un-isolated controls. A host that has
      // this wrong would attribute an isolation effect to the wrong sites and
      // nothing else would notice.
      5'd13: readout = ISO_TWIN_MASK[7:0];
      5'd14: readout = 8'd20;          // characterization path count
      // The coarse half of a TDC reading, GRAY CODED. It is captured by the
      // arrival edge out of the ring's own domain, and a binary count crossing
      // a carry boundary can be captured as any value at all, including the
      // saturation code. Convert with gray_to_bin() before doing anything with
      // it. 8'h80 is the Gray code of 8'hFF and means the counter SATURATED:
      // discard, do not scale. See the long note in src/tdc.v.
      5'd16: readout = tdc_gray;
      // Echoes, so the host can prove the select fields reached the hardware
      // rather than assuming a frame landed where it meant to.
      5'd17: readout = {3'b000, tdc_tap};
      5'd18: readout = {3'b000, char_sel};
      5'd19: readout = GLOBAL_W[7:0];
      // What the host has to agree with the chip about before a single genome
      // means anything. A host that has the payload arithmetic wrong addresses
      // the wrong site and nothing else notices.
      5'd20: readout = INSTR_VERSION;
      5'd21: readout = {4'b0000, tdc_freerun, tdc_pol, tdc_src};
      5'd22: readout = SITE_W[7:0];
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

  // gcfg[19:12] is window_exp and trans_exp, consumed inside scan_config rather
  // than here; gcfg[21] is retired and gcfg[47:38] is spare. All are listed so
  // the linter can see that leaving them alone at this level is deliberate.
  wire _unused = &{uio_in, gcfg[19:12], gcfg[21], gcfg[47:38], 1'b0};

endmodule
