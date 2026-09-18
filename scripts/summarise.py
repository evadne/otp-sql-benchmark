#!/usr/bin/env python3
"""Validate measurements and produce medians, full repeat ranges and fairness."""
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
import sys

root = Path(__file__).resolve().parents[1]
directories = [root / "results" / name for name in (sys.argv[1:] or ["matrix", "pool-sweep"])]
for directory in directories:
    rows = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    plan = json.loads((directory / "plan.json").read_text())
    assert len(rows) == len(plan), (directory, len(rows), len(plan))
    groups = defaultdict(list)
    for row in rows:
        assert row["schedulers"] == row["schedulers_online"]
        assert len(row["worker_counts"]) == row["workers"]
        assert sum(row["worker_counts"]) == row["transactions"] > 0
        assert row["elapsed_seconds"] >= row["seconds"]
        assert math.isclose(row["tps"], row["transactions"] / row["elapsed_seconds"])
        assert row["errors"] is None if row["mode"] == "sql" else row["errors"] == 0
        groups[(row["mode"], row["schedulers"], row["workers"], row["pool_size"])].append(row)
    summary = []
    for (mode, schedulers, workers, pool), measurements in sorted(groups.items()):
        assert {row["repeat"] for row in measurements} == {1, 2, 3}
        rates = [row["tps"] for row in measurements]
        fairness = [sum(r["worker_counts"]) ** 2 /
                    (workers * sum(c*c for c in r["worker_counts"])) for r in measurements]
        summary.append({"mode": mode, "schedulers": schedulers, "workers": workers,
                        "connections": pool, "median_tps": statistics.median(rates),
                        "min_tps": min(rates), "max_tps": max(rates),
                        "min_jain_fairness": min(fairness),
                        "min_worker_completions": min(min(r["worker_counts"]) for r in measurements),
                        "max_drain_seconds": max(r["drain_seconds"] for r in measurements)})
    with (directory / "summary.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)
    lines = ["| Mode | Schedulers | Callers | Connections | Median/s | Range/s | Worst fairness |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        lines.append(f"| {r['mode']} | {r['schedulers']} | {r['workers']} | {r['connections']} | "
                     f"{r['median_tps']:,.0f} | {r['min_tps']:,.0f}–{r['max_tps']:,.0f} | "
                     f"{r['min_jain_fairness']:.3f} |")
    (directory / "summary.md").write_text("\n".join(lines) + "\n")
    print(directory.name, len(rows), "valid measurements")
    print("\n".join(lines))
