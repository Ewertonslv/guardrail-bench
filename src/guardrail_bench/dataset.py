"""Labelled datasets, fetched over HTTP and cached, or read from a local file.

The bundled default is deepset/prompt-injections (Apache-2.0): 662 messages,
263 of them labelled as injection attempts. It is downloaded through the Hugging
Face datasets-server REST API so this package keeps zero runtime dependencies.

Bring your own with --dataset. The format is JSONL, one object per line:

    {"text": "ignore previous instructions", "label": 1}
    {"text": "what time is my appointment?", "label": 0}

label 1 means injection, 0 means legitimate. An `id` field is used if present.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

API = "https://datasets-server.huggingface.co/rows"
PAGE = 100  # datasets-server hard cap per request

DEFAULT_DATASET = "deepset/prompt-injections"
DEFAULT_CONFIG = "default"
DEFAULT_SPLITS = ("train", "test")


@dataclass(frozen=True)
class Example:
    text: str
    label: int  # 1 = injection, 0 = legitimate
    id: str = ""

    @property
    def is_injection(self) -> bool:
        return self.label == 1


class DatasetError(Exception):
    """The dataset could not be loaded."""


# ------------------------------------------------------------------------ cache


def cache_dir() -> Path:
    """Platform cache location, overridable for tests and for air-gapped runs."""
    override = os.environ.get("GUARDRAIL_BENCH_CACHE")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "guardrail-bench"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "guardrail-bench"


def _cache_path(dataset: str) -> Path:
    return cache_dir() / (dataset.replace("/", "__") + ".jsonl")


# ----------------------------------------------------------------------- local


def read_jsonl(path: Path) -> List[Example]:
    if not path.exists():
        raise DatasetError(f"dataset file not found: {path}")
    out: List[Example] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
            if "text" not in row or "label" not in row:
                raise DatasetError(f"{path}:{lineno} needs both 'text' and 'label'")
            try:
                label = int(row["label"])
            except (TypeError, ValueError) as exc:
                raise DatasetError(f"{path}:{lineno} label must be 0 or 1") from exc
            if label not in (0, 1):
                raise DatasetError(f"{path}:{lineno} label must be 0 or 1, got {label}")
            out.append(Example(text=str(row["text"]), label=label, id=str(row.get("id", f"row-{lineno}"))))
    if not out:
        raise DatasetError(f"{path} has no rows")
    return out


def write_jsonl(path: Path, examples: Iterable[Example]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps({"id": ex.id, "text": ex.text, "label": ex.label}, ensure_ascii=False) + "\n")
    tmp.replace(path)


# --------------------------------------------------------------------- remote


def _get_json(url: str, attempts: int = 3, timeout: float = 30.0) -> dict:
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "guardrail-bench"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(2 * (i + 1))
    raise DatasetError(
        f"could not reach {url}: {last}. "
        "If you are offline, pass --dataset with a local JSONL file."
    )


def _fetch_split(dataset: str, config: str, split: str) -> List[Example]:
    rows: List[Example] = []
    offset = 0
    while True:
        params = urllib.parse.urlencode(
            {"dataset": dataset, "config": config, "split": split, "offset": offset, "length": PAGE}
        )
        payload = _get_json(f"{API}?{params}")
        batch = payload.get("rows", [])
        if not batch:
            break
        for item in batch:
            row = item.get("row", {})
            if "text" not in row or "label" not in row:
                raise DatasetError(
                    f"{dataset} split {split} has no text/label columns; it is not a "
                    "binary injection-classification dataset"
                )
            rows.append(
                Example(
                    text=str(row["text"]),
                    label=int(row["label"]),
                    id=f"{split}-{item.get('row_idx', len(rows))}",
                )
            )
        total = payload.get("num_rows_total")
        offset += len(batch)
        if total is not None and offset >= total:
            break
    return rows


def fetch(dataset: str = DEFAULT_DATASET, config: str = DEFAULT_CONFIG,
          splits: Iterable[str] = DEFAULT_SPLITS) -> List[Example]:
    out: List[Example] = []
    for split in splits:
        out.extend(_fetch_split(dataset, config, split))
    if not out:
        raise DatasetError(f"{dataset} returned no rows")
    return out


# ------------------------------------------------------------------------ api


def load_dataset(source: Optional[str] = None, refresh: bool = False) -> List[Example]:
    """Load a local JSONL path, or the named remote dataset, using the cache."""
    if source and (source.endswith(".jsonl") or Path(source).exists()):
        return read_jsonl(Path(source))

    name = source or DEFAULT_DATASET
    cached = _cache_path(name)
    if cached.exists() and not refresh:
        return read_jsonl(cached)

    examples = fetch(name)
    try:
        write_jsonl(cached, examples)
    except OSError:
        pass  # a read-only cache dir is not a reason to fail the run
    return examples
