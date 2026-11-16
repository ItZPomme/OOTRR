"""Seed generation spread over worker processes for the tests that loop over many seeds.

Generation is pure Python and CPU-bound, so threads would not help (GIL): worker processes each build the
World of a settings set once and generate its seeds. The checks stay in the test process.

    OOTRR_TEST_JOBS=8 python -m unittest discover -s tests    # 8 processes (default: one per CPU)
    OOTRR_TEST_JOBS=1 ...                                      # sequential, in the test process
"""

from __future__ import annotations

import atexit
import os
from concurrent.futures import ProcessPoolExecutor

JOBS = int(os.environ.get("OOTRR_TEST_JOBS", "0")) or os.cpu_count() or 1

_worlds: dict = {}
_pool: ProcessPoolExecutor | None = None


def _world(key: tuple):
    from ootrr import settings
    from ootrr.world import World

    world = _worlds.get(key)
    if world is None:
        world = _worlds[key] = World(settings.build(dict(key)))
    return world


def _generate(key: tuple, seed: int):
    from ootrr.fill import generate

    return generate(_world(key), seed)


def _executor() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(JOBS)
        atexit.register(_pool.shutdown, cancel_futures=True)
    return _pool


def _lazy(key: tuple, seeds: list):
    for s in seeds:  # a function, so each case keeps its own key (a generator expression would see the last one)
        yield s, _generate(key, s)


def submit_cases(cases: dict, seeds) -> dict:
    """{name: overrides} -> {name: iterator of (seed, Result)}. Every case is submitted at once; a result is
    waited for (and a generation error raised) only when its iterator reaches it, inside the caller's subTest."""
    seeds = list(seeds)
    keys = {name: tuple(sorted(overrides.items())) for name, overrides in cases.items()}
    if JOBS <= 1:
        return {name: _lazy(key, seeds) for name, key in keys.items()}
    pool = _executor()
    futures = {name: [(s, pool.submit(_generate, key, s)) for s in seeds] for name, key in keys.items()}
    return {name: ((s, f.result()) for s, f in fs) for name, fs in futures.items()}
