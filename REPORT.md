# BEAM empty transaction results — 18 September 2026

**Native PostgreSQL reached 257,560 server-acknowledged empty transactions/s
with ten BEAM schedulers.** epgsql sent `BEGIN; COMMIT` as one request, using
40 callers and 40 connections. All three repeats exceeded 190K/s
(256,299–259,540/s). The ordinary callback transaction APIs tested stayed below
190K/s. This preserves the original finding with PostgreSQL installed directly
in codex-test-2, without Docker.

The native rerun completed **111 successful measurements plus one unsuccessful
SQL attempt**, compared with the retained 111-measurement Docker baseline.
Removing Docker produced mixed changes across the matrix, with no consistent
throughput improvement. The main ten-scheduler/forty-caller medians were
0.6–1.5% lower. These sequential measurements do not isolate Docker overhead.

## Native versus Docker: ten schedulers, forty callers

Three successful five-second measurements per row, each after two-second
per-worker warmup. Final drains and measurement overruns remain timed.
Connections and completion contracts match between deployments.

| Library / operation | Connections | Docker median/s | Native median/s | Change | Native repeat range/s |
|---|---:|---:|---:|---:|---:|
| Ecto transaction | 40 | 108,407 | 107,038 | -1.3% | 106,959–107,734 |
| Postgrex transaction | 40 | 116,197 | 115,278 | -0.8% | 115,127–115,412 |
| epgsql callback transaction | 40 | 139,391 | 138,028 | -1.0% | 137,555–138,236 |
| Postgrex, held connection | 40 | 143,981 | 142,686 | -0.9% | 141,975–145,349 |
| epgsql, acknowledged `BEGIN; COMMIT` | 40 | 261,492 | 257,560 | -1.5% | 256,299–259,540 |
| sql, local return plus final drain | 10 | 482,214 | 479,359 | -0.6% | 469,488–479,620 |

Observed repeat ranges overlap for four of these six rows; native Postgrex and
epgsql callback ranges are below their original ranges. Neither overlap nor
separation across three repeats is a significance test.

## Trend differences

**Connection count remains a material factor.** At fixed ten schedulers and
forty callers, increasing the pool from ten to forty connections raised native
Postgrex throughput by 54% and Ecto by 56%, versus 39% and 49% in the original
sweep. The larger relative gains partly reflect lower native ten-connection
medians, not higher forty-connection results.

| Connections | Postgrex Docker/s | Postgrex native/s | Change | Ecto Docker/s | Ecto native/s | Change |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 9,757 | 9,868 | +1.1% | 9,402 | 9,056 | -3.7% |
| 4 | 35,534 | 36,631 | +3.1% | 33,755 | 32,538 | -3.6% |
| 10 | 83,398 | 74,976 | -10.1% | 72,610 | 68,597 | -5.5% |
| 20 | 106,283 | 105,461 | -0.8% | 98,633 | 97,153 | -1.5% |
| 40 | 116,197 | 115,278 | -0.8% | 108,407 | 107,038 | -1.3% |

The largest median decrease was Postgrex with ten connections in this sweep:
−10.1%, with native repeats spanning 73,326–84,124/s. Its separately scheduled
main-matrix entry at the same settings instead rose 0.8% to 84,528/s. That
variation limits attribution of either difference to deployment. Both
Postgrex and Ecto increase monotonically with pool size in both sweeps.

**Scheduler trends are preserved.** At forty callers, native epgsql with forty
connections measured 138,324/s, 138,028/s and 130,110/s with 8, 10 and 16
schedulers: sixteen again performed worse than eight or ten. Postgrex, Ecto
and sql still rose as schedulers and their pools increased together. That is
a combined scheduler/pool change, not evidence of an isolated scheduler effect.
The largest positive shift was epgsql's single-caller entry (+8.1%); Postgrex
at eight schedulers/forty callers rose 7.7%, while Ecto there fell 4.5%.

**Control drift is small but present.** The no-I/O DBConnection control moved
+1.4%, +1.1% and −0.9% at 8, 10 and 16 schedulers. It does not use PostgreSQL,
so those shifts cannot be PostgreSQL container overhead. It remains a local
callback/pool control, not a SQL TPS result.

## Completion semantics, fairness and the unsuccessful attempt

The native response-blocking probe reproduced the original completion
boundary: sql returned in 27 microseconds while zero server bytes were
forwarded, whereas Postgrex, Ecto and epgsql waited approximately two seconds
for the gate to open. The independent bounded server-log audit again confirmed
exactly **10,000 workload commits**, excluding one startup commit, with no
server errors in that audit. This does not establish per-transaction error
reporting for sql or audit every transaction in the throughput matrix.

At ten schedulers and forty callers, native sql reached 479,359/s including
its final drain, but every repeat still had callers completing only one
transaction. Jain's fairness index was approximately 0.224, essentially the
same severe imbalance as before. Its early-return API and random cached
connection assignment were unchanged.

**One native sql attempt at eight schedulers and forty callers timed out**
in `Task.await(..., 65000)` and produced no measurement. The first 52 successful
cells were retained; the same cell was retried once in a fresh VM, then the
remaining plan continued. That retry completed at 398,743/s. The failed log is
retained and excluded from throughput medians, which describe successful
measurements only. Its cause is unresolved; it cannot be attributed to native
PostgreSQL from this experiment. See the [run notes](results/native-run-notes.md).

## Native environment and evidence

PostgreSQL server/client **16.15-1.pgdg13+2** were installed from official PGDG
packages on Debian 13, matching the earlier server package version and compiler.
The server ran directly as OS user `postgres` in the existing codex-test-2
Incus container on Hercules. No Docker container was used for this rerun.
The BEAM ran natively in codex-test-2 for both deployments.

The same eight physical cores with SMT (`32-39,224-231`), no CPU quota,
loopback TCP port 55432, 200 maximum connections, TLS off and 2 GiB tmpfs
storage were used. `fsync`, `synchronous_commit` and `full_page_writes` were on.
Elixir, OTP, dependency pins and all timed Elixir source files are unchanged.
Each suite retained its original shuffled plan; the native matrix includes
the documented interruption and retry. This was a later same-host rerun,
not an interleaved or randomised deployment comparison, and it measures
empty transactions rather than durable writes.

The disposable native server is now stopped and its data tmpfs unmounted.
The installed PostgreSQL packages, scripts and evidence remain available.
No package-managed default PostgreSQL cluster was created.

- [Full matched comparison](results/native-comparison.md) and
  [CSV with medians, ranges, fairness and unsuccessful-attempt counts](results/native-comparison.csv)
- [Native scheduler/caller matrix](results/native-matrix/summary.md),
  [connection sweep](results/native-pool-sweep/summary.md) and
  [acknowledged controls](results/native-controls/summary.md); each directory
  retains the plan, raw JSONL and per-cell logs
- [Native response-blocking probe](results/native-audit/completion-probe.json)
  and [exact server-log audit](results/native-audit/count-audit.json)
- [Native environment](results/native-environment.txt),
  [installation](results/native-install.txt), [shutdown](results/native-stop.txt)
  and [complete compressed server log](results/native-server.log.gz)
- [Validation record](results/native-validation.json), including the corrected
  metadata-query error and connection-loss messages from the unsuccessful run
- [Reproduction instructions](README.md), including native installation and
  explicit resumption of interrupted matrices

## Original Docker baseline

The following findings describe the original Docker deployment. Its raw
measurements remain byte-for-byte unchanged; the native comparison above
supersedes these values as the latest run.

**epgsql exceeded 190K server-acknowledged empty transactions/s with ten
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

### Ten schedulers, forty callers

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

### Connection count is a material factor

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

### What sql's result means

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

### Eight, ten and sixteen schedulers

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

### Environment and limits

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

### Evidence and reproduction

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
