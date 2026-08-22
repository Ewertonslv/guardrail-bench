"""Resolve the thing under test into a callable that takes str and returns bool.

Three ways to point at a filter, because filters live in awkward places:

    myapp.filters:looks_like_injection      an importable module
    ./scripts/guard.py:is_injection         a file that is not on sys.path
    --regex "ignore.{0,40}instructions"     no code at all
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable

Predicate = Callable[[str], bool]


class TargetError(Exception):
    """The target could not be resolved into something callable."""


def _from_file(path: Path, attr: str) -> object:
    if not path.exists():
        raise TargetError(f"file not found: {path}")
    spec = importlib.util.spec_from_file_location(f"_guardrail_bench_target_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise TargetError(f"cannot import {path} as a Python module")
    module = importlib.util.module_from_spec(spec)
    # Let the file import its own siblings, which is the usual case for a script.
    sys.path.insert(0, str(path.parent.resolve()))
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - surface the user's own import error verbatim
        raise TargetError(f"{path} raised while importing: {exc!r}") from exc
    finally:
        sys.path.pop(0)
    return _getattr(module, attr, str(path))


def _from_module(dotted: str, attr: str) -> object:
    try:
        module = importlib.import_module(dotted)
    except ImportError as exc:
        raise TargetError(
            f"cannot import module {dotted!r}: {exc}. "
            "Run from your project root, or point at the file directly: path/to/file.py:function"
        ) from exc
    return _getattr(module, attr, dotted)


def _getattr(module: object, attr: str, where: str) -> object:
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise TargetError(f"{where} has no attribute {attr!r}") from exc


def _as_predicate(obj: object, label: str) -> Predicate:
    """Accept a callable, or a compiled regex, and normalise to a bool-returning callable."""
    if isinstance(obj, re.Pattern):
        pattern = obj
        return lambda text: bool(pattern.search(text))
    if callable(obj):
        func = obj
        return lambda text: bool(func(text))
    raise TargetError(f"{label} is a {type(obj).__name__}, which is neither callable nor a compiled regex")


def load_target(spec: str) -> Predicate:
    """Load `module:attr` or `path/to/file.py:attr` and return a predicate."""
    if ":" not in spec:
        raise TargetError(
            f"expected 'module:function' or 'path/to/file.py:function', got {spec!r}"
        )
    # rsplit so Windows drive letters (C:\...) survive.
    where, attr = spec.rsplit(":", 1)
    if not where or not attr:
        raise TargetError(f"expected 'module:function', got {spec!r}")

    obj = _from_file(Path(where), attr) if where.endswith(".py") else _from_module(where, attr)
    return _as_predicate(obj, spec)


def regex_target(pattern: str, ignorecase: bool = True) -> Predicate:
    """Build a predicate straight from a pattern, for filters that are just a regex."""
    try:
        compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL if ignorecase else re.DOTALL)
    except re.error as exc:
        raise TargetError(f"invalid regex: {exc}") from exc
    return lambda text: bool(compiled.search(text))
