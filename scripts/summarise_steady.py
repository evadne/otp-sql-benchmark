#!/usr/bin/env python3
"""Validate and summarise sustained trials, including pilots and failures."""
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
import sys

from steady import ROOT, validate


def median(values):
    return statistics.median(values) if values else None


def fairness(row):
    counts = row['worker_counts']
    return sum(counts) ** 2 / (len(counts) * sum(c*c for c in counts))


def number(value, decimals=0):
    return '—' if value is None else f'{value:,.{decimals}f}'


def main():
    directory = ROOT / 'results' / (sys.argv[1] if len(sys.argv) > 1 else 'steady-60s')
    plan = json.loads((directory / 'plan.json').read_text())
    attempts = [json.loads(line) for line in (directory / 'attempts.jsonl').read_text().splitlines()]
    assert len(attempts) == len(plan['jobs'])
    assert [a['sequence'] for a in attempts] == list(range(1, len(attempts) + 1))
    grouped = defaultdict(list)
    pilots = {}
    baseline = {}
    fields = ('deps', 'elixir', 'otp', 'erts', 'cpu_affinity', 'pg_host',
              'schedulers', 'schedulers_online', 'dirty_cpu_schedulers', 'workers', 'pool_size')
    for suite, modes in [('native-matrix', ('sql', 'epgsql', 'no_io')),
                         ('native-pool-sweep', ('postgrex', 'ecto')),
                         ('native-controls', ('postgrex_held', 'epgsql_batch'))]:
        for line in (ROOT / 'results' / suite / 'results.jsonl').read_text().splitlines():
            row = json.loads(line)
            pool = 10 if row['mode'] in ('sql', 'no_io') else 40
            if (row['mode'] in modes and row['workers'] == 40 and
                    row['schedulers'] == 10 and row['pool_size'] == pool):
                baseline.setdefault(row['mode'], []).append(row)
    for attempt, job in zip(attempts, plan['jobs']):
        assert all(attempt[key] == value for key, value in job.items())
        assert (directory / attempt['log']).exists()
        if attempt['phase'] == 'measurement':
            grouped[attempt['mode']].append(attempt)
        if attempt['status'] != 'ok':
            assert attempt['status'] == 'failed' and attempt['error']
            continue
        row = attempt['measurement']
        seconds = plan['pilot_seconds'] if attempt['phase'] == 'pilot' else plan['seconds']
        window = 0 if attempt['phase'] == 'pilot' else plan['window_seconds']
        validate(row, seconds, plan['warmup_seconds'], window, plan['workers'])
        old = baseline[row['mode']]
        assert len(old) == 3
        assert all(row[field] == old[0][field] for field in fields), row['mode']
        if attempt['phase'] == 'pilot':
            pilots[row['mode']] = row
        else:
            assert row['seconds'] >= 60
            if row['mode'] in pilots:
                assert attempt['pilot_expected_transactions'] == math.ceil(pilots[row['mode']]['tps'] * seconds)
    summaries = []
    for mode, trials in sorted(grouped.items()):
        assert len(trials) == plan['repeats']
        assert {t['repeat'] for t in trials} == set(range(1, plan['repeats'] + 1))
        rows = [t['measurement'] for t in trials if t['status'] == 'ok']
        pilot = pilots.get(mode)
        short = median([r['tps'] for r in baseline[mode]])
        sustained = median([r['tps'] for r in rows])
        first = median([r['windows'][0]['api_started_tps'] for r in rows])
        last = median([r['windows'][-1]['api_started_tps'] for r in rows])
        summaries.append({'mode': mode, 'connections': 10 if mode in ('sql', 'no_io') else 40,
            'successful_repeats': len(rows), 'failed_repeats': len(trials) - len(rows),
            'pilot_tps': pilot['tps'] if pilot else None,
            'pilot_expected_transactions': math.ceil(pilot['tps'] * plan['seconds']) if pilot else None,
            'median_actual_transactions': median([r['transactions'] for r in rows]),
            'short_median_tps': short, 'sustained_median_tps': sustained,
            'change_percent': (sustained / short - 1) * 100 if rows else None,
            'min_tps': min((r['tps'] for r in rows), default=None),
            'max_tps': max((r['tps'] for r in rows), default=None),
            'min_elapsed_seconds': min((r['elapsed_seconds'] for r in rows), default=None),
            'max_elapsed_seconds': max((r['elapsed_seconds'] for r in rows), default=None),
            'max_drain_seconds': max((r['drain_seconds'] for r in rows), default=None),
            'first_window_median_api_started_tps': first,
            'last_window_median_api_started_tps': last,
            'last_vs_first_percent': (last / first - 1) * 100 if first else None,
            'max_window_api_overrun_seconds': max((w['last_api_finished_seconds'] - w['end_seconds']
                                                    for r in rows for w in r['windows']), default=None),
            'min_jain_fairness': min(map(fairness, rows), default=None),
            'min_worker_transactions': min((min(r['worker_counts']) for r in rows), default=None)})
    with (directory / 'summary.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=summaries[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(summaries)
    windows = []
    for attempt in attempts:
        if attempt['phase'] != 'measurement' or attempt['status'] != 'ok':
            continue
        for window in attempt['measurement']['windows']:
            windows.append({'mode': attempt['mode'], 'repeat': attempt['repeat'],
                            **{k: v for k, v in window.items() if k != 'worker_counts'},
                            'min_worker_transactions': min(window['worker_counts'])})
    if windows:
        with (directory / 'windows.csv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=windows[0].keys(), lineterminator='\n')
            writer.writeheader()
            writer.writerows(windows)
    failures = [a for a in attempts if a['status'] != 'ok']
    lines = [f"# Sustained {plan['seconds']}-second trials", '',
             f"Ten schedulers, forty callers, {plan['warmup_seconds']}-second per-worker warmup, "
             f"{plan['repeats']} attempts per configuration.",
             'Duration controls stopping; pilot counts are estimates only. Final drains and overruns are timed.',
             'The five-second native reference used two-second warmup. This comparison changes both warmup',
             'and measurement duration; it is not an isolated causal estimate of duration.', '',
             f"{sum(a['phase'] == 'measurement' and a['status'] == 'ok' for a in attempts)} successful sustained trials; "
             f"{sum(a['phase'] == 'measurement' and a['status'] != 'ok' for a in attempts)} failed sustained attempts; "
             f"{len(pilots)} successful short pilots. Every attempt is retained; no automatic retries.", '',
             '| Mode | Connections | Successful/attempted | Five-second median/s | Sustained median/s | Change | Sustained range/s |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"| {r['mode']} | {r['connections']} | {r['successful_repeats']}/{plan['repeats']} | "
                     f"{number(r['short_median_tps'])} | {number(r['sustained_median_tps'])} | "
                     f"{number(r['change_percent'], 1)}% | {number(r['min_tps'])}–{number(r['max_tps'])} |")
    lines += ['', 'The no-I/O control is not SQL TPS. sql has local API return plus a final fence;',
              'the other database modes await responses. Combined BEGIN/COMMIT is not a callback API.', '',
              '## Counts and elapsed time', '',
              '| Mode | Pilot expected count | Actual count (median) | Actual elapsed range/s | Max drain/s | Worst fairness |',
              '|---|---:|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"| {r['mode']} | {number(r['pilot_expected_transactions'])} | {number(r['median_actual_transactions'])} | "
                     f"{number(r['min_elapsed_seconds'], 3)}–{number(r['max_elapsed_seconds'], 3)} | "
                     f"{number(r['max_drain_seconds'], 4)} | {number(r['min_jain_fairness'], 3)} |")
    lines += ['', '## Within-run windows', '',
              'Rates group completed API operations by their start window, not server commit timestamp.',
              'An operation spanning boundaries is assigned once to its start window. Windows do not',
              'reconnect or fence. Counts are published after all operations and the final fence complete.',
              'Latest API completion time exposes window overruns; full-run drained TPS is the headline.',
              'First/last values are medians across successful repeats; they do not prove stationarity.', '',
              '| Mode | First 10s median/s | Last 10s median/s | Last vs first | Max API window overrun/s | Fewest transactions per worker in full run |',
              '|---|---:|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"| {r['mode']} | {number(r['first_window_median_api_started_tps'])} | "
                     f"{number(r['last_window_median_api_started_tps'])} | {number(r['last_vs_first_percent'], 1)}% | "
                     f"{number(r['max_window_api_overrun_seconds'], 3)} | {number(r['min_worker_transactions'])} |")
    lines += ['', '[All windows](windows.csv), [raw attempts](attempts.jsonl), [plan and source hashes](plan.json).', '',
              '## Unsuccessful attempts', '']
    lines += [f"- {a['phase']} {a['mode']} repeat {a['repeat']}: {a['error']} ([log]({a['log']}))" for a in failures] or ['None.']
    (directory / 'summary.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
