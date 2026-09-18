#!/usr/bin/env bash
set -euo pipefail
hostname
uname -a
lscpu
cat /proc/self/status
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/memory.max
elixir --version
docker inspect beam-sql-bench-20260918-pg
docker image inspect postgres:16
docker exec beam-sql-bench-20260918-pg psql -p 55432 -U postgres -d postgres \
  -c 'SELECT version()' -c 'SHOW fsync' -c 'SHOW synchronous_commit' \
  -c 'SHOW full_page_writes' -c 'SHOW max_connections' -c 'SHOW log_statement'
