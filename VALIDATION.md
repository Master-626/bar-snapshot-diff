# Validation record

Local validation record, 2026-11-16, with a November 17 follow-up.
GitHub CI results, when available, are separate from these local checks.
No PyPI release is claimed.

- Linux, Python 3.12.14: 40 source unittest tests passed, including subprocess
  CLI exit codes, exact decimal comparisons, closure/window boundaries, malformed
  CSV/timestamps, duplicates, bounded reads and POSIX FIFO rejection.
- Independent reviewer ran the original 40 tests plus 200 seeded synthetic
  comparisons against a separate expected-diff oracle. The reviewer found that
  Python normalizes invalid timezone-minute offsets; explicit bounds and
  regression cases were subsequently added, and the full source suite rerun.
- Ruff 0.17.5 lint passed using this repository's configured E4/E7/E9/F/I rules.
- Wheel and source-distribution built with Python build 1.6.1 / setuptools
  84.2.1. A fresh environment installed the wheel and passed all 40 tests without
  PYTHONPATH. Installed CLI help and the documented example were also checked.
- Example result verified: one unchanged, one added, one removed, one revised;
  one still-open bar excluded per file. Input-file immutability is covered by a
  CLI regression test.

Not tested: native Windows/macOS (CI matrix prepared only), other Python versions,
real exchange snapshot pairs, Freqtrade integration, performance at the size
limit, adversarial concurrent file replacement, downstream backtest behavior.
Synthetic examples demonstrate logic, not actual data-provider revisions.

## November 17 follow-up

Linux Python 3.13.5: all 40 source tests and all 40 wheel-import tests passed.
Wheel-import tests used PYTHONPATH to the preserved wheel, not a pip install.
The original candidate source manifest and ZIP hash were verified unchanged.
