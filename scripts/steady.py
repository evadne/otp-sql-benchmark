#!/usr/bin/env python3
"""Run duration-controlled sustained trials, retaining pilots and every failure."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def validate(row, seconds, warmup, window, workers):
    assert row['seconds'] == seconds and row['elapsed_seconds'] >= seconds
    assert row['warmup_seconds'] == warmup and row['window_seconds'] == window
    assert row['schedulers'] == row['schedulers_online'] == 10
    assert len(row['worker_counts']) == workers
    assert sum(row['worker_counts']) == row['transactions'] > 0
    assert math.isclose(row['tps'], row['transactions'] / row['elapsed_seconds'])
    assert row['errors'] is None if row['mode'] == 'sql' else row['errors'] == 0
    if window:
        assert len(row['windows']) == seconds // window
        assert sum(w['transactions'] for w in row['windows']) == row['transactions']
        for index, sample in enumerate(row['windows']):
            assert sample['start_seconds'] == index * window
            assert sample['end_seconds'] == (index + 1) * window
            assert sum(sample['worker_counts']) == sample['transactions']
            assert math.isclose(sample['api_started_tps'], sample['transactions'] / window)
        for worker in range(workers):
            assert sum(w['worker_counts'][worker] for w in row['windows']) == row['worker_counts'][worker]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.seconds < 60 or args.seconds % 10 or args.warmup < 10 or args.repeats < 3:
        parser.error('Require >=60 seconds in multiples of 10, >=10 seconds warmup and >=3 repeats')
    if Path(args.name).name != args.name:
        parser.error('Use a single result directory name')
    os.chdir(ROOT)
    destination = ROOT / 'results' / args.name
    modes = ['ecto', 'postgrex', 'epgsql', 'postgrex_held', 'epgsql_batch', 'sql', 'no_io']
    pilots = [('pilot', mode, 0) for mode in modes]
    trials = [('measurement', mode, repeat) for repeat in range(1, args.repeats + 1) for mode in modes]
    rng = random.Random(20260918)
    rng.shuffle(pilots)
    rng.shuffle(trials)
    jobs = [{'sequence': i, 'phase': phase, 'mode': mode, 'repeat': repeat}
            for i, (phase, mode, repeat) in enumerate(pilots + trials, 1)]
    manifest = {'seconds': args.seconds, 'warmup_seconds': args.warmup, 'window_seconds': 10,
                'pilot_seconds': 5, 'schedulers': 10, 'workers': 40, 'repeats': args.repeats,
                'server_deployment': os.environ.get('BENCH_PG_BACKEND', 'native'),
                'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [ROOT / 'mix.lock', *sorted((ROOT / 'lib').glob('*.ex'))]},
                'jobs': jobs}
    if args.resume:
        assert json.loads((destination / 'plan.json').read_text()) == manifest
        attempts = [json.loads(line) for line in (destination / 'attempts.jsonl').read_text().splitlines()]
    else:
        destination.mkdir(parents=True, exist_ok=False)
        (destination / 'plan.json').write_text(json.dumps(manifest, indent=2) + '\n')
        attempts = []
    done = {attempt['sequence'] for attempt in attempts}
    estimates = {a['mode']: math.ceil(a['measurement']['tps'] * args.seconds)
                 for a in attempts if a['phase'] == 'pilot' and a['status'] == 'ok'}
    with (destination / 'attempts.jsonl').open('a') as output:
        for job in jobs:
            if job['sequence'] in done:
                continue
            seconds = 5 if job['phase'] == 'pilot' else args.seconds
            window = 0 if job['phase'] == 'pilot' else 10
            pool = 10 if job['mode'] in ('sql', 'no_io') else 40
            env = os.environ | {'ERL_FLAGS': '+S 10:10 +SDcpu 2 +SDio 2',
                'BENCH_MODE': job['mode'], 'WORKERS': '40', 'POOL_SIZE': str(pool),
                'WARMUP_SECONDS': str(args.warmup), 'SECONDS_PER_RUN': str(seconds),
                'WINDOW_SECONDS': str(window), 'REPEATS': '1'}
            log = destination / f"{job['sequence']:03}-{job['phase']}-{job['mode']}-r{job['repeat']}.log"
            if log.exists():
                raise RuntimeError(f'Unrecorded prior log exists; preserve and inspect before resuming: {log}')
            record = job | {'started_at_utc': datetime.now(timezone.utc).isoformat(),
                            'pilot_expected_transactions': estimates.get(job['mode']), 'log': log.name}
            try:
                completed = subprocess.run(['mix', 'run', '--no-compile', '--no-deps-check', 'run.exs'],
                    env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    timeout=args.warmup + seconds + 120)
                log.write_text(completed.stdout)
                if completed.returncode:
                    raise RuntimeError(f'Client exited {completed.returncode}')
                rows = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith('{"')]
                assert len(rows) == 1
                row = rows[0]
                validate(row, seconds, args.warmup, window, 40)
                assert row['pool_size'] == pool and row['mode'] == job['mode']
                record |= {'status': 'ok', 'measurement': row}
                if job['phase'] == 'pilot':
                    estimates[job['mode']] = math.ceil(row['tps'] * args.seconds)
                print(f"{job['sequence']}/{len(jobs)} {job['phase']} {job['mode']} r{job['repeat']}: "
                      f"{row['transactions']:,} transactions / {row['elapsed_seconds']:.3f}s = "
                      f"{row['tps']:,.0f}/s; pilot predicts {estimates.get(job['mode'], 'unknown')}", flush=True)
            except subprocess.TimeoutExpired as error:
                captured = error.stdout or b''
                log.write_text(captured.decode(errors='replace') if isinstance(captured, bytes) else captured)
                record |= {'status': 'failed', 'error': f'Process timeout after {error.timeout}s'}
            except (RuntimeError, AssertionError, ValueError) as error:
                record |= {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
            record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
            output.write(json.dumps(record) + '\n')
            output.flush()
            if record['status'] != 'ok':
                print(f"{job['sequence']}/{len(jobs)} FAILED {job['mode']}: {record['error']} (retained; no automatic retry)", flush=True)
    print('Plan finished. Summarise successful and failed attempts together.', flush=True)


if __name__ == '__main__':
    main()
