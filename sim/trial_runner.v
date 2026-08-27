// Batch trial runner. Reads scan frames, runs one bounded trial each, writes
// results.
//
// This exists so the harness can score genomes against the ACTUAL Verilog that
// will be fabricated, not against the Python model in harness/evofab/device.py.
// The two are written from the spec independently; when they disagree, one of
// them is wrong about the chip, and finding that out now costs nothing.
//
// It is also a rehearsal for the real link. One invocation processes a whole
// batch of frames, which is the same discipline docs/THROUGHPUT.md demands of
// the firmware: never a host round trip per input vector.
//
// Usage:
//   iverilog -DSIM -DN_SITES=8 -g2012 -o build/runner.vvp src/*.v sim/trial_runner.v
//   vvp build/runner.vvp +frames=frames.txt +out=results.txt
//
// frames.txt  one hex frame per line, MSB first when shifted
// results.txt one line per frame:
//             index crc_ok inert tripped out00 out01 out10 out11 freq_byte

`default_nettype none
`timescale 1ns / 1ps

`ifndef N_SITES
  `define N_SITES 8
`endif

module trial_runner;

  localparam integer N_SITES  = `N_SITES;
  localparam integer CHAIN_W  = 32 + 12 * N_SITES + 8;  // GLOBAL_W is 32
  localparam integer MAX_BITS = 1024;

  reg        clk = 1'b0;
  // Starts high so that driving it low produces a real falling edge. An
  // asynchronous reset that is already low at time zero never fires in an event
  // simulator, which leaves anything relying on it at X. On a board the reset is
  // a genuine transition; the testbench should not be the reason it looks fine.
  reg        rst_n = 1'b1;
  reg        ena = 1'b1;
  reg  [7:0] ui = 8'h00;
  reg  [7:0] uio_i = 8'h00;
  wire [7:0] uo, uio_o, uio_oe;

  tt_um_ajhendel_evofab dut (
      .ui_in(ui), .uo_out(uo), .uio_in(uio_i), .uio_out(uio_o),
      .uio_oe(uio_oe), .ena(ena), .clk(clk), .rst_n(rst_n));

  always #5 clk = ~clk;

  // Pin positions, kept in one place so a change cannot drift between here and
  // harness/evofab/genome.py.
  localparam SCAN_EN = 0, SCAN_IN = 1, LOAD = 2, ARM = 3;
  localparam FAB_A = 4, FAB_B = 5;

  integer fin, fout, code, idx;
  reg [MAX_BITS-1:0] frame;
  reg [7:0] res_out;
  reg crc_ok, inert, tripped;
  integer a, b, i;
  reg [3:0] truth;
  reg [7:0] freq_byte;
  reg [1023:0] frames_path, out_path;

  task do_reset;
    begin
      rst_n = 1'b1;
      ui = 8'h00;
      @(posedge clk);
      rst_n = 1'b0;
      repeat (5) @(posedge clk);
      rst_n = 1'b1;
      @(posedge clk);
    end
  endtask

  task shift_in;
    input [MAX_BITS-1:0] f;
    integer k;
    begin
      ui[ARM] = 1'b1;
      ui[SCAN_EN] = 1'b1;
      for (k = CHAIN_W - 1; k >= 0; k = k - 1) begin
        ui[SCAN_IN] = f[k];
        @(posedge clk);
      end
      ui[SCAN_EN] = 1'b0;
      ui[SCAN_IN] = 1'b0;
      @(posedge clk);
    end
  endtask

  task pulse_load;
    begin
      ui[LOAD] = 1'b1;
      repeat (2) @(posedge clk);
      ui[LOAD] = 1'b0;
      @(posedge clk);
    end
  endtask

  initial begin
    if (!$value$plusargs("frames=%s", frames_path)) begin
      $display("ERROR: need +frames=<path>");
      $finish;
    end
    if (!$value$plusargs("out=%s", out_path)) begin
      $display("ERROR: need +out=<path>");
      $finish;
    end
    fin = $fopen(frames_path, "r");
    fout = $fopen(out_path, "w");
    if (fin == 0 || fout == 0) begin
      $display("ERROR: could not open files");
      $finish;
    end

    idx = 0;
    forever begin
      code = $fscanf(fin, "%h\n", frame);
      if (code != 1) begin
        $fclose(fin);
        $fclose(fout);
        $finish;
      end

      do_reset;
      shift_in(frame);
      crc_ok = uo[1];
      pulse_load;
      inert = uo[7];

      // Four input vectors, scored on the far side of the link. The host never
      // sees them.
      truth = 4'b0000;
      i = 0;
      for (a = 0; a <= 1; a = a + 1)
        for (b = 0; b <= 1; b = b + 1) begin
          ui[FAB_A] = a[0];
          ui[FAB_B] = b[0];
          repeat (3) @(posedge clk);
          truth[i] = uo[2];
          i = i + 1;
        end

      // Let the measurement window close so the frequency count is captured.
      // The capture pulses inside the gate tail, then the readout register
      // takes another clock, so wait past both rather than exactly on the edge.
      while (uo[4]) @(posedge clk);
      repeat (10) @(posedge clk);
      freq_byte = uio_o;
      tripped = uo[5];

      $fwrite(fout, "%0d %0d %0d %0d %0d %0d %0d %0d %0d\n",
              idx, crc_ok, inert, tripped,
              truth[0], truth[1], truth[2], truth[3], freq_byte);
      idx = idx + 1;
    end
  end

endmodule
