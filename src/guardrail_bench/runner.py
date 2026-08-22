"""Run a predicate over a labelled dataset and score it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Sequence

from guardrail_bench.dataset import Example

Predicate = Callable[[str], bool]


@dataclass
class Result:
    total: int = 0
    injections: int = 0
    legitimate: int = 0

    true_positives: int = 0
    false_negatives: int = 0
    false_positives: int = 0
    true_negatives: int = 0

    missed: List[Example] = field(default_factory=list)
    flagged_legitimate: List[Example] = field(default_factory=list)
    errors: List[tuple] = field(default_factory=list)  # (example, exception repr)

    elapsed_ms: float = 0.0

    # --------------------------------------------------------------- metrics

    @staticmethod
    def _pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 1) if den else 0.0

    @property
    def recall(self) -> float:
        return self._pct(self.true_positives, self.true_positives + self.false_negatives)

    @property
    def precision(self) -> float:
        return self._pct(self.true_positives, self.true_positives + self.false_positives)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return round(2 * p * r / (p + r), 1) if (p + r) else 0.0

    @property
    def accuracy(self) -> float:
        return self._pct(self.true_positives + self.true_negatives, self.total)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "injections": self.injections,
            "legitimate": self.legitimate,
            "true_positives": self.true_positives,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "recall_pct": self.recall,
            "precision_pct": self.precision,
            "f1_pct": self.f1,
            "accuracy_pct": self.accuracy,
            "errors": len(self.errors),
            "elapsed_ms": round(self.elapsed_ms, 1),
            "missed": [{"id": e.id, "text": e.text} for e in self.missed],
            "flagged_legitimate": [{"id": e.id, "text": e.text} for e in self.flagged_legitimate],
        }


def evaluate(predicate: Predicate, examples: Sequence[Example]) -> Result:
    """Score `predicate` over `examples`.

    A predicate that raises is not a crash: the message is counted as an error
    and reported. A filter that blows up on adversarial input is itself a
    finding, and hiding it behind a traceback would lose that.
    """
    import time

    result = Result(total=len(examples))
    start = time.perf_counter()

    for example in examples:
        if example.is_injection:
            result.injections += 1
        else:
            result.legitimate += 1

        try:
            flagged = bool(predicate(example.text))
        except Exception as exc:  # noqa: BLE001 - the user's filter, not ours
            result.errors.append((example, repr(exc)))
            # An exception is not a detection. Count it as a miss on the
            # injection side so the recall number stays pessimistic.
            if example.is_injection:
                result.false_negatives += 1
                result.missed.append(example)
            else:
                result.true_negatives += 1
            continue

        if example.is_injection and flagged:
            result.true_positives += 1
        elif example.is_injection:
            result.false_negatives += 1
            result.missed.append(example)
        elif flagged:
            result.false_positives += 1
            result.flagged_legitimate.append(example)
        else:
            result.true_negatives += 1

    result.elapsed_ms = (time.perf_counter() - start) * 1000
    return result
