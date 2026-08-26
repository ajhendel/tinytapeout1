#!/usr/bin/env python3
"""Drive one search run against a device, recording every trial.

    python3 harness/run_search.py --device icarus --target XOR --generations 20
    python3 harness/run_search.py --noise-floor 200 --device icarus

Crash recovery is by construction rather than by a checkpoint file. Every trial
is committed to SQLite as it happens, with the run id, so a run that dies
halfway leaves a complete record of everything it did measure. Resuming is
starting a new run and reading the old rows, which is also what you want when
the thing that died was the chip rather than the script.
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evofab.device import IcarusDevice, SimDevice
from evofab.genome import Globals, random_genome
from evofab.search import SearchConfig, evolve
from evofab.store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def make_device(name: str, n_sites: int, target: str):
    if name == "sim":
        return SimDevice(target=target, n_sites=n_sites)
    if name == "icarus":
        return IcarusDevice(n_sites=n_sites, target=target, repo_root=ROOT)
    raise SystemExit(f"unknown device {name}")


def cmd_search(args, store: Store, device) -> None:
    run_id = f"{args.device}-{args.target}-{int(time.time())}"
    store.start_run(run_id, device.device_id, f"evolve {args.target}",
                    git_commit(), vars(args))

    cfg = SearchConfig(population=args.population, generations=args.generations,
                       seed=args.seed)
    seen: dict[str, int] = {}

    # Everything the search evaluates is recorded, not only the winners.
    # A record of winners cannot answer what the search rejected and why, and it
    # cannot support a noise floor estimate at all.
    orig = device.evaluate_many

    def recording_evaluate_many(genomes):
        trials = orig(genomes)
        for g, t in zip(genomes, trials):
            store.record(run_id, g, t)
            seen[t.config_hash] = seen.get(t.config_hash, 0) + 1
        store.commit()
        return trials

    device.evaluate_many = recording_evaluate_many  # type: ignore[method-assign]

    t0 = time.perf_counter()

    def report(state):
        if state.generation % 5 == 0 or state.generation == cfg.generations - 1:
            rate = state.evaluations / max(1e-9, time.perf_counter() - t0)
            print(f"gen {state.generation:>4}  best {state.best_trial.fitness:.4f}  "
                  f"evals {state.evaluations:>6}  {rate:6.1f} trials/s")

    final = evolve(device, args.sites, cfg,
                   base_globals=Globals(window_exp=2, trans_exp=15),
                   on_generation=report)

    elapsed = time.perf_counter() - t0
    print()
    print(f"run_id      {run_id}")
    print(f"evaluations {final.evaluations} in {elapsed:.1f}s "
          f"= {final.evaluations / elapsed:.1f} trials/s")
    print(f"best        {final.best_trial.fitness:.4f} "
          f"{final.best_trial.components}")
    print(f"config      {final.best_trial.config_hash}")
    for i, s in enumerate(final.best_genome.sites):
        print(f"  site {i}  {s.describe()}")

    # The projection docs/THROUGHPUT.md cares about.
    print()
    print(f"At this rate a 100,000 evaluation search takes "
          f"{100_000 / (final.evaluations / elapsed) / 60:.1f} minutes.")
    print("Note this is a simulation rate, not a hardware rate. The number that "
          "settles docs/THROUGHPUT.md comes from a board.")


def cmd_noise_floor(args, store: Store, device) -> None:
    """Repeat identical configurations and report the resolvable difference.

    This is the methodology rehearsal for WP3 item 6. On a simulator the answer
    is trivially zero spread, and that is the point: it proves the pipeline
    computes what it claims before the number means anything, so that when a
    real device gives a nonzero spread we know the machinery was already right.
    """
    run_id = f"noise-{device.device_id}-{int(time.time())}"
    store.start_run(run_id, device.device_id, "noise floor", git_commit(),
                    vars(args))
    rng = random.Random(args.seed)
    configs = [random_genome(args.sites, rng,
                             Globals(calib_en=1, calib_sel=i % 4,
                                     window_exp=2, trans_exp=15))
               for i in range(4)]

    reps = args.noise_floor
    for r in range(reps):
        for t, g in zip(device.evaluate_many(configs), configs):
            store.record(run_id, g, t)
        if r % 25 == 0:
            store.commit()
            print(f"  repeat {r}/{reps}")
    store.commit()

    print()
    for g in configs:
        vals = store.repeats(g.config_hash(), device.device_id)
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
        print(f"{g.config_hash()}  n={len(vals):>4}  mean={mean:.6f}  "
              f"sigma={var ** 0.5:.6f}")
    print()
    print("noise floor summary:", store.noise_floor(device.device_id,
                                                    min_repeats=reps // 2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="icarus", choices=["sim", "icarus"])
    ap.add_argument("--target", default="AND",
                    choices=["AND", "OR", "XOR", "XNOR", "NAND", "NOR"])
    ap.add_argument("--sites", type=int, default=8)
    ap.add_argument("--population", type=int, default=24)
    ap.add_argument("--generations", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--db", default=os.path.join(ROOT, "build", "trials.db"))
    ap.add_argument("--noise-floor", type=int, default=0,
                    help="run the noise floor study with this many repeats")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    device = make_device(args.device, args.sites, args.target)
    with Store(args.db) as store:
        if args.noise_floor:
            cmd_noise_floor(args, store, device)
        else:
            cmd_search(args, store, device)


if __name__ == "__main__":
    main()
