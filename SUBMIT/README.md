# SUBMIT — everything left, in order

Ten steps, five of them yours. Deadline **2026-09-07 20:00 UTC**.

Absolute path to this folder:
`/Users/andrewhendel/CascadeProjects/tinytapeout1/SUBMIT/`

The design is finished and verified. Nothing in this list is engineering. It is
a license, a visibility switch, a login, a card, and a board.

---

## 1. Add a LICENSE  (yours, 2 minutes)

There is no LICENSE file. **Tiny Tapeout requires open source.** Their own
template ships Apache-2.0 and that is the recommendation, but the choice is
yours because it is a legal one.

Easiest route, in the browser:

> github.com/ajhendel/tinytapeout1 → **Add file** → **Create new file** →
> type `LICENSE` in the name box → a **"Choose a license template"** button
> appears on the right → **Apache License 2.0** → Commit.

Or from the terminal:

    cd /Users/andrewhendel/CascadeProjects/tinytapeout1
    curl -sL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE
    git add LICENSE && git commit -m "Apache-2.0" && git push

## 2. Make the repository public  (yours, 1 minute)

> github.com/ajhendel/tinytapeout1 → **Settings** → **General** → scroll to
> **Danger Zone** → **Change visibility** → **Make public**

This is not optional and it is not only about CI. Three things depend on it:

- **CI runners.** Actions stopped giving this repo runners on 2026-08-28; every
  workflow now fails in three seconds with zero steps. Public repos do not
  consume the Actions quota.
- **The `viewer` job**, which has failed on every build ever run here, because
  GitHub Pages needs a public repo.
- **The pre-registration.** `predictions/` only means something if its
  timestamp is public before the dies exist. Read
  `/Users/andrewhendel/CascadeProjects/tinytapeout1/predictions/README.md`
  under "Status" before you cite it in any paper. **This step is the earlier
  deadline**, not September 7.

Already done for you: cross-program references stripped from four files,
credential scan clean. The repo has been written as public-ready throughout.

## 3. Watch CI go green  (mine, ~20 minutes after step 2)

Push anything, or re-run the last workflow. Expect `gds`, `precheck`,
`gl_test`, `build_reports`, `submission_gate` and now also `viewer` to pass.

Tell me when step 2 is done and I will confirm the run and read the reports.

## 4. Get the price  (yours, 5 minutes)

    https://app.tinytapeout.com/calculator

Login required, which is why this has stayed yours since the start. Enter
**6x2 tiles, sky130, shuttle ttsky26c, 0 analog pins**.

Expect roughly **840 EUR** (12 tiles at about 70 EUR). Early-bird discounts
exist and are limited to individuals. Confirm the real number before budgeting;
the public pages do not carry it.

## 5. Submit  (yours, 10 minutes)

    https://app.tinytapeout.com

Sign in with GitHub → the **ttsky26c** shuttle → add a project → give it the
repository `ajhendel/tinytapeout1`. It reads `info.yaml` for the title,
description, tile count, top module and pinout. All of those are already
correct; there is nothing to type.

**Before you pay, check the box in `STATE.md` next to this folder.** If any gate
in it is not green, stop and tell me.

## 6. Pay  (yours)

## 7. Order one iCE40 board  (yours, whenever)

Separate from the shuttle, for the FPGA control arm during the months of
fabrication lead time. Either works:

- Lattice iCEstick, part `ICE40HX1K-STICK-EVN`, roughly 40 to 50 USD
- UP5K breakout, more logic

See `/Users/andrewhendel/CascadeProjects/tinytapeout1/docs/FPGA_PILOT.md`.

## 8 to 10. After submission

Silicon is typically six to nine months out. The bring-up order is written and
waiting in
`/Users/andrewhendel/CascadeProjects/tinytapeout1/docs/MEASUREMENT_PROTOCOL.md`,
stages A to E. Nothing about it needs deciding now.

---

## What NOT to do

- **Do not submit before the repo is public and CI is green.** The gates check
  things that cannot be checked after fabrication.
- **Do not commit anything to `predictions/` after submission.** That directory
  is append-only from the deadline onward, and a correction is a NEW file that
  names the file it corrects. The whole point is that it cannot be edited once
  the answers exist.
- **Do not describe the predictions as "pre-registered" until the repo has been
  public for a while.** If publication happens after the dies arrive, that
  directory is worth nothing and has to be described that way.
