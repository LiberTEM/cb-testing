import pytest
from cb_testing import f


def test_bench(benchmark):
    benchmark(f)
