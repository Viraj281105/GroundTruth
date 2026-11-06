"""Executor backends and a deterministic ``map_placebos`` helper.

Every backend maps ``fn`` over items and returns results in input order. Each
item gets its own seed derived from ``(seed, index)`` alone, so results do not
depend on the backend, worker count or scheduling.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Protocol, TypeVar

import numpy as np

T = TypeVar("T")
R = TypeVar("R")


class Executor(Protocol):
    """Maps a function over inputs, preserving input order."""

    def map(self, fn: Callable[[Any], Any], items: Sequence[Any]) -> list[Any]:
        """Return ``[fn(x) for x in items]`` in input order."""
        ...


class SerialExecutor:
    """Run in the calling process."""

    def map(self, fn: Callable[[Any], Any], items: Sequence[Any]) -> list[Any]:
        return [fn(x) for x in items]


class ProcessPoolBackend:
    """Stdlib process pool. ``fn`` and items must be picklable."""

    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers

    def map(self, fn: Callable[[Any], Any], items: Sequence[Any]) -> list[Any]:
        if not items:
            return []
        with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
            return list(pool.map(fn, items))


class DaskBackend:
    """Dask (``dask.distributed``) backend; imported lazily."""

    def __init__(self, client: Any = None) -> None:
        try:
            import dask.distributed  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The 'dask' backend needs dask[distributed]: pip install 'dask[distributed]'"
            ) from exc
        self._client = client

    def map(self, fn: Callable[[Any], Any], items: Sequence[Any]) -> list[Any]:
        from dask.distributed import Client

        client = self._client or Client(processes=True)
        futures = client.map(fn, list(items), pure=False)
        return list(client.gather(futures))


class RayBackend:
    """Ray backend; imported lazily."""

    def __init__(self) -> None:
        try:
            import ray  # noqa: F401
        except ImportError as exc:
            raise ImportError("The 'ray' backend needs ray: pip install ray") from exc

    def map(self, fn: Callable[[Any], Any], items: Sequence[Any]) -> list[Any]:
        import ray

        if not ray.is_initialized():
            ray.init()
        remote = ray.remote(fn)
        return list(ray.get([remote.remote(x) for x in items]))


def get_executor(backend: str | Executor) -> Executor:
    """Resolve a backend name (serial, process, dask, ray) or pass an Executor through."""
    if not isinstance(backend, str):
        return backend
    if backend == "serial":
        return SerialExecutor()
    if backend == "process":
        return ProcessPoolBackend()
    if backend == "dask":
        return DaskBackend()
    if backend == "ray":
        return RayBackend()
    raise ValueError(f"Unknown backend {backend!r}; expected serial, process, dask or ray.")


def item_seeds(seed: int, n: int) -> list[int]:
    """Deterministic per-item seeds depending only on ``(seed, index)``."""
    return [int(np.random.SeedSequence([seed, i]).generate_state(1)[0]) for i in range(n)]


class _Seeded:
    """Picklable adapter calling ``fn(item, seed)`` on ``(item, seed)`` pairs."""

    def __init__(self, fn: Callable[[Any, int], Any]) -> None:
        self.fn = fn

    def __call__(self, pair: tuple[Any, int]) -> Any:
        return self.fn(pair[0], pair[1])


def map_placebos(
    fn: Callable[[T, int], R],
    items: Sequence[T],
    backend: str | Executor = "serial",
    seed: int = 0,
) -> list[R]:
    """Apply ``fn(item, item_seed)`` to every item; order and seeds are backend-independent."""
    pairs = list(zip(items, item_seeds(seed, len(items)), strict=True))
    out: list[R] = get_executor(backend).map(_Seeded(fn), pairs)
    return out
