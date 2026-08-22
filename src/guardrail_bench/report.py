"""Human-readable output.

This is the part people screenshot, so it is built to be read at a glance and
to survive a terminal with no colour support.
"""

from __future__ import annotations

import os
import sys
from typing import List

from guardrail_bench.runner import Result

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"


def use_colour(stream=None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    return hasattr(stream, "isatty") and stream.isatty()


class _Paint:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, *codes: str) -> str:
        if not self.enabled or not codes:
            return text
        return "".join(codes) + text + RESET


def _grade(pct: float) -> str:
    if pct >= 90:
        return GREEN
    if pct >= 60:
        return YELLOW
    return RED


def _truncate(text: str, width: int = 84) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def render(
    result: Result,
    target: str,
    dataset: str,
    version: str,
    samples: int = 5,
    colour: bool = True,
) -> str:
    c = _Paint(colour)
    out: List[str] = []
    add = out.append

    add("")
    add(f"  {c('guardrail-bench', BOLD)} {c(version, DIM)}")
    add(f"  {c('target ', DIM)}  {target}")
    add(
        f"  {c('dataset', DIM)}  {dataset}  "
        f"{c(f'{result.total} messages ({result.injections} injections, {result.legitimate} legitimate)', DIM)}"
    )
    add("")

    caught = f"{result.true_positives} of {result.injections} injections caught"
    flags = result.true_positives + result.false_positives
    real = f"{result.true_positives} of {flags} flags were real" if flags else "nothing was flagged"

    add(f"  {c('RECALL   ', BOLD)} {c(f'{result.recall:>5}%', BOLD, _grade(result.recall))}   {c(caught, DIM)}")
    add(f"  {c('PRECISION', BOLD)} {c(f'{result.precision:>5}%', _grade(result.precision))}   {c(real, DIM)}")
    add(f"  {c('F1       ', BOLD)} {f'{result.f1:>5}%'}")
    add(f"  {c('ACCURACY ', BOLD)} {f'{result.accuracy:>5}%'}")
    add("")

    add(f"  {c('               flagged   not flagged', DIM)}")
    add(f"  injection    {result.true_positives:>9}   {result.false_negatives:>11}")
    add(f"  legitimate   {result.false_positives:>9}   {result.true_negatives:>11}")
    add("")

    if result.missed and samples:
        shown = result.missed[:samples]
        add(f"  {c(f'Injections it let through ({len(shown)} of {len(result.missed)}):', BOLD)}")
        for ex in shown:
            add(f"    {c('-', DIM)} {_truncate(ex.text)}")
        add("")

    if result.flagged_legitimate and samples:
        shown = result.flagged_legitimate[:samples]
        add(f"  {c(f'Legitimate messages it flagged ({len(shown)} of {len(result.flagged_legitimate)}):', BOLD)}")
        for ex in shown:
            add(f"    {c('-', DIM)} {_truncate(ex.text)}")
        add("")

    if result.errors:
        add(f"  {c(f'{len(result.errors)} messages raised inside your filter:', RED, BOLD)}")
        for ex, err in result.errors[:samples]:
            add(f"    {c('-', DIM)} {err}  {c(_truncate(ex.text, 50), DIM)}")
        add(f"    {c('An exception is counted as a miss, not a catch.', DIM)}")
        add("")

    add(f"  {c(f'{result.total} messages in {result.elapsed_ms:.0f} ms', DIM)}")
    add("")
    return "\n".join(out)
