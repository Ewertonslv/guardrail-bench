import re

import pytest

from guardrail_bench.target import TargetError, load_target, regex_target


def test_loads_from_a_file(tmp_path):
    mod = tmp_path / "guard.py"
    mod.write_text("def is_injection(text):\n    return 'ignore' in text\n", encoding="utf-8")
    predicate = load_target(f"{mod}:is_injection")
    assert predicate("please ignore that")
    assert not predicate("hello")


def test_loads_a_compiled_regex_object(tmp_path):
    mod = tmp_path / "guard.py"
    mod.write_text("import re\nPATTERN = re.compile(r'ignore', re.I)\n", encoding="utf-8")
    predicate = load_target(f"{mod}:PATTERN")
    assert predicate("IGNORE this")
    assert not predicate("hello")


def test_loads_from_an_importable_module():
    predicate = load_target("re:match")
    assert callable(predicate)


def test_windows_drive_letter_survives(tmp_path):
    """A path like C:\\x\\guard.py:fn must split on the LAST colon, not the first."""
    mod = tmp_path / "guard.py"
    mod.write_text("def fn(text):\n    return True\n", encoding="utf-8")
    spec = f"{mod}:fn"
    assert spec.count(":") >= 1
    assert load_target(spec)("anything")


def test_missing_colon_is_a_clear_error():
    with pytest.raises(TargetError, match="module:function"):
        load_target("myapp.filters")


def test_missing_attribute_is_a_clear_error(tmp_path):
    mod = tmp_path / "guard.py"
    mod.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(TargetError, match="no attribute"):
        load_target(f"{mod}:nope")


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(TargetError, match="file not found"):
        load_target(f"{tmp_path / 'nope.py'}:fn")


def test_unimportable_module_suggests_the_file_form():
    with pytest.raises(TargetError, match="point at the file directly"):
        load_target("definitely_not_a_real_module_xyz:fn")


def test_non_callable_target_is_rejected(tmp_path):
    mod = tmp_path / "guard.py"
    mod.write_text("VALUE = 42\n", encoding="utf-8")
    with pytest.raises(TargetError, match="neither callable nor a compiled regex"):
        load_target(f"{mod}:VALUE")


def test_import_error_inside_the_target_file_is_surfaced(tmp_path):
    mod = tmp_path / "guard.py"
    mod.write_text("raise RuntimeError('bad config')\n", encoding="utf-8")
    with pytest.raises(TargetError, match="raised while importing"):
        load_target(f"{mod}:fn")


def test_regex_target():
    predicate = regex_target(r"ignore.{0,40}instructions")
    assert predicate("Ignore all previous INSTRUCTIONS")
    assert not predicate("ignore " + "x" * 60 + " instructions")


def test_invalid_regex_is_a_clear_error():
    with pytest.raises(TargetError, match="invalid regex"):
        regex_target("(unclosed")


def test_regex_target_matches_across_newlines():
    predicate = regex_target(r"ignore.{0,40}instructions")
    assert predicate("ignore\nthe previous instructions")
