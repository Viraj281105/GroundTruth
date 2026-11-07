"""Pluggable execution backends for embarrassingly parallel work."""

from groundtruth.compute.executor import (
    Executor,
    ProcessPoolBackend,
    SerialExecutor,
    get_executor,
    item_seeds,
    map_placebos,
)

__all__ = [
    "Executor",
    "ProcessPoolBackend",
    "SerialExecutor",
    "get_executor",
    "item_seeds",
    "map_placebos",
]
