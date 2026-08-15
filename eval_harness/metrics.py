"""Scoring for the retrieval comparison. Deliberately plain: the numbers in the
README are only worth anything if the arithmetic behind them is obvious."""

from __future__ import annotations

from collections.abc import Set


def prf(predicted: Set[str], truth: Set[str]) -> tuple[float, float, float]:
    """Precision, recall, F1 over sets of file paths."""
    if not predicted or not truth:
        return (0.0, 0.0, 0.0)
    hits = len(predicted & truth)
    precision = hits / len(predicted)
    recall = hits / len(truth)
    if precision + recall == 0:
        return (precision, recall, 0.0)
    return (precision, recall, 2 * precision * recall / (precision + recall))
