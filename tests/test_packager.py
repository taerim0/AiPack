"""Covers packager.py's non-interactive failure handling -- not the full
pack() pipeline, which needs a live LLM call. handle_llm_failure() and
_resume_checkpoint_choice() are the two places pack() used to call input()
unconditionally, crashing with EOFError under closed stdin (e.g. `pack
--auto-correct` in CI) instead of degrading gracefully.
"""

import builtins

import packager


def test_handle_llm_failure_non_interactive_checkpoints_without_prompting(tmp_path, monkeypatch):
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path)

    def _unexpected_input(*a, **k):
        raise AssertionError("input() must not be called when interactive=False")

    monkeypatch.setattr(builtins, "input", _unexpected_input)

    result = packager.handle_llm_failure(
        "rules", "코딩 룰", {"project": {"name": "x"}}, "some/project", interactive=False
    )

    assert result == "EXIT"
    assert (tmp_path / "project.json").exists()


def test_handle_llm_failure_interactive_still_prompts(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "1")

    result = packager.handle_llm_failure(
        "rules", "코딩 룰", {"project": {"name": "x"}}, "some/project", interactive=True
    )

    assert result is None  # "1" = retry


def test_resume_checkpoint_choice_non_interactive_always_resumes(monkeypatch):
    def _unexpected_input(*a, **k):
        raise AssertionError("input() must not be called when interactive=False")

    monkeypatch.setattr(builtins, "input", _unexpected_input)

    assert packager._resume_checkpoint_choice(interactive=False) is True


def test_resume_checkpoint_choice_interactive_respects_choice(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "2")
    assert packager._resume_checkpoint_choice(interactive=True) is False

    monkeypatch.setattr(builtins, "input", lambda *a, **k: "")
    assert packager._resume_checkpoint_choice(interactive=True) is True
