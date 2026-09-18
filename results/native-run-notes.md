# Native rerun: interruptions and unsuccessful attempts

PostgreSQL 16.15 runs directly as the `postgres` OS user in codex-test-2.
The timed Elixir code and mix.lock are unchanged from the original baseline.

The initial shuffled matrix stopped at sequence 53: `sql`, eight schedulers,
40 callers, eight configured connections, repeat 1. The client raised a
`Task.await(..., 65000)` timeout in `BeamSqlBench.measure/5`; it did not produce a
valid measurement. The log shows application-stop notices at 14:24:49 and
14:26:18 UTC on 18 September 2026. PostgreSQL remained running. Subsequent
server messages included connection resets and open-transaction EOFs during
client teardown; these alone do not establish the cause of the worker timeout.

The failure log is retained as
[native-matrix/053-sql-s8-w40-p8-r1.previous-1.log](native-matrix/053-sql-s8-w40-p8-r1.previous-1.log).
The same cell was retried once in a fresh VM before continuing the unchanged
plan. No earlier successful measurement was replaced. Published throughput
medians and ranges describe successful measurements; the timeout is an
additional unsuccessful attempt, not a zero-rate sample or a successful run.
No causal attribution to native deployment or Docker removal is established.

An initial environment capture included an invalid `SHOW lc_collate` command.
The helper now queries database collation from `pg_database` and uses
`ON_ERROR_STOP`; the final retained environment capture uses the corrected
helper. This affected metadata capture only, not the benchmark workload.
