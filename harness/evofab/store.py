"""Results database.

One row per trial, in SQLite, with the reproducibility metadata that the design
review asked for on EVERY row rather than in a run header. A run header is
enough right up to the moment two runs get merged, a firmware is changed
mid-run, or a die is swapped, and then it is silently wrong for everything that
came after.

The table is append only in use. There is no update path in this module on
purpose. A correction is a new row with a note, matching the pre-registration
discipline in PLAN.md.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Iterable, Iterator

from .device import Trial
from .genome import Genome

SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,
    trial_index       INTEGER NOT NULL,
    config_hash       TEXT    NOT NULL,
    n_sites           INTEGER NOT NULL,
    payload_hex       TEXT    NOT NULL,
    fitness           REAL    NOT NULL,
    components_json   TEXT    NOT NULL,
    device_id         TEXT    NOT NULL,
    firmware_version  TEXT    NOT NULL,
    temperature_proxy REAL,
    supply_mv         INTEGER,
    tripped           INTEGER NOT NULL,
    crc_ok            INTEGER NOT NULL,
    wall_time_s       REAL    NOT NULL,
    unix_time         REAL    NOT NULL,
    holdout           INTEGER NOT NULL DEFAULT 0,
    notes             TEXT
);
CREATE INDEX IF NOT EXISTS trials_config ON trials(config_hash);
CREATE INDEX IF NOT EXISTS trials_run    ON trials(run_id);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    started     REAL NOT NULL,
    git_commit  TEXT,
    device_id   TEXT,
    purpose     TEXT,
    config_json TEXT
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        new = not os.path.exists(path)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        if new:
            self.conn.execute("PRAGMA journal_mode=WAL")

    # ------------------------------------------------------------------ runs
    def start_run(self, run_id: str, device_id: str, purpose: str,
                  git_commit: str | None = None, config: dict | None = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
            (run_id, time.time(), git_commit, device_id, purpose,
             json.dumps(config or {})))
        self.conn.commit()

    # ---------------------------------------------------------------- trials
    def record(self, run_id: str, genome: Genome, trial: Trial,
               holdout: bool = False) -> None:
        self.conn.execute(
            "INSERT INTO trials (run_id, trial_index, config_hash, n_sites, "
            "payload_hex, fitness, components_json, device_id, "
            "firmware_version, temperature_proxy, supply_mv, tripped, crc_ok, "
            "wall_time_s, unix_time, holdout, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, trial.trial_index, trial.config_hash, genome.n_sites,
             f"{genome.payload():x}", trial.fitness,
             json.dumps(trial.components), trial.device_id,
             trial.firmware_version, trial.temperature_proxy, trial.supply_mv,
             int(trial.tripped), int(trial.crc_ok), trial.wall_time_s,
             time.time(), int(holdout), trial.notes))

    def commit(self) -> None:
        self.conn.commit()

    # -------------------------------------------------------------- analysis
    def repeats(self, config_hash: str, device_id: str | None = None
                ) -> list[float]:
        """Every fitness ever recorded for one configuration on one device.

        This is the primitive the noise-floor study is built on. Fitness
        differences smaller than three times the spread of this list are not
        resolvable, and docs/THROUGHPUT.md requires mutation operators to be
        sized above it.
        """
        q = "SELECT fitness FROM trials WHERE config_hash=?"
        args: list = [config_hash]
        if device_id:
            q += " AND device_id=?"
            args.append(device_id)
        return [r[0] for r in self.conn.execute(q, args)]

    def noise_floor(self, device_id: str | None = None,
                    min_repeats: int = 30) -> dict:
        """Trial-to-trial spread, per configuration, over configurations with
        enough repeats to say anything. Returns the median and worst spread."""
        q = ("SELECT config_hash, COUNT(*), AVG(fitness), "
             "AVG(fitness*fitness) FROM trials")
        args: list = []
        if device_id:
            q += " WHERE device_id=?"
            args.append(device_id)
        q += " GROUP BY config_hash HAVING COUNT(*) >= ?"
        args.append(min_repeats)
        sigmas = []
        for _, n, mean, meansq in self.conn.execute(q, args):
            var = max(0.0, meansq - mean * mean) * n / (n - 1)
            sigmas.append(var ** 0.5)
        if not sigmas:
            return {"configs": 0}
        sigmas.sort()
        return {
            "configs": len(sigmas),
            "median_sigma": sigmas[len(sigmas) // 2],
            "worst_sigma": sigmas[-1],
            "min_resolvable_difference": 3 * sigmas[len(sigmas) // 2],
        }

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
