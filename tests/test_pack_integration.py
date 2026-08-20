"""End-to-end pack() test using llm.MockProvider instead of a live Gemini
call -- validates the pipeline's actual orchestration (checkpointing,
parallel per-file summaries, rules/prompt generation, token counting,
aif.json assembly) runs correctly wired together, without the cost/latency/
non-determinism of a real LLM call.

monkeypatching llm._provider (rather than the LLM_PROVIDER env var) works
regardless of import order: generate() looks up _provider as a module
global on every call, so this takes effect even though llm may already have
been imported -- with whatever provider LLM_PROVIDER resolved to at that
point -- by an earlier test file.
"""

import json

import llm
import packager


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_pack_runs_end_to_end_with_mock_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "README.md", "# Sample\n\nA sample project.\n")

    aif = packager.pack(str(project), auto=True, interactive=False)

    assert aif["project"]["name"] == "project"
    assert aif["project"]["prompt"] == "Mock AI guide for local testing."
    assert aif["rules"] == ["mock rule: methods use camelCase"]
    assert set(aif["files"].keys()) == {"main.py", "README.md"}

    for name, data in aif["files"].items():
        assert data["summary"] == "Mock summary for local testing."
        assert "compressed" in data, name

    assert "GPT-4o" in aif["tokens"]
    assert aif["tokens"]["GPT-4o"]["original"] > 0

    # no checkpoint should be left behind on a clean success
    assert not (tmp_path / "checkpoint" / "project.json").exists()

    # pack() attaches a content-hash manifest for freshness.check_freshness()
    assert set(aif["_manifest"].keys()) == {"main.py", "README.md"}


def test_save_aif_writes_a_sibling_cache_json_from_the_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(packager, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")

    aif = packager.pack(str(project), auto=True, interactive=False)
    output_path = tmp_path / "out" / "project.json"
    packager.save_aif(aif, str(output_path))

    cache_path = output_path.with_name("project.cache.json")
    assert cache_path.exists()
    manifest = json.loads(cache_path.read_text(encoding="utf-8"))
    assert list(manifest.keys()) == ["main.py"]

    # _manifest is packaging-internal bookkeeping -- must not leak into the
    # saved aif.json itself
    saved_aif = json.loads(output_path.read_text(encoding="utf-8"))
    assert "_manifest" not in saved_aif
