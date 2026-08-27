// Tapped-delay-line time-to-digital converter. Block T.
//
// WHAT IT MEASURES
//
// One transition, once per trial. A launch edge is released into two things at
// the same instant: this converter's delay line, and the path under test. When
// the path's output edge arrives, it samples the whole delay line at once. The
// number of stages the launch edge had reached by then is the path's delay,
// measured in units of one line stage.
//
// THE RANGE PROBLEM, AND WHY THIS IS A RING
//
// A bare 32 stage line spans 3.835 ns at the typical corner, measured from the
// post place-and-route SDF of the 24 site build, at 0.120 ns per tap. That is
// enough for the fixed characterization paths and it is NOT enough for the
// fabric. From the same SDF, ONE fabric site's series path is 3.515 ns, which
// is 92 percent of the whole span, and 24 sites is about 84 ns, or 22 times it.
// A linear line would have returned all ones for every fabric configuration and
// every sufficiently slow configuration would have looked identical.
//
// So the line is closed into a GATED RING and the wraps are counted. Range
// becomes the counter's range, about 2 us, while resolution stays one tap. This
// is the ordinary coarse-plus-fine construction and it costs one NAND, one flip
// flop and an eight bit counter.
//
// Three properties of the arrangement are load bearing.
//
//   1. The ring is parked until launch and is KILLED by the arrival edge, so it
//      runs for exactly the interval being measured and never for the rest of
//      the measurement window. An instrument that oscillates for ten
//      milliseconds while something else is being measured is a supply
//      disturbance, and this one is the thing we would be measuring with.
//   2. The first traversal after launch behaves exactly as the old linear line
//      did, because the ring parks with every tap high and the launch edge
//      walks a single transition down it. Short paths therefore read the same
//      as before and the wrap count is zero.
//   3. The wrap counter SATURATES rather than wrapping. A wrapped count is
//      indistinguishable from a fast path, which is the one failure that would
//      publish a slow circuit as a fast one.
//
// The ring's period is not assumed. It is the same node the frequency counter
// can be pointed at (cnt_src = 2 in src/project.v), so one trial measures the
// period and another measures the path, on the same die in the same session.
//
// WHY THIS AND NOT A RING OSCILLATOR
//
// The calibration strip already answers "how fast is this die right now" with
// rings, and rings are good at that. They are bad at two things this chip
// needs. A ring reports an average over millions of transitions and cannot
// report a single edge, which is what a combinational path actually does. And
// a ring self-heats while it runs, so the measurement moves the operating
// point it is measuring. A single-transition instrument has neither problem.
//
// WHAT COMES OUT, AND WHY IT IS RAW
//
// The thermometer code leaves this block uncooked, all TAPS bits of it. There
// is no population count in hardware. That is deliberate twice over.
//
//   1. A population count throws away WHERE the ones are. Bubbles in a
//      thermometer code are not noise, they are the map of which bins are wide
//      and which are narrow, and that map is the calibration.
//   2. A population count would be a hardware opinion about how to read the
//      line. The host can change its mind about that after the chip exists;
//      the chip cannot.
//
// THE HONEST LIMITATION, STATED HERE RATHER THAN DISCOVERED LATER
//
// The sampling edge is the path's own output, so it has to reach TAPS flip
// flops. Place and route will build a tree for it, and the skew of that tree
// lands directly on the measurement as a per-tap distortion. It is NOT a
// constant offset and it cannot be subtracted by taking a difference.
//
// This is normal for a delay-line TDC and it has a normal answer: the bins are
// calibrated on the die, not assumed. src/char_paths.v exists partly for this.
// Its depth series gives four known-ratio delays, and the fabric column gives a
// continuously variable one, so bin widths can be recovered by code density on
// real silicon. Any delay quoted from this block before that calibration is
// done is quoted in raw tap counts and says so.
//
// Do not add a hardware bin-width table. It would be a guess baked into metal.
//
// HANDSHAKE
//
// The same shape as src/freq_counter.v, for the same reason. The capture
// register is cleared asynchronously whenever the measurement gate is low, so
// each trial starts from a known state without needing a synchronizer in the
// path of an asynchronous edge, and the value is transferred into the clock
// domain by a single pulse during the tail while the gate is still open.

`timescale 1ns / 1ps
`default_nettype none

module tdc #(
    parameter integer TAPS = 32
) (
    input  wire            clk,
    input  wire            rst_n,
    input  wire            armed,     // released only after the fabric settles
    input  wire            capture,   // one clk pulse inside the tail
    input  wire            start,     // launch edge, clk domain
    input  wire            stop,      // arrival edge, asynchronous
    input  wire            freerun,   // hold the ring running for the whole window
    output wire [TAPS-1:0] taps,
    output wire      [7:0] wrap_count,// full ring periods before the arrival
    output wire            ring,      // the ring node, for the frequency counter
    output wire            done,      // the MOST RECENT trial saw an arrival
    output wire            valid      // taps holds a real capture, not zeros
);

  // ------------------------------------------------------------- delay line
  // Buffers, not inverters. Alternating tap polarity would need a per-tap
  // polarity table to read, and a wrong table is indistinguishable from a
  // broken line. Every element is a keep/dont_touch wrapper, because a delay
  // line is exactly the structure a resizer would like to shorten.
  wire [TAPS:0] line;

  // Ring closure. NAND makes the loop odd-inversion so it oscillates, and gates
  // it: with run low the ring parks with line[0] high and every tap high.
  //
  // ring_kill is set by the arrival edge, which stops the ring immediately. The
  // capture flip flops below are clocked by the same edge through a shorter
  // path (one buffer) than the kill takes to reach line[0] and propagate, so
  // the capture always wins the race. That ordering is the reason the kill is
  // placed here and not inside the sampling registers.
  // freerun suppresses the kill so the ring free-runs for the whole measurement
  // window. That is not a measurement mode, it is how the ring's own PERIOD is
  // measured: point the frequency counter at the ring node (cnt_src = 2 in
  // src/project.v) and count it over a known window. Without that, the coarse
  // count would be in units of an interval nobody had measured, and the whole
  // coarse-plus-fine construction would rest on a Liberty number, which is
  // exactly the circularity PLAN.md section 2 forbids for the TDC.
  reg  ring_kill;
  wire run = start & (~ring_kill | freerun);
  cell_nand2 #(.DRIVE(2)) ring_close (.A(run), .B(line[TAPS]), .Y(line[0]));

  genvar i;
  generate
    for (i = 0; i < TAPS; i = i + 1) begin : dl
      cell_buf #(.DRIVE(1)) u (.A(line[i]), .X(line[i+1]));
    end
  endgenerate

  // ------------------------------------------------------- sample on arrival
  //
  // The arrival edge has to reach TAPS sampling flip flops, and however it gets
  // there is skew that lands on the measurement. Left alone, the resizer would
  // build whatever tree satisfied max fanout, with a depth that varies from
  // branch to branch, and the resulting skew pattern would be an accident of a
  // tool run rather than a property of the design.
  //
  // So the tree is built here, by hand, balanced: one root buffer, four branch
  // buffers, eight flip flops each. Every flop is the same number of gates from
  // the arrival edge. That does not make the skew zero, because the wire
  // lengths are still the placer's decision, but it removes the part that was
  // avoidable and it makes the remaining part something one measurement of the
  // die can characterize rather than something that changes shape whenever the
  // flow is re-run.
  //
  // GROUPS must divide TAPS.
  localparam integer GROUPS   = 4;
  localparam integer PER_GRP  = TAPS / GROUPS;

  // ARMED, not the raw measurement gate. The configuration registers and the
  // window open on the SAME clock edge, so for the first tens of nanoseconds of
  // every trial the fabric is still settling into its new configuration and its
  // outputs are transitioning. A sampler released at that moment captures the
  // settling transient instead of the launched edge, reports done, and returns
  // a number that looks like a fast path. That is what the per-site test
  // measured before this was fixed: the first two taps reported an arrival with
  // the delay line still parked.
  //
  // src/project.v holds this low for the first eight clocks of every window and
  // fires the launch four clocks after that.
  wire clr_n = rst_n & armed;

  wire samp_root;
  cell_buf #(.DRIVE(4)) samp_rt (.A(stop), .X(samp_root));

  wire [GROUPS-1:0] samp;
  genvar b;
  generate
    for (b = 0; b < GROUPS; b = b + 1) begin : sampbuf
      cell_buf #(.DRIVE(2)) u (.A(samp_root), .X(samp[b]));
    end
  endgenerate

  wire [TAPS-1:0] line_taps = line[TAPS:1];

  // Each branch owns its own register rather than a slice of a shared one.
  // Functionally identical and it matters anyway: a single reg written by four
  // always blocks on four different clocks is a multiple-driver construct that
  // linters flag, correctly, because in almost every other design it would be a
  // bug. Writing it this way keeps the lint clean without a waiver, and a
  // waiver here would sit right beside the genuinely unusual thing this file
  // does, where nobody would look at it twice.
  wire [TAPS-1:0]   cap;
  wire [GROUPS-1:0] fired_grp;
  generate
    for (b = 0; b < GROUPS; b = b + 1) begin : sampreg
      reg [PER_GRP-1:0] q;
      reg               f;
      always @(posedge samp[b] or negedge clr_n) begin
        if (!clr_n) begin
          q <= {PER_GRP{1'b0}};
          f <= 1'b0;
        end else begin
          q <= line_taps[b*PER_GRP +: PER_GRP];
          f <= 1'b1;
        end
      end
      assign cap[b*PER_GRP +: PER_GRP] = q;
      assign fired_grp[b]              = f;
    end
  endgenerate

  // Every branch fires on the same edge, so this is an AND rather than an OR:
  // a partial fire means one branch of the sampling tree did not arrive, which
  // is a fault and must not be reported as a measurement.
  wire fired = &fired_grp;

  // ---------------------------------------------------- stop the ring on arrival
  always @(posedge samp_root or negedge clr_n) begin
    if (!clr_n) ring_kill <= 1'b0;
    else        ring_kill <= 1'b1;
  end

  // ------------------------------------------------------------ wrap counter
  // Counts full ring periods between launch and arrival. Clocked by the last
  // tap, asynchronously cleared between trials, and SATURATING: an overflowed
  // count would be indistinguishable from a fast path, and reading a saturated
  // count as a measurement is how a slow circuit gets published as a fast one.
  // The host is expected to check for 8'hFF and discard.
  reg [7:0] wraps;
  always @(posedge line[TAPS] or negedge clr_n) begin
    if (!clr_n)              wraps <= 8'h00;
    else if (wraps != 8'hFF) wraps <= wraps + 8'd1;
  end

  // The coarse count has to be latched by the ARRIVAL edge, exactly like the
  // taps, and not read later in the clock domain. Killing the ring drives
  // line[0] high, and that edge walks down the line and produces one more
  // posedge on line[TAPS] AFTER the measurement is over. Reading the counter
  // later therefore reports one phantom wrap, which is 64 taps of delay that
  // never happened. The tests found this before silicon did: the shortest fixed
  // path in the design reported a full extra ring period.
  reg [7:0] wraps_at_arrival;
  always @(posedge samp_root or negedge clr_n) begin
    if (!clr_n) wraps_at_arrival <= 8'h00;
    else        wraps_at_arrival <= wraps;
  end

  // ------------------------------------------------- hand over to the clk side
  // TAPS bits do not fit in an 8 bit readout port, so the host reads the
  // capture over several trials. That only works if a trial taken purely to
  // read a byte does not destroy the capture it is reading, so the transfer
  // happens only when an arrival edge actually occurred. A trial with the TDC
  // disabled therefore leaves the previous result standing and the host can
  // walk all four bytes of one measurement.
  //
  // The obvious hazard in that scheme is a stale read: a measurement that
  // silently failed to arrive would be read as if it were fresh. So there are
  // two flags and they mean different things.
  //
  //   done  the MOST RECENT trial produced an arrival edge. Check this on the
  //         measuring trial. It goes low on a trial that measured nothing.
  //   valid a real capture has been latched at some point since reset, so the
  //         tap register is not merely zeros from power-up.
  //
  // Reading bytes without checking done is how a dead path gets published as a
  // fast one.
  reg [TAPS-1:0] held;
  reg      [7:0] held_wraps;
  reg            held_valid;
  reg            fired_last;
  always @(posedge clk) begin
    if (!rst_n) begin
      held       <= {TAPS{1'b0}};
      held_wraps <= 8'h00;
      held_valid <= 1'b0;
      fired_last <= 1'b0;
    end else if (capture) begin
      fired_last <= fired;
      if (fired) begin
        held       <= cap;
        held_wraps <= wraps_at_arrival;
        held_valid <= 1'b1;
      end
    end
  end

  assign taps       = held;
  assign wrap_count = held_wraps;
  assign ring       = line[TAPS];
  assign done       = fired_last;
  assign valid      = held_valid;

endmodule
