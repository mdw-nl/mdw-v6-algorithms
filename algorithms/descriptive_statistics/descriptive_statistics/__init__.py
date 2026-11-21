"""Federated descriptive statistics: counts, minmax, mean, std over arbitrary columns."""

from descriptive_statistics.entrypoints import central, compute_local_stats

__all__ = ["central", "compute_local_stats"]
