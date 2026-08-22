import re

from guardrail_bench.dataset import Example
from guardrail_bench.runner import evaluate


def catch_ignore(text):
    return "ignore" in text.lower() or "disregard" in text.lower()


def test_counts_add_up(examples):
    r = evaluate(catch_ignore, examples)
    assert r.total == len(examples)
    assert r.injections + r.legitimate == r.total
    assert r.true_positives + r.false_negatives == r.injections
    assert r.false_positives + r.true_negatives == r.legitimate


def test_metrics(examples):
    r = evaluate(catch_ignore, examples)
    # catches a1 and a2, misses the leetspeak and the tag injection, flags nothing legitimate
    assert (r.true_positives, r.false_negatives) == (2, 2)
    assert (r.false_positives, r.true_negatives) == (0, 3)
    assert r.recall == 50.0
    assert r.precision == 100.0
    assert r.accuracy == 71.4


def test_perfect_filter(examples):
    r = evaluate(lambda t: True, examples)
    assert r.recall == 100.0
    assert r.false_positives == 3
    assert r.precision == 57.1


def test_filter_that_never_fires(examples):
    r = evaluate(lambda t: False, examples)
    assert r.recall == 0.0
    assert r.precision == 0.0
    assert r.f1 == 0.0
    assert not r.flagged_legitimate


def test_missed_examples_are_reported(examples):
    r = evaluate(catch_ignore, examples)
    assert {e.id for e in r.missed} == {"a3", "a4"}


def test_flagged_legitimate_is_reported(examples):
    r = evaluate(lambda t: "you are" in t, examples)
    assert [e.id for e in r.flagged_legitimate] == ["b3"]


def test_a_raising_filter_counts_as_a_miss_not_a_catch():
    """A filter that explodes must never be scored as if it caught something."""

    def explodes(text):
        raise ValueError("boom")

    rows = [Example("attack", 1, "x"), Example("normal", 0, "y")]
    r = evaluate(explodes, rows)

    assert len(r.errors) == 2
    assert r.true_positives == 0
    assert r.false_negatives == 1
    assert r.recall == 0.0
    assert [e.id for e in r.missed] == ["x"]


def test_truthy_non_bool_return_is_accepted(examples):
    r = evaluate(lambda t: re.search(r"ignore", t), examples)
    assert r.true_positives == 1


def test_to_dict_is_json_safe(examples):
    import json

    payload = evaluate(catch_ignore, examples).to_dict()
    json.dumps(payload)
    assert payload["recall_pct"] == 50.0
