import json

import pytest

from guardrail_bench.cli import EXIT_BELOW_THRESHOLD, EXIT_OK, EXIT_USAGE, main


@pytest.fixture
def guard_file(tmp_path):
    path = tmp_path / "guard.py"
    path.write_text(
        "def is_injection(text):\n"
        "    low = text.lower()\n"
        "    return 'ignore' in low or 'disregard' in low\n",
        encoding="utf-8",
    )
    return path


def test_happy_path(guard_file, dataset_file, capsys):
    code = main([f"{guard_file}:is_injection", "--dataset", str(dataset_file), "--no-color"])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "RECALL" in out
    assert "50.0%" in out
    assert "7 messages" in out


def test_json_output_is_parseable(guard_file, dataset_file, capsys):
    code = main([f"{guard_file}:is_injection", "--dataset", str(dataset_file), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["recall_pct"] == 50.0
    assert payload["dataset"].endswith("corpus.jsonl")
    assert len(payload["missed"]) == 2


def test_regex_mode(dataset_file, capsys):
    code = main(["--regex", "ignore|disregard", "--dataset", str(dataset_file), "--json"])
    assert code == EXIT_OK
    assert json.loads(capsys.readouterr().out)["recall_pct"] == 50.0


def test_target_and_regex_are_mutually_exclusive(dataset_file):
    with pytest.raises(SystemExit) as exc:
        main(["some:thing", "--regex", "x", "--dataset", str(dataset_file)])
    assert exc.value.code == EXIT_USAGE


def test_neither_target_nor_regex(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == EXIT_USAGE


def test_fail_under_trips(guard_file, dataset_file, capsys):
    code = main([f"{guard_file}:is_injection", "--dataset", str(dataset_file), "--fail-under", "60", "--no-color"])
    assert code == EXIT_BELOW_THRESHOLD
    assert "below --fail-under" in capsys.readouterr().err


def test_fail_under_passes(guard_file, dataset_file):
    assert main([f"{guard_file}:is_injection", "--dataset", str(dataset_file), "--fail-under", "50"]) == EXIT_OK


def test_bad_target_exits_cleanly(dataset_file, capsys):
    code = main(["no_such_module_xyz:fn", "--dataset", str(dataset_file)])
    assert code == EXIT_USAGE
    assert "guardrail-bench:" in capsys.readouterr().err


def test_missing_dataset_exits_cleanly(guard_file, tmp_path, capsys):
    code = main([f"{guard_file}:is_injection", "--dataset", str(tmp_path / "nope.jsonl")])
    assert code == EXIT_USAGE
    assert "not found" in capsys.readouterr().err


def test_dataset_without_injections_is_rejected(guard_file, tmp_path, capsys):
    path = tmp_path / "all_benign.jsonl"
    path.write_text('{"text": "hello", "label": 0}\n', encoding="utf-8")
    code = main([f"{guard_file}:is_injection", "--dataset", str(path)])
    assert code == EXIT_USAGE
    assert "recall is undefined" in capsys.readouterr().err


def test_report_shows_the_misses(guard_file, dataset_file, capsys):
    main([f"{guard_file}:is_injection", "--dataset", str(dataset_file), "--no-color"])
    out = capsys.readouterr().out
    assert "Injections it let through" in out
    assert "1gn0r3" in out


def test_samples_zero_hides_examples(guard_file, dataset_file, capsys):
    main([f"{guard_file}:is_injection", "--dataset", str(dataset_file), "--samples", "0", "--no-color"])
    assert "Injections it let through" not in capsys.readouterr().out


def test_a_raising_filter_is_reported_not_crashed(tmp_path, dataset_file, capsys):
    path = tmp_path / "bad_guard.py"
    path.write_text("def boom(text):\n    raise ValueError('nope')\n", encoding="utf-8")
    code = main([f"{path}:boom", "--dataset", str(dataset_file), "--no-color"])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "raised inside your filter" in out
    assert "0.0%" in out
