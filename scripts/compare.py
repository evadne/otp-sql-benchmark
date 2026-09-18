#!/usr/bin/env python3
"""Compare matched native reruns with the retained Docker baseline.

Repeat-range overlap is descriptive, not a significance test or a causal
estimate of Docker overhead. Measurements were collected sequentially.
"""
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics
import sys

root = Path(__file__).resolve().parents[1]
prefix = sys.argv[1] if len(sys.argv) > 1 else "native"

def load(name):
    directory = root / "results" / name
    rows = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    assert len(rows) == len(json.loads((directory / "plan.json").read_text()))
    groups = defaultdict(list)
    for row in rows:
        assert sum(row["worker_counts"]) == row["transactions"]
        groups[(row["mode"], row["schedulers"], row["workers"], row["pool_size"])].append(row)
    for group in groups.values():
        assert len(group) == 3 and {r["repeat"] for r in group} == {1, 2, 3}
    return groups

def fairness(row):
    counts = row["worker_counts"]
    return sum(counts) ** 2 / (len(counts) * sum(c*c for c in counts))

comparisons = []
for suite in ("matrix", "pool-sweep", "controls"):
    baseline = load(suite)
    native = load(f"{prefix}-{suite}")
    assert baseline.keys() == native.keys(), suite
    for key in sorted(baseline):
        previous, current = baseline[key], native[key]
        for field in ("deps", "elixir", "otp", "erts", "seconds", "cpu_affinity",
                      "pg_host", "dirty_cpu_schedulers", "schedulers_online"):
            assert all(r[field] == previous[0][field] for r in previous + current), (key, field)
        assert all(r["server_deployment"] == "native" for r in current)
        old = [r["tps"] for r in previous]
        new = [r["tps"] for r in current]
        old_median, new_median = statistics.median(old), statistics.median(new)
        overlap = "overlap"
        if min(new) > max(old):
            overlap = "native above"
        elif max(new) < min(old):
            overlap = "native below"
        mode, schedulers, workers, connections = key
        comparisons.append({"suite": suite, "mode": mode, "schedulers": schedulers,
            "workers": workers, "connections": connections,
            "docker_median_tps": old_median, "native_median_tps": new_median,
            "change_percent": (new_median / old_median - 1) * 100,
            "docker_min_tps": min(old), "docker_max_tps": max(old),
            "native_min_tps": min(new), "native_max_tps": max(new),
            "repeat_ranges": overlap,
            "docker_min_fairness": min(map(fairness, previous)),
            "native_min_fairness": min(map(fairness, current)),
            "native_min_worker_completions": min(min(r["worker_counts"]) for r in current)})

with (root / "results" / f"{prefix}-comparison.csv").open("w") as stream:
    writer = csv.DictWriter(stream, fieldnames=comparisons[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(comparisons)
lines = ["# Native PostgreSQL versus the retained Docker baseline", "",
         "Three repeats per configuration. Changes compare medians. Range labels compare",
         "observed repeats only; they are not confidence intervals or causal estimates.", ""]
for suite in ("matrix", "pool-sweep", "controls"):
    lines += [f"## {suite}", "",
              "| Mode | Schedulers | Callers | Connections | Docker/s | Native/s | Change | Repeat ranges |",
              "|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in comparisons:
        if r["suite"] != suite:
            continue
        lines.append(f"| {r['mode']} | {r['schedulers']} | {r['workers']} | {r['connections']} | "
                     f"{r['docker_median_tps']:,.0f} | {r['native_median_tps']:,.0f} | "
                     f"{r['change_percent']:+.1f}% | {r['repeat_ranges']} |")
    lines.append("")
(root / "results" / f"{prefix}-comparison.md").write_text("\n".join(lines))
print(f"Compared {len(comparisons)} configurations ({len(comparisons)*3} measurements per deployment).")
print("\n".join(lines))
