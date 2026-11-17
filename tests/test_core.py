import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bar_snapshot_diff import AuditError, compare, load_snapshot
from bar_snapshot_diff.core import HEADER, timestamp

T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-01T01:00:00Z"
T2 = "2026-01-01T02:00:00Z"
T3 = "2026-01-01T03:00:00Z"


def bar(time=T0, symbol="BTC/USDT", **kwargs):
    row = dict(zip(HEADER, (symbol, time, "10", "12", "8", "11", "100")))
    row.update(kwargs)
    return row


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.serial = 0

    def file(self, rows, header=HEADER):
        self.serial += 1
        p = self.root / f"{self.serial}.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
        return p

    def cmp(self, left, right, **kwargs):
        params = dict(
            interval_seconds=3600,
            start=T0,
            end=T3,
            before_asof=T3,
            after_asof=T3,
            source_id="synthetic-spot-unadjusted-1h",
        )
        params.update(kwargs)
        return compare(
            load_snapshot(self.file(left)), load_snapshot(self.file(right)), **params
        )

    def test_identical(self):
        r = self.cmp([bar()], [bar()])
        self.assertEqual(r["summary"], dict(unchanged=1, added=0, removed=0, revised=0))

    def test_numeric_not_format_difference(self):
        self.assertFalse(
            self.cmp([bar()], [bar(open="1e1", volume="100.000")])["changes"]
        )

    def test_exact_decimal_precision(self):
        r = self.cmp(
            [bar(close="10.00000000000000000000000000001")],
            [bar(close="10.00000000000000000000000000002")],
        )
        self.assertEqual(r["summary"]["revised"], 1)
        self.assertEqual(set(r["changes"][0]["fields"]), {"close"})

    def test_reordering(self):
        self.assertFalse(self.cmp([bar(), bar(T1)], [bar(T1), bar()])["changes"])

    def test_added_and_removed(self):
        r = self.cmp([bar(), bar(T1)], [bar(), bar(T2)])
        self.assertEqual([c["kind"] for c in r["changes"]], ["removed", "added"])

    def test_symbols_are_independent(self):
        r = self.cmp([bar(), bar(symbol="ETH")], [bar(), bar(symbol="ETH", close="10")])
        self.assertEqual(r["changes"][0]["symbol"], "ETH")

    def test_symbol_case_is_not_folded(self):
        r = self.cmp([bar(symbol="btc")], [bar(symbol="BTC")])
        self.assertEqual(r["summary"]["added"], 1)
        self.assertEqual(r["summary"]["removed"], 1)

    def test_open_bar_excluded(self):
        r = self.cmp([bar(), bar(T1)], [bar(), bar(T1, close="9")], before_asof=T1)
        self.assertFalse(r["changes"])
        self.assertEqual(r["before"]["excluded"]["not_closed_in_both"], 1)

    def test_closes_exactly_at_asof(self):
        r = self.cmp([bar()], [bar(close="10")], before_asof=T1)
        self.assertEqual(r["summary"]["revised"], 1)

    def test_end_exclusive(self):
        r = self.cmp([bar(), bar(T1)], [bar(), bar(T1, close="9")], end=T1)
        self.assertFalse(r["changes"])
        self.assertEqual(r["after"]["excluded"]["outside_window"], 1)

    def test_start_inclusive(self):
        self.assertEqual(
            self.cmp([bar(), bar(T1)], [bar(), bar(T1, close="9")], start=T1)[
                "summary"
            ]["revised"],
            1,
        )

    def test_newer_download_not_new_candles(self):
        r = self.cmp([bar()], [bar(), bar(T1), bar(T2)], before_asof=T1)
        self.assertFalse(r["changes"])
        self.assertEqual(r["after"]["excluded"]["not_closed_in_both"], 2)

    def test_offset_equivalence(self):
        r = self.cmp([bar()], [bar("2026-01-01T08:00:00+08:00")])
        self.assertFalse(r["changes"])

    def test_microseconds(self):
        self.assertEqual(timestamp("2026-01-01T00:00:00.123456Z").microsecond, 123456)

    def test_duplicate_key_rejected(self):
        with self.assertRaises(AuditError):
            load_snapshot(self.file([bar(), bar()]))

    def test_timezone_normalized_duplicate(self):
        with self.assertRaises(AuditError):
            load_snapshot(self.file([bar(), bar("2026-01-01T08:00:00+08:00")]))

    def test_duplicate_outside_window_still_rejected(self):
        with self.assertRaises(AuditError):
            self.cmp([bar(), bar(T3), bar(T3)], [bar()])

    def test_invalid_numeric_values(self):
        for value in [
            "NaN",
            "Infinity",
            "1_000",
            " 10",
            "",
            "1e1001",
            "1e-1001",
            "9" * 101,
        ]:
            with self.subTest(value=value), self.assertRaises(AuditError):
                load_snapshot(self.file([bar(open=value)]))

    def test_invalid_relationships(self):
        for fields in [
            dict(low="11"),
            dict(high="9"),
            dict(volume="-1"),
            dict(open="0"),
            dict(low="-1"),
        ]:
            with self.subTest(fields=fields), self.assertRaises(AuditError):
                load_snapshot(self.file([bar(**fields)]))

    def test_zero_volume_allowed(self):
        self.assertEqual(len(load_snapshot(self.file([bar(volume="0")])).rows), 1)

    def test_invalid_timestamps(self):
        for value in [
            "2026-01-01",
            "2026-01-01T00:00:00",
            "2026-02-30T00:00:00Z",
            "2026-01-01T00:00:00.1234567Z",
            "1700000000",
            "2026-01-01T00:00:00+00:60",
            "2026-01-01T00:00:00+01:99",
            "2026-01-01T00:00:00+24:00",
        ]:
            with self.subTest(value=value), self.assertRaises(AuditError):
                load_snapshot(self.file([bar(value)]))

    def test_invalid_symbol(self):
        for value in ["", " BTC", "BTC\nUSDT"]:
            with self.subTest(value=value), self.assertRaises(AuditError):
                load_snapshot(self.file([bar(symbol=value)]))

    def test_duplicate_header(self):
        p = self.root / "bad.csv"
        p.write_text("symbol,timestamp,open,high,low,close,close\n")
        with self.assertRaises(AuditError):
            load_snapshot(p)

    def test_reordered_header(self):
        self.assertEqual(
            len(load_snapshot(self.file([bar()], tuple(reversed(HEADER)))).rows), 1
        )

    def test_empty_input(self):
        with self.assertRaises(AuditError):
            load_snapshot(self.file([]))

    def test_malformed_csv(self):
        for suffix in ['"unclosed', "a,b\n", "\n"]:
            p = self.root / "bad.csv"
            p.write_text(",".join(HEADER) + "\n" + suffix)
            with self.subTest(suffix=suffix), self.assertRaises(AuditError):
                load_snapshot(p)

    def test_bom_and_crlf(self):
        p = self.file([bar()])
        p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
        self.assertEqual(len(load_snapshot(p).rows), 1)

    def test_hash_matches_bytes(self):
        p = self.file([bar()])
        self.assertEqual(
            load_snapshot(p).sha256, hashlib.sha256(p.read_bytes()).hexdigest()
        )

    def test_invalid_utf8(self):
        p = self.root / "bad.csv"
        p.write_bytes(b"\xff")
        with self.assertRaises(AuditError):
            load_snapshot(p)

    def test_directory_rejected(self):
        with self.assertRaises(AuditError):
            load_snapshot(self.root)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO only")
    def test_fifo_rejected(self):
        p = self.root / "fifo"
        os.mkfifo(p)
        with self.assertRaises(AuditError):
            load_snapshot(p)

    def test_bounded_input(self):
        p = self.file([bar()])
        with (
            patch("bar_snapshot_diff.core.MAX_BYTES", 5),
            self.assertRaises(AuditError),
        ):
            load_snapshot(p)

    def test_invalid_options(self):
        for changes in [
            dict(interval_seconds=0),
            dict(interval_seconds=True),
            dict(interval_seconds=1.2),
            dict(interval_seconds=31536001),
            dict(source_id=""),
            dict(start=T3),
            dict(after_asof=T0),
            dict(before_asof=T0),
        ]:
            with self.subTest(changes=changes), self.assertRaises(AuditError):
                self.cmp([bar()], [bar()], **changes)

    def test_no_eligible_rows(self):
        with self.assertRaises(AuditError):
            self.cmp([bar(T3)], [bar()])

    def test_early_asof(self):
        with self.assertRaises(AuditError):
            self.cmp([bar()], [bar()], before_asof="0001-01-01T00:00:00Z")

    def test_no_implied_grid(self):
        r = self.cmp([bar(), bar(T2)], [bar(), bar(T2)])
        self.assertEqual(r["summary"]["unchanged"], 2)
        self.assertFalse(r["changes"])

    def test_quoted_symbols(self):
        r = self.cmp([bar(symbol='A,"B')], [bar(symbol='A,"B')])
        self.assertEqual(r["summary"]["unchanged"], 1)

    def run_cli(self, left, right):
        args = [
            sys.executable,
            "-m",
            "bar_snapshot_diff",
            str(left),
            str(right),
            "--interval-seconds",
            "3600",
            "--start",
            T0,
            "--end",
            T3,
            "--before-asof",
            T3,
            "--after-asof",
            T3,
            "--source-id",
            "synthetic",
        ]
        return subprocess.run(args, capture_output=True, text=True, timeout=10)

    def test_cli_exit_zero(self):
        p = self.file([bar()])
        before = p.read_bytes()
        result = self.run_cli(p, p)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["unchanged"], 1)
        self.assertEqual(p.read_bytes(), before)

    def test_cli_exit_one(self):
        result = self.run_cli(self.file([bar()]), self.file([bar(close="10")]))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["revised"], 1)

    def test_cli_exit_two(self):
        result = self.run_cli(self.root / "missing", self.file([bar()]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", json.loads(result.stderr))
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
