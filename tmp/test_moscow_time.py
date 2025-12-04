#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta

# Moscow timezone (UTC+3)
MOSCOW_TZ = timezone(timedelta(hours=3))

def to_moscow_time(dt):
    """Convert datetime to Moscow timezone (UTC+3)."""
    if dt is None:
        return None
    # If datetime is naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Convert to Moscow time
    return dt.astimezone(MOSCOW_TZ)

def format_datetime_moscow(dt, format_str="%d.%m.%Y %H:%M"):
    """Format datetime in Moscow timezone."""
    if dt is None:
        return ""
    moscow_dt = to_moscow_time(dt)
    return moscow_dt.strftime(format_str)

# Test: 01.12.2025 01:47 UTC should be 04:47 Moscow time
test_dt = datetime(2025, 12, 1, 1, 47, 0, tzinfo=timezone.utc)
print(f"UTC: {test_dt}")
print(f"Moscow: {to_moscow_time(test_dt)}")
print(f"Formatted: {format_datetime_moscow(test_dt)}")

# Test naive datetime (from DB)
test_naive = datetime(2025, 12, 1, 1, 47, 0)
print(f"\nNaive UTC: {test_naive}")
print(f"Moscow from naive: {to_moscow_time(test_naive)}")
print(f"Formatted from naive: {format_datetime_moscow(test_naive)}")

