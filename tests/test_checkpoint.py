"""Covers checkpoint.py's non-interactive failure handling -- not the full
pack() pipeline, which needs a live LLM call. handle_llm_failure() and
resume_checkpoint_choice() are the two places pack() used to call input()
unconditionally, crashing with EOFError under closed stdin (e.g. `pack
--auto-correct` in CI) instead of degrading gracefully.
"""

import builtins

import checkpoint


def test_handle_llm_failure_non_interactive_checkpoints_without_prompting(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path)

    def _unexpected_input(*a, **k):
        raise AssertionError("input() must not be called when interactive=False")

    monkeypatch.setattr(builtins, "input", _unexpected_input)

    result = checkpoint.handle_llm_failure(
        "rules", "코딩 룰", {"project": {"name": "x"}}, "some/project", interactive=False
    )

    assert result == "EXIT"
    assert (tmp_path / "project.json").exists()


def test_handle_llm_failure_interactive_still_prompts(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "1")

    result = checkpoint.handle_llm_failure(
        "rules", "코딩 룰", {"project": {"name": "x"}}, "some/project", interactive=True
    )

    assert result is None  # "1" = retry


def test_resume_checkpoint_choice_non_interactive_always_resumes(monkeypatch):
    def _unexpected_input(*a, **k):
        raise AssertionError("input() must not be called when interactive=False")

    monkeypatch.setattr(builtins, "input", _unexpected_input)

    assert checkpoint.resume_checkpoint_choice(interactive=False) is True


def test_resume_checkpoint_choice_interactive_respects_choice(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "2")
    assert checkpoint.resume_checkpoint_choice(interactive=True) is False

    monkeypatch.setattr(builtins, "input", lambda *a, **k: "")
    assert checkpoint.resume_checkpoint_choice(interactive=True) is True


def test_build_snapshot_keys_files_data_by_relative_name(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    fp = str(root / "src" / "main.py")

    snapshot = checkpoint.build_snapshot(
        root, {fp: {"summary": "does a thing"}}, rules=["rule one"], prompt="a guide"
    )

    assert snapshot == {
        "project": {"name": "project", "prompt": "a guide"},
        "rules": ["rule one"],
        "files_data": {"src/main.py": {"summary": "does a thing"}},
    }


def test_build_snapshot_defaults_rules_and_prompt(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    snapshot = checkpoint.build_snapshot(root, {})
    assert snapshot == {"project": {"name": "project", "prompt": ""}, "rules": [], "files_data": {}}


def test_unpack_snapshot_round_trips_build_snapshot(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    fp = str(root / "src" / "main.py")

    snapshot = checkpoint.build_snapshot(
        root, {fp: {"summary": "does a thing"}}, rules=["rule one"], prompt="a guide"
    )
    rules, prompt, files_data = checkpoint.unpack_snapshot(snapshot)

    assert rules == ["rule one"]
    assert prompt == "a guide"
    assert files_data == {"src/main.py": {"summary": "does a thing"}}


def test_unpack_snapshot_returns_empty_defaults_for_none():
    assert checkpoint.unpack_snapshot(None) == ([], "", {})


def test_save_load_delete_checkpoint_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path)

    assert checkpoint.load_checkpoint("some/project") is None

    checkpoint.save_checkpoint("some/project", {"rules": ["a rule"]})
    assert checkpoint.load_checkpoint("some/project") == {"rules": ["a rule"]}

    checkpoint.delete_checkpoint("some/project")
    assert checkpoint.load_checkpoint("some/project") is None


def test_delete_checkpoint_is_a_no_op_when_none_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path)
    checkpoint.delete_checkpoint("some/project")  # must not raise
