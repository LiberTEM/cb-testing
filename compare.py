#!/usr/bin/env python
import io
import json
import typing
import zipfile

import click
from scipy.stats import ttest_ind


def extract_nested(outer_zipfile: zipfile.ZipFile, inner_zipname: str, filename: str) -> bytes:
    """
    Extract `filename` from a nested .zip file called `inner_zipname` stored in
    `outer_zipfile`.
    """
    with outer_zipfile.open(inner_zipname) as f:
        bytes_a = io.BytesIO(initial_bytes=f.read())
        bytes_a.seek(0)
        with zipfile.ZipFile(bytes_a, mode='r') as f_inner:
            return f_inner.read(name=filename)


def extract_and_parse(zip_fname: str, filename: str) -> "BenchmarkResults":
    with zipfile.ZipFile(file=zip_fname, mode='r') as zf:
        contents = zf.read(filename)
    return BenchmarkResults.from_json(contents.decode("utf8"))


class RawResult(typing.TypedDict):
    all_data: dict[str, typing.Any]  # as given by pytest-benchmark
    timings: list[float]


RawResults = dict[str, RawResult]


class ChangedEntry(typing.TypedDict):
    old: RawResult
    new: RawResult


def _format_duration(duration: float) -> str:
    if duration >= 1:
        return f"{duration:.2f} s"
    elif duration >= 1e-3:
        return f"{duration*1e3:.2f} ms"
    elif duration >= 1e-6:
        return f"{duration*1e6:.2f} µs"
    else:  # don't go smaller than ns
        return f"{duration*1e9:.2f} ns"


def _format_changed_timings(entry: RawResult) -> str:
    return (
        f"{_format_duration(entry['all_data']['stats']['mean'])} "
        f"(± {_format_duration(entry['all_data']['stats']['stddev'])})"
    )


class ComparisonResult:
    def __init__(
        self,
        new_benchmarks: list[str],
        removed_benchmarks: list[str],
        unchanged: list[str],
        changed: dict[str, ChangedEntry],
    ):
        self.new = new_benchmarks
        self.removed = removed_benchmarks
        self.unchanged = unchanged
        self.changed = changed

    def get_summary(self):
        """Get a summary of changed suitable for a GitHub PR comment"""
        return f"""
# Benchmark results
{self._get_new_benchmarks()}
{self._get_removed_warning()}
{self._get_change_summary()}

## Changed benchmark results
{self._get_change_details()}
"""

    def _get_removed_warning(self):
        if len(self.removed) == 0:
            return ""
        return f"""
> [!WARNING]
> The following benchmarks have been removed: {", ".join([f"`{n}`" for n in self.removed])}
> Take care when renaming benchmarks, and re-consider removal of old benchmarks!
        """

    def _get_new_benchmarks(self):
        if len(self.new) == 0:
            return ""
        return f"""
> [!NOTE]
> The following benchmarks are new: {", ".join([f"`{n}`" for n in self.new])}
        """

    def _get_change_summary(self):
        return f"Significant changes detected in {len(self.changed)} benchmarks, {len(self.unchanged)} benchmarks remain unchanged."

    def _get_change_details(self):
        if len(self.changed) == 0:
            return "No significant changes detected"
        header = """
| Name | old | new |
| ---- | --- | --- |
"""
        rows = [
            f"| {key} | {_format_changed_timings(value['old'])} | {_format_changed_timings(value['new'])} |"
            for key, value in self.changed.items()
        ]
        return header + "\n".join(rows)


class BenchmarkResults:
    def __init__(self, raw_results: RawResults):
        self._raw_results = raw_results

    @classmethod
    def from_json(cls, json_string) -> "BenchmarkResults":
        data = json.loads(json_string)
        bench_results: RawResults = {}
        for bench in data["benchmarks"]:
            bench_results[bench["fullname"]] = {
                "all_data": bench,
                "timings": bench["stats"]["data"],
            }
        return cls(raw_results=bench_results)

    def compare_to(self, old: "BenchmarkResults", alpha=0.05):
        """Compare this benchmark to another.
        
        It's assumed that the other benchmark is the older result, and this
        benchmark contains changes relative to the other.
        """
        keys_this = set(self._raw_results.keys())
        keys_old = set(old._raw_results.keys())
        new_benchmarks = list(keys_this - keys_old)
        removed_benchmarks = list(keys_old - keys_this)
        to_compare = keys_this.intersection(keys_old)
        unchanged = []
        changed = {}
        for name in to_compare:
            ttest_res = ttest_ind(
                self._raw_results[name]["timings"],
                old._raw_results[name]["timings"],
                equal_var=False,  # Whelch's t-test
            )
            if ttest_res.pvalue > alpha:  # type: ignore
                unchanged.append(name)
            else:
                changed[name] = {
                    "old": old._raw_results[name],
                    "new": self._raw_results[name],
                }
        return ComparisonResult(
            new_benchmarks=new_benchmarks,
            removed_benchmarks=removed_benchmarks,
            unchanged=unchanged,
            changed=changed,
        )


@click.command
@click.argument("name_old", type=click.Path())
@click.argument("name_new", type=click.Path())
def main(name_old, name_new):
    b_old = extract_and_parse(zip_fname=name_old, filename="bench-results.json")
    b_new = extract_and_parse(zip_fname=name_new, filename="bench-results.json")
    diff = b_new.compare_to(b_old)
    print(diff.get_summary())


if __name__ == "__main__":
    main()
