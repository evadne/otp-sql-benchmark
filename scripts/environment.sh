#!/usr/bin/env bash
set -euo pipefail
pg_bin="${BENCH_PG_BIN:-/usr/lib/postgresql/16/bin}"
pg_root="${BENCH_PG_ROOT:-/srv/beam-sql-bench-native}"
hostname
uname -a
lscpu
cat /proc/self/status
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.max
elixir --version
dpkg-query -W postgresql-16 postgresql-client-16 postgresql-common libpq5 libc6 libssl3t64
"$pg_bin/postgres" --version
sha256sum "$pg_bin/postgres" mix.lock lib/bench.ex lib/sql_client.ex
findmnt -T "$pg_root/data"
cat "$pg_root/data/postmaster.opts"
pg_pid=$(head -n 1 "$pg_root/data/postmaster.pid")
cat "/proc/$pg_pid/status"
cat "/proc/$pg_pid/cgroup"
"$pg_bin/psql" -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "${PGPORT:-55432}" -U postgres -d postgres \
  -c 'SELECT version()' -c 'SHOW fsync' -c 'SHOW synchronous_commit' \
  -c 'SHOW full_page_writes' -c 'SHOW max_connections' -c 'SHOW log_statement' \
  -c 'SHOW shared_buffers' -c 'SHOW ssl' \
  -c "SELECT datname, datcollate, datctype FROM pg_database WHERE datname = 'beam_bench'" \
  -c 'SELECT name, setting, unit, source FROM pg_settings ORDER BY name'
