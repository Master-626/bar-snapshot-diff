import argparse
import json
import sys

from .core import AuditError, compare, load_snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare closed OHLCV CSV snapshots without changing data."
    )
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--interval-seconds", required=True, type=int)
    for name in ("start", "end", "before-asof", "after-asof", "source-id"):
        parser.add_argument("--" + name, required=True)
    args = vars(parser.parse_args(argv))
    try:
        before = load_snapshot(args.pop("before"))
        after = load_snapshot(args.pop("after"))
        report = compare(before, after, **args)
    except (AuditError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    return 1 if report["changes"] else 0


if __name__ == "__main__":
    sys.exit(main())
