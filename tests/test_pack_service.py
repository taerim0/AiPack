"""Unit tests for pack_service.py's job lifecycle -- file listing, start/
poll/log capture, the reviewing pause, and submit/cancel -- independent of
gui_server.py's routes (those get their own thin adapter tests in
test_gui_server.py, same split as test_mcp_server.py/test_relationship.py).
Uses llm.MockProvider so these run network-free, same pattern as
test_pack_integration.py.
"""

import json
import time

import llm
import packager
import pack_service
from file.relationship import CycleError


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _wait(job_id, timeout=10):
    """Waits for a job to leave "running" -- into "reviewing" (the normal
    happy path now that packing always pauses for review) or "error".
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = pack_service.get_job_status(job_id)
        if status["state"] != "running":
            return status
        time.sleep(0.02)
    raise AssertionError("pack job did not finish in time")


def test_get_job_status_unknown_job_is_none():
    assert pack_service.get_job_status("no-such-job") is None


def test_list_selectable_files_splits_safe_and_dangerous(tmp_path):
    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "secret.env", 'API_KEY = "abc123"\n')

    result = pack_service.list_selectable_files(str(project))

    assert "main.py" in result["safe"]
    assert "secret.env" in result["dangerous"]


def test_start_pack_job_pauses_in_reviewing_state(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    output_path = tmp_path / "out" / "project.json"

    job_id = pack_service.start_pack_job(str(project), str(output_path), selected_files=["main.py"])
    status = _wait(job_id)

    assert status["state"] == "reviewing"
    assert status["result"] is None
    assert not output_path.exists()  # nothing saved until submit_review()


def test_start_pack_job_only_includes_selected_files(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "README.md", "# Sample\n")

    job_id = pack_service.start_pack_job(str(project), selected_files=["main.py"])
    _wait(job_id)

    review = pack_service.get_review(job_id)
    all_files = [e["file"] for e in review["needs_review"] + review["auto_kept"]]
    assert all_files == ["main.py"]


def test_get_review_returns_none_outside_reviewing_state(tmp_path, monkeypatch):
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "empty_project"
    project.mkdir()
    job_id = pack_service.start_pack_job(str(project), selected_files=["nope.py"])
    status = _wait(job_id)

    assert status["state"] == "error"
    assert pack_service.get_review(job_id) is None
    assert pack_service.get_review("no-such-job") is None


def test_submit_review_applies_edits_and_finalizes(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    output_path = tmp_path / "out" / "project.json"

    job_id = pack_service.start_pack_job(str(project), str(output_path), selected_files=["main.py"])
    _wait(job_id)

    result = pack_service.submit_review(
        job_id,
        project_name="renamed-project",
        project_prompt="Custom AI guide.",
        rules=["custom rule"],
        summaries={"main.py": "Adds two numbers together."},
    )

    assert result == {"aif_path": str(output_path), "project_path": str(project)}
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["project"]["name"] == "renamed-project"
    assert saved["project"]["prompt"] == "Custom AI guide."
    assert saved["rules"] == ["custom rule"]
    assert saved["files"]["main.py"]["summary"] == "Adds two numbers together."
    # finalize_aif() prunes working-state fields from the saved output
    assert "signatures" not in saved["files"]["main.py"]
    assert "relationships" in saved

    status = pack_service.get_job_status(job_id)
    assert status["state"] == "done"
    assert status["result"] == result


def test_submit_review_keeps_unedited_fields_when_blank(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    output_path = tmp_path / "out" / "project.json"

    job_id = pack_service.start_pack_job(str(project), str(output_path), selected_files=["main.py"])
    _wait(job_id)

    pack_service.submit_review(job_id)  # nothing changed, same as pressing enter through every prompt

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["project"]["name"] == "project"
    assert saved["project"]["prompt"] == "Mock AI guide for local testing."
    assert saved["files"]["main.py"]["summary"] == "Mock summary for local testing."


def test_submit_review_unknown_job_raises_value_error():
    try:
        pack_service.submit_review("no-such-job")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_submit_review_wrong_state_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    project = tmp_path / "empty_project"
    project.mkdir()
    job_id = pack_service.start_pack_job(str(project), selected_files=["nope.py"])
    _wait(job_id)  # ends in "error", not "reviewing"

    try:
        pack_service.submit_review(job_id)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_cancel_job_discards_a_reviewing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    output_path = tmp_path / "out" / "project.json"

    job_id = pack_service.start_pack_job(str(project), str(output_path), selected_files=["main.py"])
    _wait(job_id)

    assert pack_service.cancel_job(job_id) is True
    status = pack_service.get_job_status(job_id)
    assert status["state"] == "error"
    assert not output_path.exists()

    # cancelling again (or an unrelated job) is a no-op, not an error
    assert pack_service.cancel_job(job_id) is False
    assert pack_service.cancel_job("no-such-job") is False


def test_review_includes_a_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "a.py", "def a():\n    pass\n")
    _write(project / "b.py", "def b():\n    pass\n")

    job_id = pack_service.start_pack_job(str(project), selected_files=["a.py", "b.py"])
    _wait(job_id)

    review = pack_service.get_review(job_id)
    # neither file imports the other -- both start as roots, no internal edges
    assert review["tree"]["a.py"] == {"internal": [], "external": []}
    assert review["tree"]["b.py"] == {"internal": [], "external": []}


def test_add_dependency_in_job_links_and_returns_updated_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "a.py", "def a():\n    pass\n")
    _write(project / "b.py", "def b():\n    pass\n")

    job_id = pack_service.start_pack_job(str(project), selected_files=["a.py", "b.py"])
    _wait(job_id)

    tree = pack_service.add_dependency_in_job(job_id, "a.py", "b.py")
    assert tree["a.py"]["internal"] == ["b.py"]

    # get_review() (and a later finalize) sees the same edit, not just the
    # return value of add_dependency_in_job() itself
    assert pack_service.get_review(job_id)  # still reviewing, unaffected otherwise


def test_add_dependency_in_job_does_not_disturb_other_files_edges(tmp_path, monkeypatch):
    # the exact bug the earlier drag-and-drop version had: b.py is already
    # depended on by both a.py and c.py -- linking a new edge for a.py must
    # not touch c.py's own reference.
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "a.py", "def a():\n    pass\n")
    _write(project / "b.py", "def b():\n    pass\n")
    _write(project / "c.py", "def c():\n    pass\n")
    _write(project / "d.py", "def d():\n    pass\n")

    job_id = pack_service.start_pack_job(str(project), selected_files=["a.py", "b.py", "c.py", "d.py"])
    _wait(job_id)

    pack_service.add_dependency_in_job(job_id, "a.py", "b.py")
    pack_service.add_dependency_in_job(job_id, "c.py", "b.py")

    tree = pack_service.add_dependency_in_job(job_id, "a.py", "d.py")
    assert tree["a.py"]["internal"] == ["b.py", "d.py"]
    assert tree["c.py"]["internal"] == ["b.py"]  # untouched


def test_add_dependency_in_job_rejects_a_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "a.py", "def a():\n    pass\n")
    _write(project / "b.py", "def b():\n    pass\n")

    job_id = pack_service.start_pack_job(str(project), selected_files=["a.py", "b.py"])
    _wait(job_id)

    pack_service.add_dependency_in_job(job_id, "a.py", "b.py")  # a -> b

    try:
        pack_service.add_dependency_in_job(job_id, "b.py", "a.py")  # would close a -> b -> a
        assert False, "expected CycleError"
    except CycleError:
        pass


def test_remove_dependency_in_job_unlinks_only_that_edge(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "a.py", "def a():\n    pass\n")
    _write(project / "b.py", "def b():\n    pass\n")
    _write(project / "c.py", "def c():\n    pass\n")

    job_id = pack_service.start_pack_job(str(project), selected_files=["a.py", "b.py", "c.py"])
    _wait(job_id)

    pack_service.add_dependency_in_job(job_id, "a.py", "b.py")
    pack_service.add_dependency_in_job(job_id, "a.py", "c.py")

    tree = pack_service.remove_dependency_in_job(job_id, "a.py", "b.py")
    assert tree["a.py"]["internal"] == ["c.py"]


def test_add_dependency_in_job_unknown_job_raises_value_error():
    try:
        pack_service.add_dependency_in_job("no-such-job", "a.py", "b.py")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_remove_dependency_in_job_unknown_job_raises_value_error():
    try:
        pack_service.remove_dependency_in_job("no-such-job", "a.py", "b.py")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_add_dependency_in_job_persists_into_the_finalized_output(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "a.py", "def a():\n    pass\n")
    _write(project / "b.py", "def b():\n    pass\n")
    output_path = tmp_path / "out" / "project.json"

    job_id = pack_service.start_pack_job(str(project), str(output_path), selected_files=["a.py", "b.py"])
    _wait(job_id)

    pack_service.add_dependency_in_job(job_id, "a.py", "b.py")
    pack_service.submit_review(job_id)

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["relationships"]["a.py"]["internal"] == ["b.py"]


def test_get_job_status_since_returns_only_new_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")

    job_id = pack_service.start_pack_job(str(project), selected_files=["main.py"])
    _wait(job_id)

    full = pack_service.get_job_status(job_id)
    assert full["log_len"] == len(full["log"])

    tail = pack_service.get_job_status(job_id, since=full["log_len"])
    assert tail["log"] == []
    assert tail["log_len"] == full["log_len"]


def test_pack_job_on_empty_project_reports_error_state(tmp_path, monkeypatch):
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "empty_project"
    project.mkdir()  # no files at all -> pack() selects nothing and returns {}

    job_id = pack_service.start_pack_job(str(project), selected_files=["whatever.py"])
    status = _wait(job_id)

    assert status["state"] == "error"
    assert status["result"] is None
    assert status["error"]
