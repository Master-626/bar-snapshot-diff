# Scope research, 2026-11-16

Generic path portability and single-snapshot OHLCV validators were rejected as
candidate directions because direct alternatives already exist. Examples include
[pathport](https://github.com/Yougan001/pathport),
[ohlcv-doctor](https://github.com/ahmethasmerdogan/ohlcv-doctor), and
[financial-data-cleaner](https://github.com/MehdiDolati/financial-data-cleaner).
Their search-visible descriptions cover overlapping validation features; they
were not installed, benchmarked or fully reviewed. General-purpose dataframe or
SQL comparisons can also implement this task. This project offers a narrow,
explicit contract and a small offline CLI, not an assertion of uniqueness.

Primary-source rationale:

- [CCXT Manual](https://github.com/ccxt/ccxt/wiki/Manual): current candles may be
  incomplete, and periods without trades may be missing. Therefore this tool
  excludes bars not closed by both caller-supplied capture times and does not
  automatically fill gaps or equate gaps with provider errors.
- [Freqtrade FAQ](https://www.freqtrade.io/en/stable/faq/): its handling of missing
  data can synthesize empty candles. This candidate does not read native
  Freqtrade files or infer which rows were filled. Compare untouched exports
  with a known, documented conversion instead.
- [Binance public-data repository](https://github.com/binance/binance-public-data):
  provides checksums and an archive update history. A checksum can identify a
  version, but the comparison here cannot reconstruct older versions that were
  not saved. No Binance dataset was downloaded or redistributed.

User demand is inferred from the general reproducibility problem, not validated
by interviews, adoption or real trading outcomes. No genuine pair of historical
exchange snapshots has been tested. No account, key or money is involved.
