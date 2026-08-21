from cli import _split_patterns, _check_max_tokens


def test_split_patterns_none_when_no_value():
    assert _split_patterns(None) is None
    assert _split_patterns("") is None


def test_split_patterns_splits_on_comma():
    assert _split_patterns("src/**/*.py,*.md") == ["src/**/*.py", "*.md"]


def test_split_patterns_strips_whitespace_around_each_pattern():
    # "src/**/*.py, *.md" (a space after the comma) used to leave " *.md"
    # as a literal leading-space pattern that pathspec matches nothing
    # against, silently dropping every intended file.
    assert _split_patterns("src/**/*.py, *.md , other/**") == ["src/**/*.py", "*.md", "other/**"]


def test_split_patterns_drops_empty_entries():
    assert _split_patterns("a.py,,b.py,") == ["a.py", "b.py"]


def _tokens(compressed: int) -> dict:
    return {"GPT-4o": {"original": 9999, "compressed": compressed, "saved_pct": 0.0}}


def test_check_max_tokens_passes_when_under_budget():
    passed, actual = _check_max_tokens(_tokens(100), max_tokens=200, model="GPT-4o")
    assert passed is True
    assert actual == 100


def test_check_max_tokens_passes_when_exactly_at_budget():
    passed, actual = _check_max_tokens(_tokens(200), max_tokens=200, model="GPT-4o")
    assert passed is True
    assert actual == 200


def test_check_max_tokens_fails_when_over_budget():
    passed, actual = _check_max_tokens(_tokens(300), max_tokens=200, model="GPT-4o")
    assert passed is False
    assert actual == 300


def test_check_max_tokens_returns_none_for_unknown_model():
    passed, actual = _check_max_tokens(_tokens(100), max_tokens=200, model="Not-A-Real-Model")
    assert passed is False
    assert actual is None
