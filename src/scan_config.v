// Configuration scan chain with shadow registers, CRC-8 readback check, and
// the hardware safety controller.
//
// Ordinary synchronous logic on purpose. This block is the thing that stops the
// fabric hurting itself, so it is written the way the rest of the world writes
// digital logic and is left entirely to the synthesizer. The fabric can never
// gate its own kill path, so nothing here takes a combinational input from the
// fabric. The single fabric observable that reaches this block, the transition
// monitor, arrives through a two-stage synchronizer and can only ever cause a
// trip, never clear one.
//
// Chain order, shifted in MSB first:
//     [ GLOBAL W ][ SITE 0 : 12 ][ SITE 1 : 12 ] ... [ SITE N-1 : 12 ][ CRC 8 ]
//
// GLOBAL_W is 48 in src/project.v. The global field map lives in project.v and
// in harness/evofab/genome.py; the only two fields this block consumes are
// window_exp and trans_exp, and their positions are repeated below. If you move
// a global field, move it in all three places in one commit. Nothing here would
// fail loudly if you did not.
//
// The CRC is computed by the host over the payload and appended. On load, the
// device recomputes it and only transfers the shadow chain into the live config
// registers if the CRC matches and arm is high. A bad frame therefore cannot
// reach the fabric at all, which is the point.

// Explicit timescale. Without one, a module picks up whatever default the
// compiler applies, and a delay written as 5 can land on a completely different
// time base than the testbench driving it. That silently stopped the simulation
// model of the calibration rings from oscillating at all in one harness while
// working in another.
`timescale 1ns / 1ps
`default_nettype none

module scan_config #(
    parameter integer N_SITES = 8,
    parameter integer GLOBAL_W = 16
) (
    input  wire                        clk,
    input  wire                        rst_n,
    input  wire                        scan_en,
    input  wire                        scan_in,
    input  wire                        load,
    input  wire                        arm,
    input  wire                        fab_mon,      // asynchronous, fabric side
    output wire                        scan_out,
    output wire                        crc_ok,
    output wire [GLOBAL_W-1:0]         gcfg,
    output wire [12*N_SITES-1:0]       scfg,
    output wire                        inert,
    output wire                        tripped,
    output wire                        meas_busy,
    output wire                        meas_gate,
    output wire                        meas_capture,
    output wire [23:0]                 trans_count
);

  localparam integer PAYLOAD_W = GLOBAL_W + 12*N_SITES;
  localparam integer CHAIN_W   = PAYLOAD_W + 8;

  // ------------------------------------------------------------ shadow chain
  reg [CHAIN_W-1:0] shadow;
  always @(posedge clk) begin
    if (!rst_n)      shadow <= {CHAIN_W{1'b0}};
    else if (scan_en) shadow <= {shadow[CHAIN_W-2:0], scan_in};
  end
  assign scan_out = shadow[CHAIN_W-1];

  // ------------------------------------------------------------------- CRC-8
  // Poly 0x07, init 0x00, MSB first. Chosen because it catches the failure that
  // actually matters here, a frame short or long by a bit, which would
  // otherwise rotate the whole genome and produce a plausible looking but wrong
  // configuration.
  //
  // Computed SERIALLY, one bit per scan clock, not combinationally over the
  // assembled payload. The combinational version was the first thing built and
  // the trial place and route rejected it: a 120 bit payload makes a 120 level
  // deep XOR chain, which showed up as 36 ns of setup violation at the slow
  // corner against a 20 ns clock. The serial version is one XOR level deep and
  // also removes about 12 cells per site, because the tree grew with the site
  // count and so landed in the marginal area column.
  //
  // No end-of-payload counter is needed. For this LFSR form, feeding the
  // payload and then its own CRC leaves the register at zero, so the whole
  // chain is fed in and the check is simply that the register is zero. That
  // property is asserted against an independent implementation in
  // harness/tests/test_genome.py rather than taken on trust.
  // The running register is reinitialised on the rising edge of scan_en, so
  // each frame is checked on its own. Carrying the residue of the previous
  // frame into the next one is not a theoretical concern; it was the first
  // thing the tests caught after this change, and it would have made a good
  // frame look corrupt whenever a corrupt one preceded it.
  function automatic [7:0] crc_step;
    input [7:0] c;
    input       bit_in;
    begin
      crc_step = {c[6:0], 1'b0} ^ ((c[7] ^ bit_in) ? 8'h07 : 8'h00);
    end
  endfunction

  reg [7:0] crc_run;
  reg       scan_en_d;
  always @(posedge clk) scan_en_d <= scan_en;
  wire scan_start = scan_en & ~scan_en_d;

  always @(posedge clk) begin
    if (!rst_n)         crc_run <= 8'h00;
    else if (scan_start) crc_run <= crc_step(8'h00, scan_in);
    else if (scan_en)    crc_run <= crc_step(crc_run, scan_in);
  end
  assign crc_ok = (crc_run == 8'h00);

  wire [PAYLOAD_W-1:0] shadow_payload = shadow[CHAIN_W-1 -: PAYLOAD_W];

  // -------------------------------------------------------- live config regs
  reg [PAYLOAD_W-1:0] live;
  reg                 loaded;
  always @(posedge clk) begin
    if (!rst_n) begin
      live   <= {PAYLOAD_W{1'b0}};
      loaded <= 1'b0;
    end else if (load && crc_ok && arm) begin
      live   <= shadow_payload;
      loaded <= 1'b1;
    end
  end
  assign gcfg = live[PAYLOAD_W-1 -: GLOBAL_W];
  assign scfg = live[12*N_SITES-1:0];

  // ------------------------------------------------------ measurement window
  // Window length is 2^(4 + window_exp) clocks, so 16 clocks up to 2^19. At the
  // 50 MHz target that is 320 ns up to 10.5 ms, which brackets the 1 ms to
  // 10 ms measurement window that docs/THROUGHPUT.md budgets per trial. The
  // window is the trial duration limit as well as the counter gate, so a trial
  // cannot run forever by construction rather than by the host remembering to
  // stop it.
  // The limits are tested by looking at ONE bit of the counter rather than by
  // comparing against 2^k - 1. A counter counting up from zero sets bit k
  // exactly when it reaches 2^k, so the two are equivalent, but the comparison
  // form needs a 24 bit variable shifter and a 24 bit comparator in series and
  // the bit test needs a 24 to 1 mux. The trial place and route found 136
  // endpoints with setup violations and these were two of the deep paths.
  wire [3:0]  window_exp = gcfg[15:12];
  wire [3:0]  trans_exp  = gcfg[19:16];
  wire [4:0]  window_bit = 5'd4 + {1'b0, window_exp};
  wire [4:0]  trans_bit  = 5'd4 + {1'b0, trans_exp};
  reg  [23:0] win_cnt;
  reg         busy;
  reg         load_d;
  always @(posedge clk) load_d <= load;
  wire load_edge = load & ~load_d;

  always @(posedge clk) begin
    if (!rst_n) begin
      win_cnt <= 24'd0;
      busy    <= 1'b0;
    end else if (load_edge && crc_ok && arm) begin
      win_cnt <= 24'd0;
      busy    <= 1'b1;
    end else if (busy) begin
      if (win_cnt[window_bit]) busy <= 1'b0;
      else win_cnt <= win_cnt + 24'd1;
    end
  end
  assign meas_busy = busy;

  // The window is held open for a short tail after the count stops, so the
  // frequency counter can be read while it is frozen and still cleared. See the
  // long note in src/freq_counter.v for why this handshake is shaped this way
  // rather than done with a synchronizer.
  reg [2:0] tail;
  always @(posedge clk) begin
    if (!rst_n)            tail <= 3'd0;
    else if (busy)         tail <= 3'd5;
    else if (tail != 3'd0) tail <= tail - 3'd1;
  end
  assign meas_gate    = busy | (tail != 3'd0);
  assign meas_capture = (tail == 3'd2);

  // ---------------------------------------------- fabric observable, isolated
  reg mon_s1, mon_s2, mon_s3;
  always @(posedge clk) begin
    mon_s1 <= fab_mon;
    mon_s2 <= mon_s1;
    mon_s3 <= mon_s2;
  end
  wire mon_edge = mon_s2 ^ mon_s3;

  // ------------------------------------------------------- transition counter
  // This counts ACTIVITY for the safety limiter, in the system clock domain,
  // and it saturates at one count per clock by construction. It is not a
  // frequency counter and must never be used as one; see src/freq_counter.v.
  reg [23:0] tcnt;
  always @(posedge clk) begin
    if (!rst_n) tcnt <= 24'd0;
    else if (load_edge) tcnt <= 24'd0;
    else if (busy && mon_edge) tcnt <= tcnt + 24'd1;
  end
  assign trans_count = tcnt;

  // ----------------------------------------------- safety, sticky, one way up
  // A configuration that toggles more than 2^(4 + trans_exp) times inside the
  // window is rejected mid-trial. The limit is a transition COUNT rather than a
  // rate because the window is itself bounded, which makes the pair of limits
  // a hard bound on total switching activity per trial.
  // The trip is sticky until reset, arm going low also forces inert, and
  // nothing the fabric can do clears either.
  reg trip;
  always @(posedge clk) begin
    if (!rst_n) trip <= 1'b0;
    else if (busy && tcnt[trans_bit]) trip <= 1'b1;
  end
  assign tripped = trip;
  assign inert   = trip | ~arm | ~loaded;

endmodule
