# bar-snapshot-diff

Compare two **local OHLCV CSV snapshots** without changing either file. Find
numeric revisions, added records and removed records in an explicitly selected
window where bars were already closed at both snapshot times.

This is a small, dependency-free Python research-data tool, not a downloader,
trading bot, backtest engine, data-repair system or investment recommendation.
It does not integrate with Freqtrade or read its native Feather files.

## 中文摘要

本工具只读比较两份本地 OHLCV CSV 快照，找出在双方都已收盘的窗口里被修订、新增或删除的 K 线。数值用精确十进制比较，不用浮点；每处修订带有 `after` 减 `before` 的精确差值。它不联网、不修改文件、也不交易。退出码：`0` 无数值或成员变化，`1` 有变化，`2` 输入或参数无效（错误信息是 stderr 上的一行 JSON）。

## Why

Two downloads of historical candles need not be identical. A normal diff also
flags row order, decimal formatting, newly arriving candles and changes to a
still-open candle. This tool compares decimal values by `(symbol, open time)`,
requires explicit as-of times and a shared window, and records hashes of the
exact input bytes. The [research note](RESEARCH.md) describes alternatives and
sources; no novelty or production-readiness claim is made.

## Install locally

Python 3.8 or newer, no runtime dependencies:

```sh
python -m pip install .
```

No published PyPI package is claimed. For source-only use, set `PYTHONPATH=src`
and run `python -m bar_snapshot_diff` with the same arguments below.

## Reproducible example

```sh
bar-snapshot-diff examples/before.csv examples/after.csv \
  --interval-seconds 3600 \
  --start 2026-01-01T00:00:00Z --end 2026-01-01T04:00:00Z \
  --before-asof 2026-01-01T03:00:00Z \
  --after-asof 2026-01-01T04:00:00Z \
  --source-id synthetic-spot-unadjusted-1h
```

Expected: one unchanged, one revised, one added, one removed. The revised
01:00 close goes from `11` to `10`, so that field's `delta` is `-1` (after
minus before, as exact decimal text). The 03:00 bar is excluded from both
files because it was not closed at the first capture time. Examples are
invented fixtures, not exchange prices. Output is JSON on stdout. Exit codes:
**0** no numeric or membership changes, **1** changes, **2** invalid input or
options. Exit 2 prints one JSON object, `{"error": "..."}`, on stderr and does
not write a report. Exit 0 does not certify completeness or correct prices.

## Input contract

UTF-8 CSV, optional BOM, exactly these named columns (order can vary):

```csv
symbol,timestamp,open,high,low,close,volume
BTC/USDT,2026-01-01T00:00:00Z,10,12,8,11,100
```

- `timestamp` is **bar OPEN time**, explicit timezone and seconds required.
  Accepted form: `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` or numeric offset `+HH:MM`.
  Epoch integers, naive times, date-only values and leap seconds are rejected.
  Offset hours/minutes are bounded to 00..23 / 00..59. `-00:00` is treated as
  zero offset under this ISO-style contract, not RFC 3339 unknown-offset metadata.
  Timestamps are normalized to UTC. One symbol/time pair per file; duplicates
  are rejected even outside the comparison window.
- Numeric values use dot-decimal notation or exponent notation. Values are
  compared exactly with Decimal, not floating point or a tolerance. `10`,
  `10.0`, and `1e1` compare equal. The report retains original strings.
  A revised field also includes `delta`, the exact difference of after minus
  before, rendered as fixed-point text. That difference ignores the
  process-wide decimal precision. Format-only differences stay unchanged and
  have no delta. Price values must be positive, volume nonnegative, and
  low/high must bound open/close. Negative-price instruments are intentionally
  unsupported.
- Symbols are exact, case-sensitive labels, with no surrounding whitespace or
  C0 control characters (U+0000..U+001F). The tool does not resolve aliases.
- The interval is a fixed number of elapsed seconds, 1..31536000. No months,
  exchange calendars, session bars, resampling or automatic interval inference.
  Row order may differ. No missing-bar grid is inferred.
- `--start` is inclusive and `--end` exclusive for bar OPEN times. A record is
  eligible only if `open_time + interval <= before_asof` and `<= after_asof`.
  The second as-of must not precede the first. Each file must have at least one
  eligible record. A completely absent expected symbol cannot be detected if
  absent from both snapshots.
- Capture times and `--source-id` are **caller assertions**, not verified
  provenance. Compare the same venue, instrument/product, price/volume units,
  adjustment convention and timeframe. Use an identical requested window and
  retain any conversion scripts. Different export coverage can look like an
  addition/removal; a revision is not proof of a provider correction or error.
- Inputs are limited to 50 MiB each and loaded into memory. UTF-8, CSV and schema
  failures stop comparison; blank records and extra columns are not silently
  ignored. Decimal tokens are limited to 100 characters and adjusted exponents
  -1000..1000. Report record numbers count CSV records including the header,
  **not physical lines** (quoted fields may contain newlines).

## Safety and interpretation

No network calls, credentials, order execution, file modification or automatic
fill/repair. The program never opens an output file. Shell redirection such as
`> report.json` is performed by your shell and can overwrite a file, including an
input: choose a new output path, never redirect onto a source.

Only regular files are accepted. Symlinks to regular files are allowed; FIFO,
directory and device inputs are rejected. A nonblocking open and descriptor
check reduce special-file races. Size/mtime changes during reading are rejected,
but this is not an atomic filesystem snapshot or an adversarial-race guarantee.
Copy completed exports to a stable location before comparing. SHA-256 identifies
the bytes read, not their authenticity or scientific/financial correctness.

Added/removed means present in one eligible set, not necessarily exchange
backfill/deletion. Both files can share a gap or the same wrong value. Genuine
zero-trade gaps and normal post-close revisions may exist. Investigate differences
before deciding which snapshot to use; keep both originals.

## Development

Python 3.8 or newer. Continuous integration runs ruff and pytest on 3.8 and
3.9 (`ubuntu-22.04`) and on 3.10 through 3.13 (`ubuntu-latest`).

```sh
PYTHONPATH=src python -m pytest
python -m ruff check src tests
python -m pip wheel . --no-deps --no-build-isolation -w dist
```

Tests are synthetic. See [VALIDATION.md](VALIDATION.md) for exactly what was run.
See this repository's Actions page for remote CI results; the workflow file alone
is not evidence of a passing run.
