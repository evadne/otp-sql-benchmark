#!/usr/bin/env bash
# Disposable native PostgreSQL; no Docker or default system cluster involved.
set -euo pipefail
test "$(id -u)" -eq 0
pg_bin="${BENCH_PG_BIN:-/usr/lib/postgresql/16/bin}"
pg_root="${BENCH_PG_ROOT:-/srv/beam-sql-bench-native}"
pg_data="$pg_root/data"
pg_port="${PGPORT:-55432}"

case "${1:-start}" in
  start)
    test -x "$pg_bin/postgres"
    install -d -o postgres -g postgres -m 0750 "$pg_root" "$pg_root/socket"
    if [ -f "$pg_data/PG_VERSION" ]; then
      echo "Existing cluster at $pg_data; refusing to replace it" >&2
      exit 1
    fi
    install -d -o postgres -g postgres -m 0700 "$pg_data"
    if ! mountpoint -q "$pg_data"; then
      mount -t tmpfs -o "size=2g,mode=0700,uid=$(id -u postgres),gid=$(id -g postgres)" \
        tmpfs "$pg_data"
    fi
    runuser -u postgres -- "$pg_bin/initdb" -D "$pg_data" \
      --username=postgres --auth=trust --encoding=UTF8 --locale=en_US.utf8
    runuser -u postgres -- "$pg_bin/pg_ctl" -D "$pg_data" -l "$pg_root/server.log" \
      -o "-p $pg_port -c max_connections=200 -c listen_addresses=127.0.0.1 -c unix_socket_directories=$pg_root/socket -c log_statement=none" \
      -w start
    "$pg_bin/createdb" -h 127.0.0.1 -p "$pg_port" -U postgres beam_bench
    ;;
  stop)
    runuser -u postgres -- "$pg_bin/pg_ctl" -D "$pg_data" -m fast -w stop
    umount "$pg_data"
    ;;
  status)
    runuser -u postgres -- "$pg_bin/pg_ctl" -D "$pg_data" status
    ;;
  *) echo "Usage: $0 [start|stop|status]" >&2; exit 2 ;;
esac
