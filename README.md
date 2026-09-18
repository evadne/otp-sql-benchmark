# Empty SQL transactions on the BEAM

Reproduce a 190,000 transactions/s question with explicit completion semantics.
See `REPORT.md` for measured results. Dependencies are pinned in `mix.lock`.

## Workloads

| Mode | Operation | Completion boundary | Connections |
|---|---|---|---|
| `postgrex` | `Postgrex.transaction(pool, fn _ -> :empty end)` | Server COMMIT response, checkout each time | Configured pool |
| `ecto` | `Repo.transact(fn -> {:ok, :empty} end)` | Server COMMIT response, checkout each time | Configured pool |
| `epgsql` | `epgsql:with_transaction` | Server COMMIT response | One dedicated connection per worker |
| `sql` | `SQL.transaction do :ok end` | Local API return; final SELECT fence timed separately | One per scheduler, library default |
| `postgrex_held` | Postgrex transaction inside worker-long `DBConnection.run` | Server COMMIT response; checkout amortised | One held connection per worker |
| `epgsql_batch` | Simple query `BEGIN; COMMIT` | Server response to combined request | One dedicated connection per worker |
| `no_io` | DBConnection transaction with no-I/O callbacks | Local callback/pool control; **not SQL TPS** | Configured pool |

The SQL 0.5.0 library is unmodified. Its `use SQL` macro opens a database at
compilation time; this harness uses the equivalent sigil attributes and imports
instead, and starts the normal SQL application/pool before measurement.
SQL's API does not return commit errors to this caller; its error count is `null`,
not an asserted zero. A final SELECT on each worker's cached connection establishes
an ordering fence, but does not retroactively provide per-transaction error handling.

## Method

- Linux Incus container on Hercules. Client and PostgreSQL share eight physical
  AMD EPYC 9684X cores with SMT; 16 allowed logical CPUs. This is a container
  baseline, not a measurement on ten dedicated physical cores.
- BEAM normal schedulers: 8, 10, 16. Two dirty CPU and two dirty I/O schedulers
  are configured separately. 10 is the reference claim, not a tuning recommendation.
- Same-host TCP loopback, TLS off, PostgreSQL 16.15. `fsync`,
  `synchronous_commit`, and `full_page_writes` stay on. The disposable database
  lives on tmpfs; empty transactions do not test write durability or storage TPS.
- Fresh VM per cell. Connections, compilation and two-second per-worker warmup
  are excluded. Workers rendezvous, then receive a common future start/deadline.
- Each worker checks monotonic time each transaction, keeps a private count,
  verifies the expected return, and reports once. No central counter, latency
  histogram or per-operation logging is on the hot path.
- Five-second measurement windows, three repetitions in a fixed shuffled order.
  In-flight operations and the final drain can overrun the deadline: **their full
  time is included**. API and drained rates are retained separately. Warmup SQL
  queues are fenced before the measurement barrier.
- Exceptions/incorrect returns fail the run. The harness never turns failed
  operations into throughput. Per-worker counts expose starvation rather than
  presenting aggregate throughput alone.
- The 10-scheduler matrix varies callers (1, 10, 40); the 8/16 comparison fixes
  callers at 40. Postgrex/Ecto pools follow scheduler count in the main matrix.
  The additional pool sweep fixes 10 schedulers and 40 callers while varying
  connections 1/4/10/20/40. `sql` hard-wires pool size to scheduler count;
  changing it independently would require changing the library.

## Reproduce

Use Linux, Docker, Python 3.9+, Elixir 1.19.5 and OTP 28.3.2. On codex-test-2:

```sh
export PATH=/root/.asdf/installs/elixir/1.19.5-otp-28/bin:/root/.asdf/installs/erlang/28.3.2/bin:$PATH
export ERL_FLAGS='+S 10:10 +SDcpu 2 +SDio 2'
bash scripts/postgres.sh
mix deps.get
mix compile --warnings-as-errors
mix format --check-formatted
mix run -e 'BeamSqlBench.audit()'
bash scripts/environment.sh > results/environment.txt
python3 scripts/matrix.py another-matrix
python3 scripts/matrix.py another-pool-sweep pool
python3 scripts/matrix.py another-controls controls
python3 scripts/completion_probe.py another-audit
python3 scripts/count_audit.py another-audit
python3 scripts/summarise.py another-matrix another-pool-sweep another-controls
```

Each run directory must be new. Keep the raw JSONL and per-cell logs. For a
single longer case:

```sh
BENCH_MODE=postgrex WORKERS=40 POOL_SIZE=10 SECONDS_PER_RUN=30 REPEATS=5 mix run run.exs
```

Keep held connections at least as numerous as workers for `postgrex_held`.
`PGHOST` accepts a numeric IPv4 address and `PGPORT` defaults to 55432.
Run the completion probe and count audit serially after performance work.
The probe temporarily withholds every server response through a local TCP proxy;
only `sql` is expected to return while responses are blocked.
The count audit logs a bounded 10,000-transaction run and subtracts a zero-operation
startup control. It waits for an independent log marker to ensure Docker has
delivered the complete log, then requires exact BEGIN/COMMIT counts and no errors.
Logging is reset before returning. `bash scripts/qualify.sh RUN_NAME` performs
the complete validation/matrix sequence in new result directories.

When finished, stop/remove only the dedicated benchmark container. Its database
is disposable; the source and raw results live outside Docker.

## Primary sources

- [SQL 0.5.0 transaction macro](https://github.com/elixir-dbvisor/sql/blob/v0.5.0/lib/sql.ex#L104)
- [SQL PostgreSQL adapter](https://github.com/elixir-dbvisor/sql/blob/v0.5.0/lib/adapters/postgres.ex)
- [SQL pool](https://github.com/elixir-dbvisor/sql/blob/v0.5.0/lib/pool.ex)
- [Postgrex transaction API](https://hexdocs.pm/postgrex/0.22.4/Postgrex.html#transaction/3)
- [epgsql transaction API](https://github.com/epgsql/epgsql/blob/4.8.0/src/epgsql.erl)
- [PostgreSQL connection architecture](https://www.postgresql.org/docs/16/tutorial-arch.html)
