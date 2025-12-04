#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from scripts.export_statistics_to_excel import format_datetime_moscow, to_moscow_time
from datetime import datetime, timezone

# Test with UTC time
dt_utc = datetime(2025, 12, 1, 1, 47, 0, tzinfo=timezone.utc)
print(f"UTC datetime: {dt_utc}")
print(f"Moscow time: {to_moscow_time(dt_utc)}")
print(f"Formatted: {format_datetime_moscow(dt_utc)}")

# Test with naive datetime (as from DB)
dt_naive = datetime(2025, 12, 1, 1, 47, 0)
print(f"\nNaive datetime: {dt_naive}")
print(f"Moscow time from naive: {to_moscow_time(dt_naive)}")
print(f"Formatted from naive: {format_datetime_moscow(dt_naive)}")

