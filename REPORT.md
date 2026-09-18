# BEAM empty transaction results — 18 September 2026

**Yes: epgsql exceeded 190K server-acknowledged empty transactions/s with ten
BEAM schedulers.** Sending `BEGIN; COMMIT` as one simple-query request achieved
**261,492/s median** across three runs (259,508–262,926/s), using 40 callers and
40 connections. The client waits for the response. This is a specialised empty
transaction operation; it does not provide a callback between BEGIN and COMMIT.

Schultzer's unmodified **sql 0.5.0** achieved **482,214/s including a final drain**
at ten schedulers and 40 callers, with ten configured connections. A bounded
server-log audit confirmed all 10,000 submitted transactions executed and
committed without server errors. Its throughput advantage is real in this
workload, but its transaction call returns before acknowledgement and its
caller distribution was severely unfair.

## Ten schedulers, forty callers

Three five-second runs per row, preceded by two-second per-worker warmup.
Median and full observed repeat range; no confidence interval is claimed.

| Library / operation | Connections | Median transactions/s | Repeat range | Completion contract |
|---|---:|---:|---:|---|
| Ecto SQL 3.14.0 / `Repo.transact` | 40 | 108,407 | 107,517–109,757 | Per-transaction server acknowledgement |
| Postgrex 0.22.4 / `transaction` | 40 | 116,197 | 115,657–116,269 | Per-transaction server acknowledgement |
| epgsql 4.8.0 / `with_transaction` | 40 | 139,391 | 138,552–139,427 | Per-transaction server acknowledgement |
| Postgrex, connection held across worker loop | 40 | 143,981 | 142,298–144,403 | Per-transaction acknowledgement; checkout amortised |
| epgsql, one request containing `BEGIN; COMMIT` | 40 | **261,492** | 259,508–262,926 | Server acknowledgement of combined request |
| sql 0.5.0 / empty transaction macro | 10 | **482,214** | 454,265–491,102 | Local return; final per-worker SELECT fence included |

The standard callback APIs tested did not reach 190K here. The acknowledged
single-request operation did. Those findings should be reported together with
connection count and the completion boundary, rather than as one library ranking.

## Connection count is a material factor

This sweep fixes **10 schedulers and 40 callers**, varying only the configured
pool size. Each database connection has a PostgreSQL backend process. This
changes both client-pool contention and available server concurrency; the
experiment does not attribute the gain exclusively to either component.

| Connections | Postgrex median/s | Ecto median/s |
|---:|---:|---:|
| 1 | 9,757 | 9,402 |
| 4 | 35,534 | 33,755 |
| 10 | 83,398 | 72,610 |
| 20 | 106,283 | 98,633 |
| 40 | 116,197 | 108,407 |

Increasing the pool from 10 to 40 connections raised Postgrex throughput by
39% and Ecto by 49%. Separately, epgsql's single-request control rose from
155,699/s at 10 callers/connections to 261,492/s at 40; both caller and connection
counts change in that comparison. Parallel-query workers are not involved in
these empty transactions.

## What sql's result means

The response-blocking probe placed a transparent TCP proxy between each client
and PostgreSQL, warmed the connection, then withheld **all server responses for
two seconds** while continuing to forward requests.

| Operation | Returned while responses were blocked? | Call duration |
|---|---|---:|
| sql empty transaction | Yes | 13 microseconds |
| Postgrex transaction | No | 2.001 seconds |
| Ecto transaction | No | 2.001 seconds |
| epgsql transaction | No | 2.003 seconds |

Zero server bytes were forwarded during each gate. This confirms the distinction
in the [transaction macro's source](https://github.com/elixir-dbvisor/sql/blob/v0.5.0/lib/sql.ex#L104):
it receives a local BEGIN notification and sends COMMIT without awaiting its
server response. This concerns ordinary COMMIT acknowledgement, not PostgreSQL
two-phase commit.

The benchmark fences each worker's cached connection with `SELECT 1` after
warmup and after measurement. Final fence time and any operation completing
after the nominal deadline are included in the denominator. The result therefore
does not simply abandon a queue of outstanding transactions when the clock stops.
However, a fence does not add per-transaction error reporting to this API; its
error-count field remains `null` rather than an asserted zero.

The independent bounded audit logged **10,001 BEGINs and 10,001 COMMITs**, versus
one of each for startup alone: exactly **10,000 workload transactions**, with
no PostgreSQL ERROR/FATAL/PANIC messages. Raw logs are retained compressed.

Fairness is a separate problem. In every 40-caller sql run at ten schedulers,
some workers completed just **one transaction** during the nominal five-second
window, while others completed hundreds of thousands. Jain's fairness index
was 0.222–0.224 (1 means equal counts), versus approximately 1 for the synchronous
rows. The three sql runs took about 5.58–5.68 seconds including overruns. Aggregate
throughput should not be interpreted as uniformly low per-caller latency.

The released library fixes connection count to scheduler count. Source inspection
also shows that its cached random connection selection excludes the last slot:
the hash range is pool size minus one. Thus ten configured connections provide
at most nine selected slots. No library code was changed for these experiments.
The Hex-installed transaction and adapter sources were hash-checked against
the v0.5.0 Git tag and match.

## Eight, ten and sixteen schedulers

Forty callers throughout. Postgrex/Ecto/sql pools follow scheduler count; epgsql
retains forty dedicated connections. Consequently the first three columns
measure a combined scheduler/pool change, not an isolated scheduler effect.

| Schedulers | Postgrex/s | Ecto/s | sql drained/s | epgsql/s |
|---:|---:|---:|---:|---:|
| 8 | 65,519 | 62,441 | 396,302 | 140,333 |
| 10 | 83,827 | 72,071 | 482,214 | 139,391 |
| 16 | 104,577 | 96,186 | 555,113 | 132,127 |

A no-I/O DBConnection adapter produced 391,541 local transactions/s at ten
schedulers. This is a control for callback and pool overhead, **not SQL database
throughput**. Empty real transactions still exercise the driver, protocol,
sockets, PostgreSQL backends and OS scheduling.

## Environment and limits

- Hercules, codex-test-2 Incus container; AMD EPYC 9684X. CPU affinity
  `32-39,224-231`: **eight physical cores with SMT**, 16 logical CPUs.
- Client BEAM and PostgreSQL share that allocation. No CPU quota; no Incus
  allocation was changed. This is not a ten-dedicated-physical-core result.
- Elixir 1.19.5; OTP 28.3.2 / ERTS 16.2.1; normal schedulers explicitly fixed
  with `+S N:N`; dirty CPU/I/O schedulers fixed at two each.
- PostgreSQL 16.15, pinned Docker digest; loopback TCP, TLS off, no external
  connection pooler. `fsync`, `synchronous_commit`, `full_page_writes` on.
- Disposable PostgreSQL storage on tmpfs. No application reads/writes inside
  the measured transactions. These results do not establish durable-write TPS.
- **111 measured cells**, fresh VM per cell, three repetitions per configuration,
  serial execution with a retained shuffled plan. SQL assignment randomness
  remains part of the released library's behaviour. These are finite baseline
  measurements, not a long-running saturation or tail-latency study.
- The dedicated PostgreSQL container was stopped and removed after capture.
  The Linux harness and evidence remain at `/srv/beam-sql-bench-20260918` for reuse.

## Evidence and reproduction

The [README](README.md) contains exact operations and commands. Dependencies,
container digest and environment are frozen. The initial harness checkpoint is
`d84d8f1`; completion checks and the main matrix were retained in `69133fb`.

- [Main scheduler/caller matrix](results/matrix/summary.md),
  [raw measurements](results/matrix/results.jsonl)
- [Connection sweep](results/pool-sweep/summary.md),
  [raw measurements](results/pool-sweep/results.jsonl)
- [Acknowledged controls](results/controls/summary.md),
  [raw measurements](results/controls/results.jsonl)
- [Response-blocking probe](results/completion-probe.json)
- [Exact server-log audit](results/count-audit.json)
- [Full host and container environment](results/environment.txt)

The retained `count-audit-initial.json` is an unsuccessful early attempt to use
the database-wide transaction counter. That counter includes internal/background
work and cannot serve as this workload's exact count. It is superseded by the
log audit, which waits for an independent server-log marker before counting;
Docker's log collector can lag behind client completion.
