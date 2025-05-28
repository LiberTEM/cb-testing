import pytest
from cb_testing import f, g


def test_bench_f(benchmark):
    benchmark(f)


def test_bench_g(benchmark):
    benchmark(g)
