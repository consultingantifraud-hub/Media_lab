"""Utility helpers for money/balance formatting."""
from __future__ import annotations

from decimal import Decimal
from typing import Union


Number = Union[int, float, Decimal, None]


def kopecks_to_rubles(amount_kopecks: Number) -> float:
    """Convert integer kopecks (as stored in DB) to rubles with 2 decimals."""
    if amount_kopecks is None:
        return 0.0
    return round(float(amount_kopecks) / 100.0, 2)


def format_kopecks(amount_kopecks: Number) -> str:
    """Format kopeck amount as 'xx.xx' rubles string."""
    return f"{kopecks_to_rubles(amount_kopecks):.2f}"

