# Initial benchmark snapshot

This repository was seeded on 18 September 2026 from the benchmark and findings
created in the originating Codex task.

- Source checkout: `/Users/evadne/Documents/Codex/2026-09-18/are-there-any-sql-database-libraries/outputs/beam-sql-bench`
- Source revision: `1fa8c206e5146530f197cc58a625eca3112b49cc`
- Earlier source checkpoints: `d84d8f1` and `69133fb`.
- Copied 147 tracked files, including the harness, pinned dependencies,
  report, all 111 performance measurements, summaries and completion/audit evidence.
- Copied file contents were verified byte-for-byte. The only modified source file
  is `.gitignore`, extended for local build, editor, Python and scratch files.
  This provenance note is new.

The source Git history was not imported: this repository begins with a fresh
initial commit. Historical commit identifiers in `REPORT.md` refer to the source
checkout above. No benchmark was rerun as part of this repository creation.

See [REPORT.md](REPORT.md) for findings and [README.md](README.md) for reproduction.

## Subsequent native rerun

After the initial snapshot, PostgreSQL was installed directly in codex-test-2
and the matrix repeated. `results/native-*` retains this separate evidence,
including one unsuccessful attempt and its explicit retry. The report now leads
with the native comparison; the original Docker evidence was preserved. Timed Elixir source and dependency
pins were byte-for-byte unchanged from the initial commit through `eb2912f`.

## Sustained measurements

The subsequent minute-long profile adds ten-second reporting windows around
the original per-transaction loop and records warmup/window metadata. The loop
and library operations themselves are unchanged. Defaults for direct runs are
now 60 seconds of measurement and ten seconds of warmup; the explicitly timed
legacy matrix still reproduces the five-second baseline. Dependency pins and
all historical raw results remain unchanged. Pilot estimates do not impose a
transaction-count limit on sustained trials.
