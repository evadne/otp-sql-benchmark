#!/usr/bin/env python3
"""Count explicit server-executed BEGIN/COMMIT statements in a bounded SQL run.

Database-wide xact_commit includes internal/background transactions, so it is
not used as an exact counter for this workload. Statement logging is enabled
only for this audit, then reset before performance measurements.
"""
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

root = Path(__file__).resolve().parents[1]
destination = root / 'results' / sys.argv[1] if len(sys.argv) > 1 else root / 'results'
destination.mkdir(parents=True, exist_ok=True)
if (destination / 'count-audit.json').exists():
    raise FileExistsError('Choose a new output directory to preserve the existing audit')
container = 'beam-sql-bench-20260918-pg'

def psql(query):
    subprocess.run(['docker', 'exec', container, 'psql', '-XAt', '-p', '55432',
                    '-U', 'postgres', '-d', 'postgres', '-c', query], check=True,
                   stdout=subprocess.DEVNULL)

def trial(count):
    since = datetime.now(timezone.utc).isoformat()
    env = os.environ | {'BENCH_MODE': 'sql', 'WORKERS': '10', 'AUDIT_COUNT': str(count),
                        'ERL_FLAGS': '+S 10:10 +SDcpu 2 +SDio 2'}
    completed = subprocess.run(
        ['mix', 'run', '--no-compile', '--no-deps-check', '-e', 'BeamSqlBench.count_audit()'],
        cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=120, check=True)
    # Docker's log collector can lag behind the completed client. Wait for an
    # independent server-log barrier, rather than stopping at an expected count.
    marker = 'BEAM_SQL_AUDIT_BARRIER_' + uuid.uuid4().hex
    psql("DO $$ BEGIN RAISE LOG '" + marker + "'; END $$")
    deadline = time.monotonic() + 10
    while True:
        log = subprocess.check_output(['docker', 'logs', '--since', since, container],
                                      stderr=subprocess.STDOUT)
        if marker.encode() in log:
            break
        if time.monotonic() > deadline:
            raise RuntimeError('Docker did not deliver the server-log barrier')
        time.sleep(0.1)
    path = destination / f'count-audit-{count}-postgres.log.gz'
    path.write_bytes(gzip.compress(log, mtime=0))
    lines = log.decode().splitlines()
    record = {'api_transactions': count * 10,
              'begins': sum(bool(re.search(r'LOG:  execute .*: begin$', x)) for x in lines),
              'commits': sum(bool(re.search(r'LOG:  execute .*: commit$', x)) for x in lines),
              'server_errors': [x for x in lines if re.search(r'\] (ERROR|FATAL|PANIC):', x)],
              'server_log': path.name, 'client_log': completed.stdout}
    return record

psql("ALTER DATABASE beam_bench SET log_statement = 'all'")
try:
    control = trial(0)
    measured = trial(1000)
finally:
    psql('ALTER DATABASE beam_bench RESET log_statement')
record = {'zero_transaction_control': control, 'measured': measured,
          'net_server_commits': measured['commits'] - control['commits']}
(destination / 'count-audit.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
assert control['begins'] == control['commits'] == 1, record
assert measured['begins'] == measured['commits'] == 10001, record
assert record['net_server_commits'] == measured['api_transactions'], record
assert not control['server_errors'] and not measured['server_errors'], record
