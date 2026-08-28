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
    output wire      [7:0] wrap_gray, // full ring periods before arrival, GRAY
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
  // ring_kill is asserted once the sampling registers have CAPTURED, not on the
  // arrival edge itself. See the long note at the kill below: the two used to
  // be started by the same edge and raced, and extraction says the race was
  // lost at every fast corner.
  // freerun suppresses the kill so the ring free-runs for the whole measurement
  // window. That is not a measurement mode, it is how the ring's own PERIOD is
  // measured: point the frequency counter at the ring node (cnt_src = 2 in
  // src/project.v) and count it over a known window. Without that, the coarse
  // count would be in units of an interval nobody had measured, and the whole
  // coarse-plus-fine construction would rest on a Liberty number, which is
  // exactly the circularity PLAN.md section 2 forbids for the TDC.
  //
  // THE KILL GUARD
  //
  // If line[1] changed before the sampling flip flops closed, the converter
  // would record a line that the arrival edge never saw, and the error would be
  // a SHORT reading on some dies and not others.
  //
  // The kill is now caused by the capture rather than racing it, so the
  // ordering holds by construction. These two dont_touch buffers stay anyway.
  // They cost two cells, they delay only the shutdown of an instrument whose
  // reading is already latched, and they keep the margin large enough that
  // tools/tdc_race.py can measure it out of extracted timing at every corner
  // instead of asking whether a few picoseconds went the right way.
  wire ring_kill;
  wire kill_d0, kill_d1;
  cell_buf #(.DRIVE(1)) kill_b0 (.A(ring_kill), .X(kill_d0));
  cell_buf #(.DRIVE(1)) kill_b1 (.A(kill_d0),   .X(kill_d1));
  wire run = start & (~kill_d1 | freerun);
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

  // THE ROOT'S FANOUT IS PART OF THE DESIGN, not an afterthought. It was not,
  // and the build measured the cost.
  //
  // The root used to drive the four branch buffers AND the eight flip flops of
  // the coarse capture directly, which is twelve sinks. LibreLane's default max
  // fanout for sky130hd is ten. So the resizer repaired it, by inserting one
  // repeater in front of branches 0 and 1 and leaving branches 2 and 3 direct.
  //
  // That is not a cosmetic asymmetry. From the extracted timing of the build
  // that did it: taps 0 to 15 were sampled 0.52 ns LATER than taps 16 to 31 at
  // the typical corner, and 1.02 ns later at the slow one. The effective
  // threshold of a tap is the line delay to it MINUS the sampling delay to it,
  // so a step in the second is a step in the first, and the bin between tap 15
  // and tap 16 came out 5.08 nominal taps wide at every one of the nine
  // corners. About fifteen percent of the converter's range was one undivided
  // bin, and an arrival landing in it is resolved eight times worse than one
  // landing anywhere else.
  //
  // It stayed MONOTONE only because the repeater happened to land on the LOW
  // half. Had the placer picked branches 2 and 3 instead, the same 0.52 ns
  // would have run the effective thresholds BACKWARDS across four bins, and the
  // thermometer code would not have been a thermometer code. Which two branches
  // get the repeater is not something this design gets to choose.
  //
  // So the fanout is brought under the limit here rather than left for the
  // resizer to fix in whichever way it likes. The coarse capture gets its own
  // branch buffer, exactly like the four tap groups, and the root drives five
  // buffer inputs and nothing else.
  //
  // The coarse branch also buys a correctness improvement that was owed anyway.
  // The coarse count is latched by the arrival edge to the same DEPTH as the
  // fine taps now. Before this it was one buffer level shallower, so the coarse
  // and fine halves of the same reading were taken at instants about a tenth of
  // a nanosecond apart, and the coarse/fine boundary resolution in
  // tdc_decode() assumed they were not.
  wire samp_root;
  cell_buf #(.DRIVE(8)) samp_rt (.A(stop), .X(samp_root));

  wire [GROUPS-1:0] samp;
  genvar b;
  generate
    for (b = 0; b < GROUPS; b = b + 1) begin : sampbuf
      cell_buf #(.DRIVE(2)) u (.A(samp_root), .X(samp[b]));
    end
  endgenerate

  // The fifth branch. Same drive, same depth, same root as the four above.
  wire samp_coarse;
  cell_buf #(.DRIVE(2)) samp_cb (.A(samp_root), .X(samp_coarse));

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
  //
  // THE KILL IS CAUSED BY THE CAPTURE, NOT RACED AGAINST IT.
  //
  // This used to be its own flip flop clocked by samp_root, in parallel with
  // the sampling registers, with two guard buffers behind it to make the
  // ordering comfortable. Extraction says it was not comfortable. Measured on
  // the shipped build, per delay line stage, at every corner:
  //
  //     slow corners    +0.16 to +0.21 ns of margin
  //     typical         -0.02 to +0.01
  //     fast corners    -0.04 to -0.06
  //
  // and the worst stage is always stage 0, because the kill reaches it first.
  // A negative margin means the flip flop sampling tap 0 can latch line[1]
  // AFTER the kill has driven it back to the parked value, which reads as the
  // launch edge not having arrived yet, which is a reading that is SHORT by a
  // tap or two. Systematic, corner dependent, and in the direction that looks
  // like a fast circuit.
  //
  // Adding more buffers would buy margin and would leave it a race. So the kill
  // is taken from `fired` instead, which is the AND of the four branches' own
  // fired flags. Those flags are set by the same edges as the capture registers
  // beside them, so the kill cannot begin until every branch has clocked: the
  // ordering is now clock-to-Q plus an AND tree plus the guard buffers, all of
  // it AFTER the captures, rather than a comparison between two paths that
  // happen to start together.
  //
  // What this gives up: on a trial where one branch fails to fire, `fired`
  // never rises and the ring is not killed early. It still stops, because `run`
  // is gated by `start`, which falls when the window closes. A partial capture
  // is already reported as no arrival, so the trial was void either way; the
  // cost is that the ring runs to the end of that window instead of stopping.
  assign ring_kill = fired;

  // ------------------------------------------------------------ wrap counter
  // Counts full ring periods between launch and arrival. Clocked by the last
  // tap, asynchronously cleared between trials, and SATURATING: an overflowed
  // count would be indistinguishable from a fast path, and reading a saturated
  // count as a measurement is how a slow circuit gets published as a fast one.
  // The host checks for 8'h80, the Gray code of 8'hFF, and discards.
  //
  // AND WHY THE VALUE THAT LEAVES THIS BLOCK IS GRAY CODED
  //
  // The counter lives in the ring's domain and is captured by the arrival edge,
  // which has no relationship to it whatever. A binary counter crossing 0111 to
  // 1000 presents four simultaneously changing bits to that capture, and a
  // capture that lands in the middle of it can return any of sixteen values,
  // including 1111, which is the saturation code. That is not a rare corner: at
  // one ring period per count the counter is changing for a few tens of
  // picoseconds out of every few nanoseconds, and this chip takes many thousands
  // of readings.
  //
  // So a Gray coded copy is registered beside the binary one, from the same
  // next-state value on the same edge, and the Gray copy is what crosses. Only
  // one bit differs between adjacent counts, so a capture taken during a
  // transition returns either the old count or the new one and nothing else.
  //
  // This does not remove metastability, and nothing in an asynchronous capture
  // can. It confines the ambiguity to ADJACENT counts, which is what makes the
  // fine code able to resolve it: the host knows where in the ring the edge was,
  // so it knows which side of the counter's own clock edge the arrival fell on.
  // That resolution is tdc_decode() in harness/evofab/genome.py and it is tested
  // against synthetic captures, including this case.
  //
  // The conversion back to binary is NOT done here. Same reason the thermometer
  // code leaves uncooked: a converter in metal is an opinion that cannot be
  // revised, and the raw Gray value is the diagnostic. gray_to_bin() is three
  // lines of Python and it is covered by tests.
  // WHAT HANGS OFF THE LAST STAGE IS PART OF THE DELAY LINE.
  //
  // line[TAPS] closes the ring, feeds tap 31's sampling flop, clocks the
  // sixteen flip flops of the counter below, and leaves the block as the ring
  // observation output. That load is not the load the other thirty-one stages
  // carry, and the extracted timing said so: the last stage measured 0.393 ns
  // against a 0.124 ns typical stage, so the bin between tap 30 and tap 31 was
  // 3.2 taps wide before anything else was wrong with it.
  //
  // The counter and the observation output do not need to be on the ring node.
  // They are moved behind a buffer, which leaves the ring itself carrying the
  // NAND and one sampling flop like every other stage. The counter now
  // increments one buffer delay later, which moves the coarse/fine boundary
  // window and does not create one: the boundary was always there, it is why
  // the count is Gray coded and why tdc_decode() carries a guard band.
  wire ring_tapped;
  cell_buf #(.DRIVE(4)) ring_tap (.A(line[TAPS]), .X(ring_tapped));

  reg [7:0] wraps;
  reg [7:0] wraps_gray;
  wire [7:0] wraps_nxt = (wraps == 8'hFF) ? 8'hFF : (wraps + 8'd1);
  always @(posedge ring_tapped or negedge clr_n) begin
    if (!clr_n) begin
      wraps      <= 8'h00;
      wraps_gray <= 8'h00;
    end else begin
      wraps      <= wraps_nxt;
      wraps_gray <= wraps_nxt ^ (wraps_nxt >> 1);
    end
  end

  // The coarse count has to be latched by the ARRIVAL edge, exactly like the
  // taps, and not read later in the clock domain. Killing the ring drives
  // line[0] high, and that edge walks down the line and produces one more
  // posedge on line[TAPS] AFTER the measurement is over. Reading the counter
  // later therefore reports one phantom wrap, which is 64 taps of delay that
  // never happened. The tests found this before silicon did: the shortest fixed
  // path in the design reported a full extra ring period.
  reg [7:0] gray_at_arrival;
  always @(posedge samp_coarse or negedge clr_n) begin
    if (!clr_n) gray_at_arrival <= 8'h00;
    else        gray_at_arrival <= wraps_gray;
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
  reg      [7:0] held_gray;
  reg            held_valid;
  reg            fired_last;
  always @(posedge clk) begin
    if (!rst_n) begin
      held       <= {TAPS{1'b0}};
      held_gray  <= 8'h00;
      held_valid <= 1'b0;
      fired_last <= 1'b0;
    end else if (capture) begin
      fired_last <= fired;
      if (fired) begin
        held       <= cap;
        held_gray  <= gray_at_arrival;
        held_valid <= 1'b1;
      end
    end
  end

  assign taps       = held;
  assign wrap_gray  = held_gray;
  assign ring       = ring_tapped;
  assign done       = fired_last;
  assign valid      = held_valid;

endmodule
