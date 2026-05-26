"""Metric formatting utilities for evaluation scripts."""

from datetime import datetime, timezone
from typing import Any


def metric(name: str, data_type: str, result: Any, tier: int, **kwargs) -> dict:
    """Create a standardized metric entry."""
    entry = {"name": name, "data_type": data_type, "tier": tier, "result": result}
    entry.update({k: v for k, v in kwargs.items() if v is not None})
    return entry


def timestamp() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(tz=timezone.utc).isoformat()


def format_report(metrics: list[dict], **extra) -> dict:
    """Format metrics into a standard report structure."""
    report = {
        "run_timestamp": timestamp(),
        "metrics": metrics,
    }
    report.update(extra)
    return report
