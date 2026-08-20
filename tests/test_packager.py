"""Covers packager.py's non-interactive failure handling -- not the full
pack() pipeline, which needs a live LLM call. handle_llm_failure() and
_resume_checkpoint_choice() are the two places pack() used to call input()
unconditionally, crashing with EOFError under closed stdin (e.g. `pack
--auto-correct` in CI) instead of degrading gracefully.
"""

import builtins
import json

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


def test_chunked_splits_into_groups_of_size():
    assert packager._chunked(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]


def test_request_batch_summaries_uses_the_batch_response_when_complete(monkeypatch):
    monkeypatch.setattr(
        packager, "analyze_batch_summaries",
        lambda items: json.dumps({"summaries": {"a.py": "does a", "b.py": "does b"}}),
    )

    def _unexpected_fallback(*a, **k):
        raise AssertionError("_request_summary must not be called when the batch response is complete")

    monkeypatch.setattr(packager, "_request_summary", _unexpected_fallback)

    batch = [("a.py", {"signatures": [], "dependencies": []}), ("b.py", {"signatures": [], "dependencies": []})]
    assert packager._request_batch_summaries(batch) == {"a.py": "does a", "b.py": "does b"}


def test_request_batch_summaries_falls_back_per_file_on_a_missing_key(monkeypatch):
    # the batch response only covers a.py -- b.py must fall back
    # individually rather than the whole batch being lost
    monkeypatch.setattr(
        packager, "analyze_batch_summaries",
        lambda items: json.dumps({"summaries": {"a.py": "does a"}}),
    )
    monkeypatch.setattr(packager, "_request_summary", lambda name, data: f"fallback for {name}")

    batch = [("a.py", {"signatures": [], "dependencies": []}), ("b.py", {"signatures": [], "dependencies": []})]
    assert packager._request_batch_summaries(batch) == {"a.py": "does a", "b.py": "fallback for b.py"}


def test_request_batch_summaries_falls_back_entirely_on_a_garbled_response(monkeypatch):
    monkeypatch.setattr(packager, "analyze_batch_summaries", lambda items: "not json")
    monkeypatch.setattr(packager, "_request_summary", lambda name, data: f"fallback for {name}")

    batch = [("a.py", {"signatures": [], "dependencies": []})]
    assert packager._request_batch_summaries(batch) == {"a.py": "fallback for a.py"}
