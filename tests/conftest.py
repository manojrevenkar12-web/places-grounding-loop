import functools

import pytest

from pgl.pipeline.release import build
from pgl.settings import load


@functools.lru_cache
def _releases():
    s = load()
    r1 = build(1, s)
    return r1, build(2, s, r1)


@pytest.fixture
def s():
    return load()


@pytest.fixture
def releases():
    import copy

    r1, r2 = _releases()
    return r1, copy.deepcopy(r2)
