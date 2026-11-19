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

## November 18, 2026 follow-up

Local checks after exact `delta` reporting, record-numbered decimal errors,
JSON CLI usage errors, and the license-file metadata fix:

- Linux, CPython 3.8.20, 3.9.25, 3.10.22, 3.11.18, 3.12.3, and 3.13.18:
  `PYTHONPATH=src python -m pytest` — 50 passed. On 3.10 and newer, pytest also
  reported 35 unittest subtests passed. The count includes the original
  unittest module plus the new pytest module.
- Ruff 0.17.5 `ruff check src tests` passed with the configured E4/E7/E9/F/I
  rules (`target-version = py38`).
- Isolated wheels built on those same interpreters. A non-isolated build with
  setuptools 68.1.2 also succeeded after `license` was changed to a file table.
- The documented example still exits 1 with one unchanged, one revised, one
  added, and one removed row. The revised close delta is `-1`. Example bytes
  were unchanged.

CI is Linux-only: ubuntu-22.04 for 3.8 and 3.9, ubuntu-latest for 3.10–3.13.
Remote Actions results are separate from this local record. No PyPI release is
claimed. Real exchange snapshot pairs were not used.

## November 17 follow-up

Linux Python 3.13.5: all 40 source tests and all 40 wheel-import tests passed.
Wheel-import tests used PYTHONPATH to the preserved wheel, not a pip install.
The original candidate source manifest and ZIP hash were verified unchanged.
