import numpy as np
import pytest

from groundtruth.compute import SerialExecutor, get_executor, map_placebos


def draw(item: int, seed: int) -> tuple[int, float]:
    return item, float(np.random.default_rng(seed).normal())


def test_order_and_backend_equivalence() -> None:
    items = list(range(8))
    a = map_placebos(draw, items, "serial", seed=3)
    b = map_placebos(draw, items, "process", seed=3)
    assert a == b
    assert [x[0] for x in a] == items
    assert a != map_placebos(draw, items, "serial", seed=4)


def test_custom_executor_and_empty() -> None:
    assert map_placebos(draw, [], SerialExecutor()) == []


def test_unknown_backend() -> None:
    with pytest.raises(ValueError):
        get_executor("nope")


def test_optional_backends_clear_error() -> None:
    for name in ("dask", "ray"):
        try:
            __import__(name)
        except ImportError:
            with pytest.raises(ImportError, match=name):
                get_executor(name)
