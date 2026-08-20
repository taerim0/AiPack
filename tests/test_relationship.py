import pytest

from file.relationship import (
    build_tree, has_cycle, move_file, build_stem_map, CycleError,
    get_dependents, get_blast_radius,
)


def test_build_tree_splits_internal_and_external():
    files = {
        "a.py": {"dependencies": ["b", "os"]},
        "b.py": {"dependencies": []},
    }
    tree = build_tree(files)
    assert tree["a.py"] == {"internal": ["b.py"], "external": ["os"]}
    assert tree["b.py"] == {"internal": [], "external": []}


def test_build_tree_dedupes_and_excludes_self_reference():
    files = {
        "a.py": {"dependencies": ["b", "b", "a"]},  # duplicate + self-import
        "b.py": {"dependencies": []},
    }
    tree = build_tree(files)
    assert tree["a.py"]["internal"] == ["b.py"]


def test_has_cycle_detects_would_be_cycle():
    # b already depends on a; making a depend on b too (moving b under a)
    # would close a -> b -> a
    files = {
        "a.py": {"dependencies": []},
        "b.py": {"dependencies": ["a"]},
    }
    stem_map = build_stem_map(files.keys())
    assert has_cycle(files, stem_map, "b.py", "a.py") is True
    # the reverse isn't a cycle: a doesn't depend on anything yet
    assert has_cycle(files, stem_map, "a.py", "b.py") is False


def test_has_cycle_detects_transitive_cycle_through_a_third_file():
    # z -> y -> x already; moving z under x would close x -> z -> y -> x
    files = {
        "x.py": {"dependencies": []},
        "y.py": {"dependencies": ["x"]},
        "z.py": {"dependencies": ["y"]},
    }
    stem_map = build_stem_map(files.keys())
    assert has_cycle(files, stem_map, "z.py", "x.py") is True


def test_move_file_reparents_and_removes_from_old_parent():
    files = {
        "a.py": {"dependencies": ["b"]},
        "b.py": {"dependencies": []},
        "c.py": {"dependencies": []},
    }
    move_file(files, "b.py", "c.py")

    assert "b" not in files["a.py"]["dependencies"]
    assert files["c.py"]["dependencies"] == ["b.py"]


def test_move_file_raises_on_cycle():
    files = {
        "a.py": {"dependencies": []},
        "b.py": {"dependencies": ["a"]},  # b depends on a
    }
    with pytest.raises(CycleError):
        move_file(files, "b.py", "a.py")  # would make a depend on b too -> a <-> b


def test_move_file_raises_on_unknown_or_self():
    files = {"a.py": {"dependencies": []}, "b.py": {"dependencies": []}}

    with pytest.raises(ValueError):
        move_file(files, "a.py", "a.py")

    with pytest.raises(ValueError):
        move_file(files, "missing.py", "b.py")


def test_get_dependents_finds_direct_dependents_only():
    # b and c both depend on a; c also depends on b
    relationships = {
        "a.py": {"internal": [], "external": []},
        "b.py": {"internal": ["a.py"], "external": []},
        "c.py": {"internal": ["a.py", "b.py"], "external": []},
    }

    assert get_dependents(relationships, "a.py") == ["b.py", "c.py"]
    assert get_dependents(relationships, "b.py") == ["c.py"]
    assert get_dependents(relationships, "c.py") == []


def test_get_blast_radius_is_transitive():
    # c -> b -> a: changing a transitively affects both b and c
    relationships = {
        "a.py": {"internal": [], "external": []},
        "b.py": {"internal": ["a.py"], "external": []},
        "c.py": {"internal": ["b.py"], "external": []},
    }

    assert get_blast_radius(relationships, "a.py") == ["b.py", "c.py"]
    assert get_blast_radius(relationships, "b.py") == ["c.py"]
    assert get_blast_radius(relationships, "c.py") == []


def test_get_blast_radius_handles_a_diamond_without_duplicates():
    # b and c both depend on a; d depends on both b and c
    relationships = {
        "a.py": {"internal": [], "external": []},
        "b.py": {"internal": ["a.py"], "external": []},
        "c.py": {"internal": ["a.py"], "external": []},
        "d.py": {"internal": ["b.py", "c.py"], "external": []},
    }

    assert get_blast_radius(relationships, "a.py") == ["b.py", "c.py", "d.py"]


def test_get_blast_radius_includes_self_when_part_of_a_cycle():
    # a <-> b: a mutual import. A change to a can transitively come back
    # around through b, so a legitimately appears in its own blast radius --
    # this isn't a bug, see get_blast_radius()'s docstring.
    relationships = {
        "a.py": {"internal": ["b.py"], "external": []},
        "b.py": {"internal": ["a.py"], "external": []},
    }

    assert get_blast_radius(relationships, "a.py") == ["a.py", "b.py"]
