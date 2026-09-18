#!/usr/bin/env python3
"""Run each cell in a fresh VM, serially, with reproducible shuffled order."""
import json
import os
from pathlib import Path
import random
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)
arguments = sys.argv[1:]
resume = "--resume" in arguments
arguments = [arg for arg in arguments if arg != "--resume"]
destination = root / "results" / (arguments[0] if arguments else "matrix")
if not resume:
    destination.mkdir(parents=True, exist_ok=False)
modes = ["postgrex", "ecto", "epgsql", "sql"]
if len(arguments) > 1 and arguments[1] == "pool":
    cells = [(mode, 10, 40, pool) for mode in ("postgrex", "ecto")
             for pool in (1, 4, 10, 20, 40)]
elif len(arguments) > 1 and arguments[1] == "controls":
    cells = [(mode, 10, 40, 40) for mode in ("epgsql_batch", "postgrex_held")]
else:
    cells = [(mode, 10, workers, 10) for mode in modes for workers in (1, 10, 40)]
    cells += [(mode, schedulers, 40, schedulers) for mode in modes for schedulers in (8, 16)]
    cells += [("no_io", schedulers, 40, schedulers) for schedulers in (8, 10, 16)]
    cells += [(mode, 10, 10, 10) for mode in ("postgrex_held", "epgsql_batch")]
jobs = [(repeat, *cell) for repeat in (1, 2, 3) for cell in cells]
random.Random(20260918).shuffle(jobs)
completed_count = 0
if resume:
    assert json.loads((destination / "plan.json").read_text()) == [list(job) for job in jobs]
    previous = [json.loads(line) for line in (destination / "results.jsonl").read_text().splitlines()]
    assert len(previous) <= len(jobs)
    for index, row in enumerate(previous, 1):
        repeat, mode, schedulers, workers, _ = jobs[index - 1]
        assert (row["sequence"], row["repeat"], row["mode"], row["schedulers"], row["workers"]) == (index, repeat, mode, schedulers, workers)
    completed_count = len(previous)
else:
    (destination / "plan.json").write_text(json.dumps(jobs, indent=2) + "\n")
with (destination / "results.jsonl").open("a" if resume else "w") as results:
    for index, (repeat, mode, schedulers, workers, pool) in enumerate(jobs, 1):
        if index <= completed_count:
            continue
        log = destination / f"{index:03}-{mode}-s{schedulers}-w{workers}-p{pool}-r{repeat}.log"
        if log.exists():
            attempt = 1
            while log.with_suffix(f".previous-{attempt}.log").exists():
                attempt += 1
            retained = log.with_suffix(f".previous-{attempt}.log")
            log.rename(retained)
            print(f"Retained prior unsuccessful attempt: {retained.name}", flush=True)
        env = os.environ | {
            "ERL_FLAGS": f"+S {schedulers}:{schedulers} +SDcpu 2 +SDio 2",
            "BENCH_MODE": mode, "WORKERS": str(workers),
            "POOL_SIZE": str(pool), "WARMUP_SECONDS": "2",
            "SECONDS_PER_RUN": "5", "REPEATS": "1",
        }
        completed = subprocess.run(
            ["mix", "run", "--no-compile", "--no-deps-check", "run.exs"],
            env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=150,
        )
        log.write_text(completed.stdout)
        if completed.returncode:
            raise RuntimeError(f"Failed cell: {log}\n{completed.stdout}")
        rows = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith('{"')]
        if len(rows) != 1:
            raise RuntimeError(f"Expected exactly one measurement: {log}")
        row = rows[0] | {"repeat": repeat, "sequence": index,
                         "server_deployment": os.environ.get("BENCH_PG_BACKEND", "native")}
        results.write(json.dumps(row) + "\n")
        results.flush()
        print(f"{index}/{len(jobs)} {mode} S={schedulers} W={workers} P={pool}: "
              f"{row['tps']:,.0f}/s; drain={row['drain_seconds']:.4f}s", flush=True)
