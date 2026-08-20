import pytest

from edits import (
    set_project_name,
    set_project_prompt,
    add_rule,
    remove_rule,
    set_file_summary,
    finalize_aif,
)


def _make_aif():
    return {
        "project": {"name": "old-name", "prompt": "old prompt"},
        "rules": ["rule one"],
        "files": {
            "a.py": {
                "summary": "old summary",
                "signatures": ["def a()"],
                "dependencies": ["b"],
                "api": [],
                "compressed": "def a():\n    ...",
            },
            "b.py": {
                "summary": "b summary",
                "signatures": [],
                "dependencies": [],
                "api": [],
                "compressed": "x = 1",
            },
        },
    }


def test_set_project_name_and_prompt():
    aif = _make_aif()
    set_project_name(aif, "new-name")
    set_project_prompt(aif, "new prompt")
    assert aif["project"]["name"] == "new-name"
    assert aif["project"]["prompt"] == "new prompt"


def test_add_and_remove_rule():
    aif = _make_aif()
    add_rule(aif, "rule two")
    assert aif["rules"] == ["rule one", "rule two"]

    remove_rule(aif, 0)
    assert aif["rules"] == ["rule two"]


def test_remove_rule_out_of_range_raises():
    aif = _make_aif()
    with pytest.raises(IndexError):
        remove_rule(aif, 5)


def test_set_file_summary():
    aif = _make_aif()
    set_file_summary(aif, "a.py", "new summary")
    assert aif["files"]["a.py"]["summary"] == "new summary"


def test_set_file_summary_unknown_file_raises():
    aif = _make_aif()
    with pytest.raises(KeyError):
        set_file_summary(aif, "missing.py", "summary")


def test_finalize_aif_builds_relationships_and_prunes_working_fields():
    aif = _make_aif()
    finalize_aif(aif)

    assert aif["relationships"]["a.py"] == {"internal": ["b.py"], "external": []}

    for data in aif["files"].values():
        assert "signatures" not in data
        assert "dependencies" not in data
        assert "api" not in data
        # summary/compressed are what actually ships -- must survive
        assert "summary" in data
        assert "compressed" in data
