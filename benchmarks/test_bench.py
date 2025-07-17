import pytest
from cb_testing import f, g


def test_bench(benchmark):
    benchmark(f)


def test_bench_g(benchmark):
    benchmark(g)
