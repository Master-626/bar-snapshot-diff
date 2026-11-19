"""Read-only, closed-window OHLCV snapshot comparison."""

from .core import AuditError, compare, load_snapshot

__version__ = "0.1.1"
__all__ = ["compare", "load_snapshot", "AuditError"]
