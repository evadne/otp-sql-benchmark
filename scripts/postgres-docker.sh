#!/usr/bin/env bash
set -euo pipefail
docker run -d --name beam-sql-bench-20260918-pg \
  --label purpose=beam-sql-bench-20260918 --network host \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=beam_bench \
  --tmpfs /var/lib/postgresql/data:rw,size=2g \
  postgres@sha256:e17e86066e5ef83e0952a9347f5c792b7ece00972e2aa787a6986f471b3dd3d5 \
  -p 55432 -c max_connections=200 -c listen_addresses=127.0.0.1 \
  -c unix_socket_directories=/var/run/postgresql -c log_statement=none
for attempt in {1..60}; do
  if docker exec beam-sql-bench-20260918-pg pg_isready -p 55432 -U postgres; then
    exit 0
  fi
  sleep 1
done
exit 1
