"""Gaps the original suite did not pin down: exact deltas and error contracts."""

import csv
import json
import subprocess
import sys
from decimal import Context, Decimal, getcontext, localcontext
from pathlib import Path

import pytest

from bar_snapshot_diff import AuditError, compare, load_snapshot
from bar_snapshot_diff.core import HEADER

ROOT = Path(__file__).resolve().parents[1]
T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-01T01:00:00Z"
T2 = "2026-01-01T02:00:00Z"
T3 = "2026-01-01T03:00:00Z"


def write_rows(directory, name, rows):
    path = directory / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            record = dict(
                zip(HEADER, ("BTC/USDT", T0, "10", "12", "8", "11", "100"))
            )
            record.update(row)
            writer.writerow(record)
    return path


def run_compare(left, right, **kwargs):
    params = dict(
        interval_seconds=3600,
        start=T0,
        end=T3,
        before_asof=T3,
        after_asof=T3,
        source_id="synthetic-spot-unadjusted-1h",
    )
    params.update(kwargs)
    return compare(load_snapshot(left), load_snapshot(right), **params)


def assert_delta(before, after, text):
    ctx = Context(prec=4096, Emax=1000000, Emin=-1000000)
    with localcontext(ctx):
        assert Decimal(text) == Decimal(after) - Decimal(before)


def run_cli(args):
    return subprocess.run(
        [sys.executable, "-m", "bar_snapshot_diff", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_delta_is_after_minus_before(tmp_path):
    report = run_compare(
        write_rows(tmp_path, "before.csv", [{}]),
        write_rows(
            tmp_path,
            "after.csv",
            [{"close": "10", "volume": "100.5"}],
        ),
    )
    fields = report["changes"][0]["fields"]
    assert set(fields) == {"close", "volume"}
    assert fields["close"] == {"before": "11", "after": "10", "delta": "-1"}
    assert fields["volume"] == {"before": "100", "after": "100.5", "delta": "0.5"}
    assert_delta("11", "10", fields["close"]["delta"])
    assert_delta("100", "100.5", fields["volume"]["delta"])
    assert report["summary"]["revised"] == 1


def test_scientific_notation_delta_and_format_only_equality(tmp_path):
    changed = run_compare(
        write_rows(tmp_path, "before.csv", [{"close": "1e1"}]),
        write_rows(tmp_path, "after.csv", [{"close": "10.25"}]),
    )
    close = changed["changes"][0]["fields"]["close"]
    assert close["before"] == "1e1"
    assert close["after"] == "10.25"
    assert close["delta"] == "0.25"
    assert_delta("1e1", "10.25", close["delta"])

    same = run_compare(
        write_rows(tmp_path, "left.csv", [{"close": "1e1", "volume": "100.000"}]),
        write_rows(tmp_path, "right.csv", [{"close": "10", "volume": "100"}]),
    )
    assert same["changes"] == []
    assert same["summary"]["unchanged"] == 1


def test_delta_ignores_ambient_decimal_precision(tmp_path):
    before_close = "10." + ("0" * 29) + "1"
    after_close = "10." + ("0" * 29) + "2"
    expected = "0." + ("0" * 29) + "1"
    previous = getcontext().prec
    getcontext().prec = 1
    try:
        report = run_compare(
            write_rows(tmp_path, "before.csv", [{"close": before_close}]),
            write_rows(tmp_path, "after.csv", [{"close": after_close}]),
        )
        assert getcontext().prec == 1
    finally:
        getcontext().prec = previous
    delta = report["changes"][0]["fields"]["close"]["delta"]
    assert delta == expected
    assert_delta(before_close, after_close, delta)


def test_large_exponent_delta_is_exact(tmp_path):
    shared = {"open": "1", "high": "1e1000", "low": "1", "volume": "1"}
    report = run_compare(
        write_rows(tmp_path, "before.csv", [{**shared, "close": "1"}]),
        write_rows(tmp_path, "after.csv", [{**shared, "close": "1e1000"}]),
    )
    delta = report["changes"][0]["fields"]["close"]["delta"]
    assert delta == "9" * 1000
    assert_delta("1", "1e1000", delta)


def test_added_and_removed_rows_have_no_delta(tmp_path):
    report = run_compare(
        write_rows(tmp_path, "before.csv", [{}, {"timestamp": T1}]),
        write_rows(tmp_path, "after.csv", [{}, {"timestamp": T2}]),
    )
    kinds = {change["kind"] for change in report["changes"]}
    assert kinds == {"added", "removed"}
    for change in report["changes"]:
        assert "delta" not in change
        assert "fields" not in change


def test_unrepresentable_decimal_names_the_record(tmp_path):
    path = write_rows(
        tmp_path,
        "bad.csv",
        [{}, {"timestamp": T1, "open": "1e" + ("9" * 20)}],
    )
    with pytest.raises(AuditError) as caught:
        load_snapshot(path)
    assert str(caught.value) == "record 3: invalid decimal"


def test_crlf_snapshot_loads(tmp_path):
    path = tmp_path / "crlf.csv"
    path.write_bytes(
        b"symbol,timestamp,open,high,low,close,volume\r\n"
        b"BTC/USDT,2026-01-01T00:00:00Z,10,12,8,11,100\r\n"
    )
    assert len(load_snapshot(path).rows) == 1


def test_cli_usage_errors_are_json():
    missing = run_cli([])
    assert missing.returncode == 2
    assert missing.stdout == ""
    assert json.loads(missing.stderr)["error"]

    unknown = run_cli(["--not-a-real-option"])
    assert unknown.returncode == 2
    assert unknown.stdout == ""
    assert "error" in json.loads(unknown.stderr)

    invalid = run_cli(
        [
            "before.csv",
            "after.csv",
            "--interval-seconds",
            "nope",
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
    )
    assert invalid.returncode == 2
    assert invalid.stdout == ""
    message = json.loads(invalid.stderr)["error"]
    assert "interval-seconds" in message


def test_cli_help_stays_text():
    result = run_cli(["--help"])
    assert result.returncode == 0
    assert "interval-seconds" in result.stdout
    assert result.stderr == ""


def test_documented_example_delta_and_exit_code():
    before = (ROOT / "examples" / "before.csv").read_bytes()
    after = (ROOT / "examples" / "after.csv").read_bytes()
    result = run_cli(
        [
            str(ROOT / "examples" / "before.csv"),
            str(ROOT / "examples" / "after.csv"),
            "--interval-seconds",
            "3600",
            "--start",
            T0,
            "--end",
            "2026-01-01T04:00:00Z",
            "--before-asof",
            T3,
            "--after-asof",
            "2026-01-01T04:00:00Z",
            "--source-id",
            "synthetic-spot-unadjusted-1h",
        ]
    )
    assert result.returncode == 1, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["summary"] == {
        "unchanged": 1,
        "added": 1,
        "removed": 1,
        "revised": 1,
    }
    revised = [change for change in report["changes"] if change["kind"] == "revised"]
    assert len(revised) == 1
    close = revised[0]["fields"]["close"]
    assert close == {"before": "11", "after": "10", "delta": "-1"}
    assert report["before"]["excluded"]["not_closed_in_both"] == 1
    assert report["after"]["excluded"]["not_closed_in_both"] == 1
    assert (ROOT / "examples" / "before.csv").read_bytes() == before
    assert (ROOT / "examples" / "after.csv").read_bytes() == after
