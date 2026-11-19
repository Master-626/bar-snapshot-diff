"""Strict inputs and exact decimal comparison; no data repair or trading."""

import csv
import hashlib
import io
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext

FIELDS = ("open", "high", "low", "close", "volume")
HEADER = ("symbol", "timestamp", *FIELDS)
MAX_BYTES = 50 * 1024 * 1024
STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z"
)
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
# Two 100-digit tokens with exponents in +/-1000 can differ by about 2200 digits.
_DELTA = Context(prec=4096, Emax=1000000, Emin=-1000000)
for _signal in list(_DELTA.traps):
    _DELTA.traps[_signal] = False


class AuditError(ValueError):
    """Input cannot support an unambiguous comparison."""


def timestamp(value):
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise AuditError(
            "timestamp must be ISO 8601 with seconds and explicit timezone"
        )
    if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise AuditError("timezone offset hour/minute out of range")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (ValueError, OverflowError) as exc:
        raise AuditError("invalid timestamp") from exc


def iso(value):
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Bar:
    symbol: str
    time: datetime
    values: tuple
    raw: tuple
    record: int


@dataclass(frozen=True)
class Snapshot:
    sha256: str
    rows: tuple


def read_regular(path):
    """Read one bounded byte buffer. Never open FIFO/device streams for reading."""
    before = os.stat(path)
    if not stat.S_ISREG(before.st_mode):
        raise AuditError("input must be a regular file")
    fd = os.open(
        path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    )
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise AuditError("input must be a regular file")
        if opened.st_size > MAX_BYTES:
            raise AuditError("input exceeds 50 MiB limit")
        data = handle.read(MAX_BYTES + 1)
        after = os.fstat(handle.fileno())
        if len(data) > MAX_BYTES:
            raise AuditError("input exceeds 50 MiB limit")
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise AuditError("input changed during reading")
    return data


def load_snapshot(path):
    data = read_regular(path)
    try:
        reader = csv.reader(
            io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True
        )
        header = next(reader, None)
        if header is None or len(header) != len(HEADER) or set(header) != set(HEADER):
            raise AuditError("CSV must have exactly: " + ",".join(HEADER))
        rows = []
        seen = set()
        for record, cells in enumerate(reader, 2):
            if len(cells) != len(HEADER):
                raise AuditError(
                    f"record {record}: wrong field count (blank records are not allowed)"
                )
            row = dict(zip(header, cells))
            symbol = row["symbol"]
            if (
                not symbol
                or symbol != symbol.strip()
                or any(ord(c) < 32 for c in symbol)
            ):
                raise AuditError(f"record {record}: invalid symbol")
            time = timestamp(row["timestamp"])
            key = (symbol, time)
            if key in seen:
                raise AuditError(f"record {record}: duplicate symbol/timestamp")
            seen.add(key)
            raw = tuple(row[field] for field in FIELDS)
            values = []
            for value in raw:
                if len(value) > 100 or not NUMBER.fullmatch(value):
                    raise AuditError(f"record {record}: invalid decimal")
                try:
                    number = Decimal(value)
                except InvalidOperation as exc:
                    raise AuditError(f"record {record}: invalid decimal") from exc
                if not number.is_finite() or abs(number.adjusted()) > 1000:
                    raise AuditError(
                        f"record {record}: nonfinite or excessive decimal exponent"
                    )
                values.append(number)
            op, high, low, close, volume = values
            if (
                min(op, high, low, close) <= 0
                or volume < 0
                or not low <= min(op, close) <= max(op, close) <= high
            ):
                raise AuditError(f"record {record}: invalid OHLCV relationships")
            rows.append(Bar(symbol, time, tuple(values), raw, record))
        if not rows:
            raise AuditError("snapshot has no records")
        return Snapshot(hashlib.sha256(data).hexdigest(), tuple(rows))
    except (UnicodeError, csv.Error, InvalidOperation) as exc:
        raise AuditError(f"invalid CSV: {exc}") from exc


def format_exact(number):
    """Fixed-point text of a finite Decimal, with no context rounding."""
    if not number.is_finite():
        raise AuditError("nonfinite decimal has no exact rendering")
    if number.is_zero():
        return "0"
    sign, digits, exponent = number.as_tuple()
    digits = list(digits)
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    if not digits:
        return "0"
    body = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        text = body + ("0" * exponent)
    else:
        point = len(body) + exponent
        if point > 0:
            text = body[:point] + "." + body[point:]
        else:
            text = "0." + ("0" * -point) + body
    if sign:
        text = "-" + text
    return text


def exact_delta(after, before):
    """Exact after-minus-before text. Ignores the caller's decimal precision."""
    with localcontext(_DELTA):
        delta = after - before
    if not delta.is_finite() or delta.is_zero():
        raise AuditError("internal: differing decimals produced a non-exact delta")
    return format_exact(delta)


def compare(
    before, after, *, interval_seconds, start, end, before_asof, after_asof, source_id
):
    """Compare provided rows eligible in a shared closed-bar window.

    All time arguments are timezone-explicit ISO strings. No expected grid is
    inferred. `source_id` is an unverified caller assertion of common provenance.
    Revised fields include an exact decimal `delta` of after minus before.
    """
    if type(interval_seconds) is not int or not 1 <= interval_seconds <= 31536000:
        raise AuditError("interval_seconds must be integer 1..31536000")
    if not isinstance(source_id, str) or not source_id.strip():
        raise AuditError(
            "source_id is required (same venue, product, adjustment and interval)"
        )
    start, end, old_at, new_at = map(timestamp, (start, end, before_asof, after_asof))
    if not start < end:
        raise AuditError("start must precede end")
    if new_at < old_at:
        raise AuditError("after_asof must not precede before_asof")
    duration = timedelta(seconds=interval_seconds)
    try:
        cutoff = min(old_at - duration, end - timedelta(microseconds=1))
    except OverflowError as exc:
        raise AuditError("asof timestamp is too early for this interval") from exc
    if cutoff < start:
        raise AuditError(
            "no bar in the requested window could be closed in both snapshots"
        )

    def select(snapshot):
        eligible = {}
        counts = {"outside_window": 0, "not_closed_in_both": 0}
        for bar in snapshot.rows:
            if not start <= bar.time < end:
                counts["outside_window"] += 1
            elif bar.time > cutoff:
                counts["not_closed_in_both"] += 1
            else:
                eligible[(bar.symbol, bar.time)] = bar
        return eligible, counts

    old, old_excluded = select(before)
    new, new_excluded = select(after)
    if not old or not new:
        raise AuditError("each snapshot must contain at least one eligible closed bar")
    changes = []
    unchanged = 0
    for key in sorted(old.keys() | new.keys()):
        left, right = old.get(key), new.get(key)
        base = {"symbol": key[0], "timestamp": iso(key[1])}
        if left is None:
            changes.append(
                {
                    **base,
                    "kind": "added",
                    "after_record": right.record,
                    "after": dict(zip(FIELDS, right.raw)),
                }
            )
        elif right is None:
            changes.append(
                {
                    **base,
                    "kind": "removed",
                    "before_record": left.record,
                    "before": dict(zip(FIELDS, left.raw)),
                }
            )
        else:
            fields = {
                name: {
                    "before": left.raw[i],
                    "after": right.raw[i],
                    "delta": exact_delta(right.values[i], left.values[i]),
                }
                for i, name in enumerate(FIELDS)
                if left.values[i] != right.values[i]
            }
            if fields:
                changes.append(
                    {
                        **base,
                        "kind": "revised",
                        "before_record": left.record,
                        "after_record": right.record,
                        "fields": fields,
                    }
                )
            else:
                unchanged += 1
    return {
        "schema_version": 1,
        "source_id_asserted": source_id,
        "window": {
            "start_inclusive": iso(start),
            "end_exclusive": iso(end),
            "latest_eligible_open_inclusive": iso(cutoff),
            "interval_seconds": interval_seconds,
        },
        "before": {
            "sha256": before.sha256,
            "asof": iso(old_at),
            "records": len(before.rows),
            "eligible": len(old),
            "excluded": old_excluded,
        },
        "after": {
            "sha256": after.sha256,
            "asof": iso(new_at),
            "records": len(after.rows),
            "eligible": len(new),
            "excluded": new_excluded,
        },
        "summary": {
            "unchanged": unchanged,
            **{
                kind: sum(x["kind"] == kind for x in changes)
                for kind in ("added", "removed", "revised")
            },
        },
        "changes": changes,
    }
