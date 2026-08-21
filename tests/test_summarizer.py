"""Covers summarizer.py's batching/fallback logic in isolation from the full
pack() pipeline (see test_pack_integration.py for that, against
llm.MockProvider).
"""

import json

import summarizer


def test_chunked_splits_into_groups_of_size():
    assert summarizer.chunked(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]


def test_request_batch_summaries_uses_the_batch_response_when_complete(monkeypatch):
    monkeypatch.setattr(
        summarizer, "analyze_batch_summaries",
        lambda items: json.dumps({"summaries": {"a.py": "does a", "b.py": "does b"}}),
    )

    def _unexpected_fallback(*a, **k):
        raise AssertionError("request_summary must not be called when the batch response is complete")

    monkeypatch.setattr(summarizer, "request_summary", _unexpected_fallback)

    batch = [("a.py", {"signatures": [], "dependencies": []}), ("b.py", {"signatures": [], "dependencies": []})]
    assert summarizer.request_batch_summaries(batch) == {"a.py": "does a", "b.py": "does b"}


def test_request_batch_summaries_falls_back_per_file_on_a_missing_key(monkeypatch):
    # the batch response only covers a.py -- b.py must fall back
    # individually rather than the whole batch being lost
    monkeypatch.setattr(
        summarizer, "analyze_batch_summaries",
        lambda items: json.dumps({"summaries": {"a.py": "does a"}}),
    )
    monkeypatch.setattr(summarizer, "request_summary", lambda name, data: f"fallback for {name}")

    batch = [("a.py", {"signatures": [], "dependencies": []}), ("b.py", {"signatures": [], "dependencies": []})]
    assert summarizer.request_batch_summaries(batch) == {"a.py": "does a", "b.py": "fallback for b.py"}


def test_request_batch_summaries_falls_back_entirely_on_a_garbled_response(monkeypatch):
    monkeypatch.setattr(summarizer, "analyze_batch_summaries", lambda items: "not json")
    monkeypatch.setattr(summarizer, "request_summary", lambda name, data: f"fallback for {name}")

    batch = [("a.py", {"signatures": [], "dependencies": []})]
    assert summarizer.request_batch_summaries(batch) == {"a.py": "fallback for a.py"}


def test_generate_summaries_returns_a_summary_per_pending_file_keyed_by_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        summarizer, "analyze_batch_summaries",
        lambda items: json.dumps({"summaries": {"a.py": "does a"}}),
    )

    root = tmp_path / "project"
    root.mkdir()
    fp = str(root / "a.py")
    pending = {fp: {"signatures": [], "dependencies": []}}

    assert summarizer.generate_summaries(pending, root) == {fp: "does a"}


def test_generate_summaries_placeholders_a_summary_that_never_comes_back(tmp_path, monkeypatch):
    monkeypatch.setattr(summarizer, "analyze_batch_summaries", lambda items: json.dumps({"summaries": {}}))
    monkeypatch.setattr(summarizer, "request_summary", lambda name, data: "")

    root = tmp_path / "project"
    root.mkdir()
    fp = str(root / "a.py")
    pending = {fp: {"signatures": [], "dependencies": []}}

    assert summarizer.generate_summaries(pending, root) == {fp: "요약 생성 실패"}
