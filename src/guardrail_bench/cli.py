"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from guardrail_bench import __version__
from guardrail_bench.dataset import DEFAULT_DATASET, DatasetError, load_dataset
from guardrail_bench.report import render, use_colour
from guardrail_bench.runner import evaluate
from guardrail_bench.target import TargetError, load_target, regex_target

EXIT_OK = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_USAGE = 2

EPILOG = """\
examples:
  guardrail-bench myapp.filters:looks_like_injection
  guardrail-bench ./scripts/guard.py:is_injection
  guardrail-bench --regex "ignore.{0,40}(instructions|rules)"
  guardrail-bench myapp:guard --dataset ./my_corpus.jsonl --json
  guardrail-bench myapp:guard --fail-under 60        # for CI

your filter is any callable that takes a string and returns something truthy
when the message should be treated as an injection attempt. A compiled regex
works too.

bring your own dataset with --dataset, as JSONL, one object per line:
  {"text": "ignore previous instructions", "label": 1}
  {"text": "what time is my appointment?", "label": 0}
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="guardrail-bench",
        description="Measure the recall of your prompt-injection filter against a labelled dataset.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "target",
        nargs="?",
        help="module:function, or path/to/file.py:function",
    )
    p.add_argument("--regex", metavar="PATTERN", help="benchmark a bare regex instead of a callable")
    p.add_argument(
        "--dataset",
        metavar="SOURCE",
        help=f"local .jsonl file, or a Hugging Face dataset name (default: {DEFAULT_DATASET})",
    )
    p.add_argument("--refresh", action="store_true", help="re-download the dataset, ignoring the cache")
    p.add_argument("--json", action="store_true", dest="as_json", help="emit machine-readable JSON")
    p.add_argument("--samples", type=int, default=5, metavar="N", help="examples to show per section (default: 5)")
    p.add_argument(
        "--fail-under",
        type=float,
        metavar="RECALL",
        help="exit 1 when recall is below this percentage, for use in CI",
    )
    p.add_argument("--no-color", action="store_true", help="disable colour output")
    p.add_argument("--version", action="version", version=f"guardrail-bench {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.target) == bool(args.regex):
        parser.error("give exactly one of TARGET or --regex")

    try:
        predicate = regex_target(args.regex) if args.regex else load_target(args.target)
    except TargetError as exc:
        print(f"guardrail-bench: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        examples = load_dataset(args.dataset, refresh=args.refresh)
    except DatasetError as exc:
        print(f"guardrail-bench: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not any(e.is_injection for e in examples):
        print("guardrail-bench: the dataset has no rows labelled 1, so recall is undefined", file=sys.stderr)
        return EXIT_USAGE

    result = evaluate(predicate, examples)

    label = f"regex {args.regex!r}" if args.regex else args.target
    source = args.dataset or DEFAULT_DATASET

    if args.as_json:
        payload = result.to_dict()
        payload["target"] = label
        payload["dataset"] = source
        payload["version"] = __version__
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        colour = use_colour() and not args.no_color
        print(render(result, label, source, __version__, samples=args.samples, colour=colour))

    if args.fail_under is not None and result.recall < args.fail_under:
        print(
            f"guardrail-bench: recall {result.recall}% is below --fail-under {args.fail_under}%",
            file=sys.stderr,
        )
        return EXIT_BELOW_THRESHOLD

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
