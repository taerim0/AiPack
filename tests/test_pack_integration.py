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

import builtins
import json

import checkpoint
import llm
import packager
import summarizer


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_pack_runs_end_to_end_with_mock_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

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

    # confidence.py: MockProvider's canned summary doesn't mention main.py's
    # actual signature ("add"), so it's correctly flagged low; README.md has
    # no signatures to check against, so there's nothing to contradict
    assert aif["files"]["main.py"]["confidence"] == 0.0
    assert aif["files"]["README.md"]["confidence"] == 1.0

    assert "GPT-4o" in aif["tokens"]
    assert aif["tokens"]["GPT-4o"]["original"] > 0

    # no checkpoint should be left behind on a clean success
    assert not (tmp_path / "checkpoint" / "project.json").exists()

    # pack() attaches a content-hash manifest for freshness.check_freshness()
    assert set(aif["_manifest"].keys()) == {"main.py", "README.md"}


def test_pack_use_llm_false_never_calls_the_llm_and_uses_structural_summaries(tmp_path, monkeypatch):
    # A provider that raises on any call at all -- stricter than counting
    # calls after the fact, since a call this test doesn't expect fails
    # immediately at the point it happens rather than only being caught by
    # a final assertion.
    class _RaisingProvider(llm.MockProvider):
        def generate(self, prompt: str, retry: int = 5) -> str:
            raise AssertionError("use_llm=False must never call the LLM provider")

    monkeypatch.setattr(llm, "_provider", _RaisingProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "README.md", "# Sample\n\nA sample project.\n")

    aif = packager.pack(str(project), auto=True, interactive=False, use_llm=False)

    assert aif["files"]["main.py"]["summary"] == "Defines: add(a, b)"
    # README.md has no Tree-sitter grammar -> no signatures/dependencies at all
    assert "No signatures or dependencies detected" in aif["files"]["README.md"]["summary"]
    assert aif["rules"] == []
    assert aif["project"]["prompt"] == packager.STRUCTURAL_ONLY_NOTE


def test_pack_use_llm_false_still_reuses_a_cached_real_summary(tmp_path, monkeypatch):
    # use_llm=False means "don't call the LLM now," not "throw away a
    # better answer already on hand" -- a file unchanged since a prior
    # LLM-enabled pack should keep that real summary, not get downgraded.
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(packager, "RESULT_DIR", tmp_path / "result")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    packager.save_aif(packager.pack(str(project), auto=True, interactive=False))

    class _RaisingProvider(llm.MockProvider):
        def generate(self, prompt: str, retry: int = 5) -> str:
            raise AssertionError("use_llm=False must never call the LLM provider")

    monkeypatch.setattr(llm, "_provider", _RaisingProvider())
    aif = packager.pack(str(project), auto=True, interactive=False, use_llm=False)

    assert aif["files"]["main.py"]["summary"] == "Mock summary for local testing."


def test_confirm_regenerate_failed_summaries_non_interactive_returns_false_without_prompting(monkeypatch):
    def _unexpected_input(*a, **k):
        raise AssertionError("input() must not be called when interactive=False")

    monkeypatch.setattr(builtins, "input", _unexpected_input)

    assert packager._confirm_regenerate_failed_summaries(["main.py"], interactive=False) is False


def test_confirm_regenerate_failed_summaries_interactive_respects_choice(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "1")
    assert packager._confirm_regenerate_failed_summaries(["main.py"], interactive=True) is True

    monkeypatch.setattr(builtins, "input", lambda *a, **k: "2")
    assert packager._confirm_regenerate_failed_summaries(["main.py"], interactive=True) is False

    monkeypatch.setattr(builtins, "input", lambda *a, **k: "")
    assert packager._confirm_regenerate_failed_summaries(["main.py"], interactive=True) is False


class _EmptySummaryProvider(llm.MockProvider):
    """Answers rules/prompt/relationships normally (via MockProvider) but
    returns an empty payload for any summary-shaped prompt, so every file's
    summary comes back "" and generate_summaries() falls back to
    SUMMARY_FAILED_PLACEHOLDER for each -- sets up "a previous pack already
    cached a failure" without needing a real network failure.
    """

    def generate(self, prompt: str, retry: int = 5) -> str:
        if '"summaries"' in prompt or '"summary"' in prompt:
            return "{}"
        return super().generate(prompt, retry=retry)


def test_pack_prompts_to_regenerate_a_cached_failed_summary_and_honors_yes(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(packager, "RESULT_DIR", tmp_path / "result")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")

    # first pack: the summary call fails for every file, so main.py's cached
    # summary ends up being the literal failure placeholder
    monkeypatch.setattr(llm, "_provider", _EmptySummaryProvider())
    aif1 = packager.pack(str(project), auto=True, interactive=False)
    assert aif1["files"]["main.py"]["summary"] == summarizer.SUMMARY_FAILED_PLACEHOLDER
    packager.save_aif(aif1)

    # second pack: file content unchanged (would normally reuse the cached
    # summary as-is), but interactive + answering "1" should regenerate it
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "1")
    aif2 = packager.pack(str(project), auto=True, interactive=True)

    assert aif2["files"]["main.py"]["summary"] == "Mock summary for local testing."


def test_pack_leaves_cached_failed_summary_when_declined(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(packager, "RESULT_DIR", tmp_path / "result")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")

    monkeypatch.setattr(llm, "_provider", _EmptySummaryProvider())
    aif1 = packager.pack(str(project), auto=True, interactive=False)
    packager.save_aif(aif1)

    # non-interactive: no prompt at all, placeholder stays cached as-is
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    aif2 = packager.pack(str(project), auto=True, interactive=False)
    assert aif2["files"]["main.py"]["summary"] == summarizer.SUMMARY_FAILED_PLACEHOLDER

    # interactive but declined ("2"): same result, by explicit choice
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "2")
    aif3 = packager.pack(str(project), auto=True, interactive=True)
    assert aif3["files"]["main.py"]["summary"] == summarizer.SUMMARY_FAILED_PLACEHOLDER


def test_pack_attaches_tech_stack_detected_from_a_manifest_file(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "requirements.txt", "flask>=2.0\nrequests\n")

    aif = packager.pack(str(project), auto=True, interactive=False)

    assert aif["project"]["tech_stack"] == [{
        "manifest": "requirements.txt",
        "language": "Python",
        "package_manager": "pip",
        "dependencies": ["flask", "requests"],
        "dependencies_truncated": False,
    }]

    # survives finalize_aif() the same way project.name/prompt do -- it's
    # not a per-file field finalize_aif() prunes
    from edits import finalize_aif
    assert finalize_aif(aif)["project"]["tech_stack"] == aif["project"]["tech_stack"]


def test_pack_attaches_an_empty_tech_stack_when_no_manifest_present(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")

    aif = packager.pack(str(project), auto=True, interactive=False)

    assert aif["project"]["tech_stack"] == []


def test_pack_captures_a_text_file_reference_to_a_code_file(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "entities" / "player.gd", "extends Node\nfunc _ready():\n    pass\n")
    # README.md has no Tree-sitter grammar, so extract_dependencies() alone
    # would never connect it to player.gd -- this is exactly the gap
    # text_references.py closes.
    _write(project / "README.md", "See entities/player.gd for the player logic.\n")

    aif = packager.pack(str(project), auto=True, interactive=False)

    assert aif["files"]["README.md"]["dependencies"] == ["entities/player.gd"]
    # and it survives finalize_aif()'s relationship-building the same way a
    # real import would
    from edits import finalize_aif
    final = finalize_aif(aif)
    assert final["relationships"]["README.md"]["internal"] == ["entities/player.gd"]


def test_pack_text_reference_does_not_hijack_the_summary_prompt(tmp_path, monkeypatch):
    # _request_summary()/analyze_batch_summaries() both switch a file's
    # summary prompt from content-based to signature/dependency-based the
    # moment `dependencies` is non-empty -- a text-reference match must not
    # be visible to that decision, or README.md's summary would get
    # generated from `Dependencies: ['entities/player.gd']` alone, having
    # never seen its actual text. MockProvider ignores prompt content
    # entirely, so this needs a provider that records what it was actually
    # asked, not just that *a* summary came back.
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    captured_prompts = []

    class _CapturingMockProvider(llm.MockProvider):
        def generate(self, prompt: str, retry: int = 5) -> str:
            captured_prompts.append(prompt)
            return super().generate(prompt, retry)

    monkeypatch.setattr(llm, "_provider", _CapturingMockProvider())

    project = tmp_path / "project"
    _write(project / "entities" / "player.gd", "extends Node\nfunc _ready():\n    pass\n")
    _write(project / "README.md", "See entities/player.gd for the player logic. UNIQUE_MARKER_TEXT_XYZ\n")

    packager.pack(str(project), auto=True, interactive=False)

    readme_prompts = [p for p in captured_prompts if "README.md" in p]
    assert readme_prompts, "expected at least one summary-generation prompt mentioning README.md"
    assert any("UNIQUE_MARKER_TEXT_XYZ" in p for p in readme_prompts), (
        "README.md's summary prompt should include its actual content (content-based "
        "routing), not just its signatures/dependencies -- got:\n" + "\n---\n".join(readme_prompts)
    )
    assert not any("Dependencies: ['entities/player.gd']" in p for p in readme_prompts), (
        "the text-reference-derived dependency leaked into the summary-routing decision"
    )


def test_pack_scopes_files_via_ziplex_json_include(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "src" / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "README.md", "# Sample\n")
    _write(project / ".ziplex.json", json.dumps({"include": ["src/**"], "ignore": []}))

    aif = packager.pack(str(project), auto=True, interactive=False)

    assert set(aif["files"].keys()) == {"src/main.py"}


def test_pack_include_ignore_params_extend_ziplex_json_not_replace_it(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

    project = tmp_path / "project"
    _write(project / "src" / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "src" / "main.generated.py", "def gen():\n    pass\n")
    _write(project / "README.md", "# Sample\n")
    _write(project / ".ziplex.json", json.dumps({"include": ["src/**"], "ignore": []}))

    # --ignore's pattern layers on top of (not instead of) the config
    # file's own include scope
    aif = packager.pack(str(project), auto=True, interactive=False, ignore=["*.generated.py"])

    assert set(aif["files"].keys()) == {"src/main.py"}


def test_save_aif_writes_a_sibling_cache_json_from_the_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_provider", llm.MockProvider())
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")

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


class _CountingMockProvider(llm.MockProvider):
    """Same fixed responses as MockProvider, but counts calls -- MockProvider
    alone can't tell a caching test whether a summary was actually reused or
    just regenerated identically, since it always returns the same text
    either way. Call count is the only reliable signal.
    """

    def __init__(self):
        self.calls = 0

    def generate(self, prompt: str, retry: int = 5) -> str:
        self.calls += 1
        return super().generate(prompt, retry)


def test_pack_reuses_summaries_for_unchanged_files_on_a_second_run(tmp_path, monkeypatch):
    provider = _CountingMockProvider()
    monkeypatch.setattr(llm, "_provider", provider)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(packager, "RESULT_DIR", tmp_path / "result")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "README.md", "# Sample\n\nA sample project.\n")

    # first pack: main.py + README.md need summarizing, but both fit in one
    # batch (well under BATCH_SIZE) so that's 1 call, plus rules and the AI
    # guide (1 call each) -- everything is new
    aif1 = packager.pack(str(project), auto=True, interactive=False)
    packager.save_aif(aif1)  # default path -> tmp_path/result/project.json, via the monkeypatched RESULT_DIR
    first_run_calls = provider.calls
    assert first_run_calls == 3

    # second pack, nothing on disk changed: both summaries should be reused
    # from result/project.json -- only rules + prompt regenerate (2 calls),
    # since those aren't cached (see pack()'s use_cache docstring)
    provider.calls = 0
    aif2 = packager.pack(str(project), auto=True, interactive=False)

    assert provider.calls == 2
    assert aif2["files"]["main.py"]["summary"] == aif1["files"]["main.py"]["summary"]
    assert aif2["files"]["README.md"]["summary"] == aif1["files"]["README.md"]["summary"]


def test_pack_only_resummarizes_a_changed_file(tmp_path, monkeypatch):
    provider = _CountingMockProvider()
    monkeypatch.setattr(llm, "_provider", provider)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(packager, "RESULT_DIR", tmp_path / "result")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")
    _write(project / "README.md", "# Sample\n")

    packager.save_aif(packager.pack(str(project), auto=True, interactive=False))

    _write(project / "main.py", "def add(a, b):\n    return a + b + 1\n")  # only this one changes
    provider.calls = 0
    packager.pack(str(project), auto=True, interactive=False)

    # 1 batch call (just main.py) + rules + prompt = 3; README.md's summary is reused
    assert provider.calls == 3


def test_pack_splits_into_multiple_batches_past_batch_size(tmp_path, monkeypatch):
    provider = _CountingMockProvider()
    monkeypatch.setattr(llm, "_provider", provider)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(packager, "RESULT_DIR", tmp_path / "result")
    monkeypatch.setattr(summarizer, "BATCH_SIZE", 2)

    project = tmp_path / "project"
    for i in range(5):
        _write(project / f"file{i}.py", f"def fn{i}():\n    return {i}\n")

    packager.pack(str(project), auto=True, interactive=False)

    # 5 files at BATCH_SIZE=2 -> 3 batch calls (2, 2, 1), plus rules + prompt
    assert provider.calls == 5


def test_pack_use_cache_false_resummarizes_everything(tmp_path, monkeypatch):
    provider = _CountingMockProvider()
    monkeypatch.setattr(llm, "_provider", provider)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoint")
    monkeypatch.setattr(packager, "RESULT_DIR", tmp_path / "result")

    project = tmp_path / "project"
    _write(project / "main.py", "def add(a, b):\n    return a + b\n")

    packager.save_aif(packager.pack(str(project), auto=True, interactive=False))

    provider.calls = 0
    packager.pack(str(project), auto=True, interactive=False, use_cache=False)

    # 1 batch call + rules + prompt = 3, same as an unseen project -- nothing reused
    assert provider.calls == 3
