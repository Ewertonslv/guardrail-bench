"""Measure the recall of a prompt-injection filter against a labelled dataset."""

from guardrail_bench.dataset import Example, load_dataset
from guardrail_bench.runner import Result, evaluate
from guardrail_bench.target import load_target

__version__ = "0.1.0"

__all__ = ["Example", "Result", "evaluate", "load_dataset", "load_target", "__version__"]
