from cli import _split_patterns


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
