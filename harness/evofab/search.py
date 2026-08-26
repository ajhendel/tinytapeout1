"""The outer search loop.

It never sees an input vector. It sees genomes and Trials. That is the whole
architectural point; see harness/README.md.

The GA here is deliberately plain. A clever search would make it harder to tell
whether an effect came from the fabric or from the optimizer, and the questions
this chip is built to answer are about the fabric.
"""

from __future__ import annotations

import dataclasses
import random
import time
from typing import Callable, Iterable, Sequence

from .device import Device, Trial
from .genome import Genome, Globals, OPERATORS, crossover, random_genome


@dataclasses.dataclass
class SearchConfig:
    population: int = 24
    generations: int = 50
    elite: int = 2
    crossover_rate: float = 0.5
    operator_weights: dict[str, float] = dataclasses.field(
        default_factory=lambda: {"function": 1.0, "drive": 1.0,
                                 "load": 1.0, "route": 0.5})
    seed: int = 0
    # Checkpoint every N generations so a crash costs at most that much. The
    # device may be a chip on a bench in a room nobody is in.
    checkpoint_every: int = 5


@dataclasses.dataclass
class SearchState:
    generation: int
    best_genome: Genome
    best_trial: Trial
    evaluations: int


def mutate(g: Genome, rng: random.Random, weights: dict[str, float]) -> Genome:
    names = list(weights)
    op = rng.choices(names, weights=[weights[n] for n in names])[0]
    return OPERATORS[op](g, rng)


def evolve(device: Device,
           n_sites: int,
           cfg: SearchConfig,
           base_globals: Globals | None = None,
           on_generation: Callable[[SearchState], None] | None = None
           ) -> SearchState:
    rng = random.Random(cfg.seed)
    pop = [random_genome(n_sites, rng, base_globals) for _ in range(cfg.population)]

    best_g: Genome | None = None
    best_t: Trial | None = None
    evals = 0

    for gen in range(cfg.generations):
        # One batched call per generation, so a device that can keep its link
        # busy gets the chance to. Never one call per input vector.
        trials = device.evaluate_many(pop)
        evals += len(trials)

        ranked = sorted(zip(pop, trials), key=lambda gt: gt[1].fitness,
                        reverse=True)
        if best_t is None or ranked[0][1].fitness > best_t.fitness:
            best_g, best_t = ranked[0]

        state = SearchState(generation=gen, best_genome=best_g,
                            best_trial=best_t, evaluations=evals)
        if on_generation:
            on_generation(state)

        # Next generation. Elites survive unchanged so the recorded best is
        # always a configuration that was actually measured, not a
        # reconstruction.
        nxt = [g for g, _ in ranked[:cfg.elite]]
        while len(nxt) < cfg.population:
            a = _tournament(ranked, rng)
            if rng.random() < cfg.crossover_rate:
                b = _tournament(ranked, rng)
                child = crossover(a, b, rng)
            else:
                child = a
            child = mutate(child, rng, cfg.operator_weights)
            try:
                child.validate()
            except Exception:
                # A structurally unsafe child is discarded, not repaired.
                # Repairing biases the operator's effect size, which the noise
                # floor study needs to be able to attribute.
                continue
            nxt.append(child)
        pop = nxt

    return SearchState(generation=cfg.generations, best_genome=best_g,
                       best_trial=best_t, evaluations=evals)


def _tournament(ranked: Sequence[tuple[Genome, Trial]], rng: random.Random,
                k: int = 3) -> Genome:
    picks = [rng.randrange(len(ranked)) for _ in range(k)]
    return ranked[min(picks)][0]
