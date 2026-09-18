# Sustained 60-second trials

Ten schedulers, forty callers, 10-second per-worker warmup, 3 attempts per configuration.
Duration controls stopping; pilot counts are estimates only. Final drains and overruns are timed.
The five-second native reference used two-second warmup. This comparison changes both warmup
and measurement duration; it is not an isolated causal estimate of duration.

21 successful sustained trials; 0 failed sustained attempts; 7 successful short pilots. Every attempt is retained; no automatic retries.

| Mode | Connections | Successful/attempted | Five-second median/s | Sustained median/s | Change | Sustained range/s |
|---|---:|---:|---:|---:|---:|---:|
| ecto | 40 | 3/3 | 107,038 | 107,472 | 0.4% | 107,165–107,781 |
| epgsql | 40 | 3/3 | 138,028 | 136,947 | -0.8% | 136,571–137,304 |
| epgsql_batch | 40 | 3/3 | 257,560 | 257,428 | -0.1% | 257,424–258,538 |
| no_io | 10 | 3/3 | 395,889 | 395,017 | -0.2% | 394,736–396,600 |
| postgrex | 40 | 3/3 | 115,278 | 115,764 | 0.4% | 115,579–116,003 |
| postgrex_held | 40 | 3/3 | 142,686 | 144,487 | 1.3% | 144,235–148,247 |
| sql | 10 | 3/3 | 479,359 | 463,294 | -3.4% | 455,770–466,218 |

The no-I/O control is not SQL TPS. sql has local API return plus a final fence;
the other database modes await responses. Combined BEGIN/COMMIT is not a callback API.

## Counts and elapsed time

| Mode | Pilot expected count | Actual count (median) | Actual elapsed range/s | Max drain/s | Worst fairness |
|---|---:|---:|---:|---:|---:|
| ecto | 6,419,762 | 6,448,345 | 60.000–60.000 | 0.0000 | 1.000 |
| epgsql | 8,189,532 | 8,217,193 | 60.003–60.004 | 0.0000 | 1.000 |
| epgsql_batch | 15,515,379 | 15,445,906 | 60.001–60.001 | 0.0000 | 1.000 |
| no_io | 23,589,805 | 23,701,063 | 60.000–60.000 | 0.0000 | 1.000 |
| postgrex | 6,886,055 | 6,945,858 | 60.000–60.000 | 0.0000 | 1.000 |
| postgrex_held | 8,584,333 | 8,669,239 | 60.000–60.000 | 0.0000 | 1.000 |
| sql | 27,323,704 | 28,214,661 | 60.526–60.900 | 0.0002 | 0.225 |

## Within-run windows

Rates group completed API operations by their start window, not server commit timestamp.
An operation spanning boundaries is assigned once to its start window. Windows do not
reconnect or fence. Counts are published after all operations and the final fence complete.
Latest API completion time exposes window overruns; full-run drained TPS is the headline.
First/last values are medians across successful repeats; they do not prove stationarity.

| Mode | First 10s median/s | Last 10s median/s | Last vs first | Max API window overrun/s | Fewest transactions per worker in full run |
|---|---:|---:|---:|---:|---:|
| ecto | 107,686 | 107,590 | -0.1% | 0.001 | 160,497 |
| epgsql | 137,424 | 136,851 | -0.4% | 0.004 | 204,620 |
| epgsql_batch | 258,122 | 256,659 | -0.6% | 0.001 | 385,355 |
| no_io | 394,812 | 395,124 | 0.1% | 0.001 | 588,608 |
| postgrex | 115,743 | 115,879 | 0.1% | 0.001 | 173,024 |
| postgrex_held | 145,500 | 144,092 | -1.0% | 0.000 | 215,045 |
| sql | 515,735 | 447,078 | -13.3% | 50.900 | 1 |

[All windows](windows.csv), [raw attempts](attempts.jsonl), [plan and source hashes](plan.json).

## Unsuccessful attempts

None.
