# Native PostgreSQL versus the retained Docker baseline

Three repeats per configuration. Changes compare medians. Range labels compare
observed repeats only; they are not confidence intervals or causal estimates.

**1 unsuccessful native attempt(s) were retained and retried.**
Medians and ranges describe successful measurements only. See the report for the failure context.

- [Retained attempt](native-matrix/053-sql-s8-w40-p8-r1.previous-1.log)

## matrix

| Mode | Schedulers | Callers | Connections | Docker/s | Native/s | Change | Repeat ranges |
|---|---:|---:|---:|---:|---:|---:|---|
| ecto | 8 | 40 | 8 | 62,441 | 59,628 | -4.5% | overlap |
| ecto | 10 | 1 | 10 | 8,439 | 8,305 | -1.6% | overlap |
| ecto | 10 | 10 | 10 | 67,772 | 66,776 | -1.5% | overlap |
| ecto | 10 | 40 | 10 | 72,071 | 71,140 | -1.3% | overlap |
| ecto | 16 | 40 | 16 | 96,186 | 94,732 | -1.5% | native below |
| epgsql | 8 | 40 | 40 | 140,333 | 138,324 | -1.4% | native below |
| epgsql | 10 | 1 | 1 | 15,081 | 16,304 | +8.1% | overlap |
| epgsql | 10 | 10 | 10 | 79,073 | 83,432 | +5.5% | overlap |
| epgsql | 10 | 40 | 40 | 139,391 | 138,028 | -1.0% | native below |
| epgsql | 16 | 40 | 40 | 132,127 | 130,110 | -1.5% | native below |
| epgsql_batch | 10 | 10 | 10 | 155,699 | 149,869 | -3.7% | overlap |
| no_io | 8 | 40 | 8 | 381,416 | 386,596 | +1.4% | native above |
| no_io | 10 | 40 | 10 | 391,541 | 395,889 | +1.1% | overlap |
| no_io | 16 | 40 | 16 | 410,708 | 407,039 | -0.9% | overlap |
| postgrex | 8 | 40 | 8 | 65,519 | 70,594 | +7.7% | overlap |
| postgrex | 10 | 1 | 10 | 8,953 | 8,792 | -1.8% | overlap |
| postgrex | 10 | 10 | 10 | 76,940 | 76,239 | -0.9% | overlap |
| postgrex | 10 | 40 | 10 | 83,827 | 84,528 | +0.8% | overlap |
| postgrex | 16 | 40 | 16 | 104,577 | 102,385 | -2.1% | native below |
| postgrex_held | 10 | 10 | 10 | 114,875 | 114,018 | -0.7% | overlap |
| sql | 8 | 40 | 8 | 396,302 | 398,743 | +0.6% | overlap |
| sql | 10 | 1 | 10 | 85,220 | 83,202 | -2.4% | overlap |
| sql | 10 | 10 | 10 | 356,855 | 343,333 | -3.8% | overlap |
| sql | 10 | 40 | 10 | 482,214 | 479,359 | -0.6% | overlap |
| sql | 16 | 40 | 16 | 555,113 | 565,599 | +1.9% | overlap |

## pool-sweep

| Mode | Schedulers | Callers | Connections | Docker/s | Native/s | Change | Repeat ranges |
|---|---:|---:|---:|---:|---:|---:|---|
| ecto | 10 | 40 | 1 | 9,402 | 9,056 | -3.7% | native below |
| ecto | 10 | 40 | 4 | 33,755 | 32,538 | -3.6% | overlap |
| ecto | 10 | 40 | 10 | 72,610 | 68,597 | -5.5% | overlap |
| ecto | 10 | 40 | 20 | 98,633 | 97,153 | -1.5% | native below |
| ecto | 10 | 40 | 40 | 108,407 | 107,038 | -1.3% | overlap |
| postgrex | 10 | 40 | 1 | 9,757 | 9,868 | +1.1% | overlap |
| postgrex | 10 | 40 | 4 | 35,534 | 36,631 | +3.1% | overlap |
| postgrex | 10 | 40 | 10 | 83,398 | 74,976 | -10.1% | overlap |
| postgrex | 10 | 40 | 20 | 106,283 | 105,461 | -0.8% | native below |
| postgrex | 10 | 40 | 40 | 116,197 | 115,278 | -0.8% | native below |

## controls

| Mode | Schedulers | Callers | Connections | Docker/s | Native/s | Change | Repeat ranges |
|---|---:|---:|---:|---:|---:|---:|---|
| epgsql_batch | 10 | 40 | 40 | 261,492 | 257,560 | -1.5% | overlap |
| postgrex_held | 10 | 40 | 40 | 143,981 | 142,686 | -0.9% | overlap |
