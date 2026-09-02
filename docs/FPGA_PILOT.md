# FPGA_PILOT — what runs on which FPGA, and why

WP3 from HANDOFF.md. Written 2026-08-26 after checking what is actually
available rather than assuming.

## The two platforms are not interchangeable

**Lattice iCE40** (iCEstick or iCE40-UP5K breakout, roughly 30 to 60 USD, open
toolchain yosys plus nextpnr plus icestorm).

**AWS F2** (f2.6xlarge, 24 vCPU, 256 GiB, one AMD Virtex UltraScale+ VU47P,
1.98 USD per hour on demand in us-east-1, quota confirmed at 64 vCPU in both
us-east-1 and us-west-2 on the author's account; FPGA Developer AMI (Ubuntu)
1.19.2 available with Vivado licensed for use on F instances).

The difference that decides everything is the bitstream. IceStorm has reverse
engineered the iCE40 bitstream completely, which is the reason the entire modern
intrinsic evolvable hardware line exists on that part (Bitstream Evolution, IEEE
Access 2025; Whitley et al., ALIFE 2021). The UltraScale+ bitstream is closed.
No amount of money makes a VU47P do Thompson-style bitstream evolution.

## Assignment

| WP3 item | Platform | Reason |
|---|---|---|
| 1. Harness end to end | already done in simulation, then iCE40 | The harness is written; see harness/. The real trials-per-second number needs a real link, and the link we are rehearsing is a small MCU talking to a chip, which an iCEstick models and a cloud FPGA does not |
| 2. Logical fabric emulation | iCE40 first, **F2 for scale** | 64 sites fits an iCE40. Thousands of sites do not, and testing the genome validator and mutation operators at a scale well beyond the ASIC is exactly what a VU47P is for |
| 3. Real coupled ring oscillators | iCE40 primary, F2 optional | Both parts permit combinational loops (iCE40 natively, UltraScale+ with ALLOW_COMBINATORIAL_LOOPS). The iCE40 gives more direct access with less shell between the design and the silicon, and it is the part the field publishes on |
| 4. p-bit prototype | iCE40 | Same reason. Also cheap enough to leave running for days of autocorrelation data |
| 5. TDC dry run | iCE40 | Needs bench instruments physically attached. A cloud FPGA has no bench |
| 6. Noise floor methodology | iCE40 | Needs the same physical part repeatedly over hours, with a temperature covariate |
| 7. Sabotage transfer pilot | iCE40 | Needs overclocking to the marginal edge, which the AWS shell does not expose |
| 8. Evaluate Bitstream Evolution | neither, desk work | Read the toolkit before building anything it already provides |

## Verdict on F2

F2 is warranted for **item 2 at scale**, and is a reasonable supplement for item
3. It is the wrong tool for items 1, 4, 5, 6 and 7, all of which need a physical
part on a bench that can be overclocked, probed and left running.

It is also not the current bottleneck. The gating unknown right now is the area
result from the Tiny Tapeout CI run, which is free. Starting an F2 starts an
hourly clock against work that is not blocked.

The recommendation is therefore: order the iCE40 board, and start F2 when WP3
item 2 is running at 64 sites on the iCE40 and we want to know what happens at
1,000.

Two further notes on F2 before anyone starts.

- The F2 flow is not "load a bitstream". Custom Logic is built against the AWS
  shell with `aws_build_dcp_from_cl.sh`, which is hours of Vivado, then uploaded
  to S3, then turned into an AFI by AWS, which is another hour or so, and only
  then loaded onto a running instance. Budget most of a day for the first one.
- A plain compute instance, not F2, is the right shape for the SPICE corner
  sweeps that WP5 pre-registration needs. Those want cores, not an FPGA.

## Cost hygiene

`tools/aws/launch_f2.sh` launches at most one instance, tagged
`Project=tinytapeout1` and `CostCenter=tinytapeout1-personal` so this spend is
separable from everything else in the account, with a lease baked into the
instance by two independent mechanisms and shutdown behavior set to terminate.
An expired lease then costs nothing at all rather than costing EBS. The script
refuses to start a second instance while one exists.

    AWS_PROFILE=<profile> tools/aws/launch_f2.sh --list
    AWS_PROFILE=<profile> LEASE_HOURS=8 tools/aws/launch_f2.sh
    AWS_PROFILE=<profile> tools/aws/launch_f2.sh --terminate

The account is a separate research account of the author's and it is named in
`~/.aws/config`, not here. This repository is published, that account is not
part of this project, and the only thing crossing the boundary is compute. The
`Project` and `CostCenter` tags are what keep the bill separable.

## What Andrew has to do

Order one iCE40 board. Either works; the UP5K breakout has more logic and the
iCEstick is the part the published replications use.

- Lattice iCEstick Evaluation Kit, part ICE40HX1K-STICK-EVN, roughly 40 to 50
  USD from Mouser or Digi-Key.
- Lattice iCE40 UP5K breakout, part ICE40UP5K-B-EVN, roughly 50 to 60 USD, same
  distributors.

Recommendation is the **iCEstick**, because the Bitstream Evolution toolkit and
the published tone-discriminator replications target it, so we inherit their
working configuration instead of debugging our own.
