# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Directory-scoped detail lives in nested CLAUDE.md files, loaded automatically when you're working in that subtree — this file stays high-level on purpose:
- `src/extract/CLAUDE.md` — Tree-sitter code compression/extraction (`languages.py`/`parser.py`/`extractor.py`/`compressor.py`) + the non-Tree-sitter text compressors (json/markdown/txt).
- `src/file/CLAUDE.md` — file collection, security scanning, and the dependency-graph API (`collector.py`/`scanner.py`/`selector.py`/`relationship.py`).

## What this is

Local project → `aif.json`: a token-reduced context format an AI reads instead of raw files. Pipeline: Tree-sitter compression/extraction → Gemini summarization → optional human correction. `aif.json` carries only summaries + relationships, never full per-file code — shape at the bottom of this file.

## Commands

Setup (Windows, matches the existing `venv/` in this repo):
```
venv\Scripts\activate
pip install -r requirement.txt   # note: filename has no "s"
```

Requires a `.env` with `GEMINI_API_KEY=...` (read via `python-dotenv` in `src/llm.py`).

Run any subcommand from repo root:
```
python src/cli.py pack <project_path>                              # full pipeline, interactive file selection + correction
python src/cli.py pack <project_path> --auto                       # skip interactive selection, include all safe files
python src/cli.py pack <project_path> --auto-correct                # skip interactive correction, auto-accept LLM output
python src/cli.py pack <project_path> --auto --auto-correct         # non-interactive*, for CI/scripted use
python src/cli.py pack <project_path> -o out.json                  # custom output path (also writes out.detail.json)

python src/cli.py collect <project_path>            # just file collection + security scan
python src/cli.py tokens <project_path>             # token count, before/after compression
python src/cli.py tree <project_path>                # dependency tree only
python src/cli.py search <project_path> <pattern> --context 2 --ignore-case  # regex search across safe files
python src/cli.py detail <name>.detail.json <file-key> --start 10 --end 40   # partial read of one file's compressed body
python src/cli.py freshness <project_path> <name>.cache.json                # hash-check aif.json against disk, no LLM calls
python src/cli.py signatures|dependencies|api|compress|debug <single_file>
```

MCP server (exposes an already-packed project's `aif.json`/`detail.json`, read-only — see the `mcp_server.py` bullet below):
```
python src/mcp_server.py                                  # run directly, stdio transport
claude mcp add ziplex -- python src/mcp_server.py          # register with Claude Code (from repo root)
```
*`--auto --auto-correct` makes `pack` fully non-interactive: `packager.py`'s `handle_llm_failure()` and its checkpoint-resume prompt both take an `interactive` flag now (threaded from `--auto-correct`) and skip straight to their non-interactive default — checkpoint-and-exit, and always-resume, respectively — instead of calling `input()` against a closed stdin.

Tests (`tests/`, pytest via `pytest.ini` which puts `src/` on `pythonpath`):
```
pip install -r requirement-dev.txt   # adds pytest on top of requirement.txt
pytest
```
Covers the deterministic, non-LLM logic only — compressors, extractor, `file/collector.py`'s ignore/binary filtering, `file/relationship.py`'s graph ops, `edits.py`'s pure setters, `search.py`, `freshness.py`, and `tokenizer.py`'s counting, plus `packager.py`'s non-interactive failure handling (`handle_llm_failure`/`_resume_checkpoint_choice` with `interactive=False`, monkeypatching `input` to assert it's never called). `tests/test_pack_integration.py` runs the *full* `pack()` pipeline end to end (checkpointing, parallel summaries, rules/prompt, token counting) against `llm.MockProvider` instead of Gemini — see the `llm.py` bullet below. `tests/test_mcp_server.py` checks the MCP-specific wiring (tool registration, docstring-as-description, `call_tool` dispatch) on top of that — see the `mcp_server.py` bullet below. Nothing in the suite calls Gemini or needs `GEMINI_API_KEY`. `testfiles/` is separate — sample input for manual, ad-hoc CLI runs, not part of the test suite.

For a quick manual smoke test against a real project without waiting on Gemini: `LLM_PROVIDER=mock python src/cli.py pack <project_path> --auto --auto-correct` runs the whole pipeline in well under a second, network-free.

## Architecture

`src/cli.py` is a thin argparse dispatcher; all real logic lives in the modules it calls. The `pack` command runs the full pipeline end to end:

1. **`file/collector.py`** → **`file/scanner.py`** → **`file/selector.py`** — collect, security-scan, and (unless `--auto`) interactively select files. Detail: `src/file/CLAUDE.md`.
2. **`extract/code/*`** + **`extract/text/*`** — Tree-sitter signature/dependency/API extraction and body-stripping compression for code; regex-based compression for JSON/Markdown/plain text. Detail: `src/extract/CLAUDE.md`.
3. **`tokenizer.py`** — counts tokens per model (`tiktoken`). `analyze_tokens_with_compression` (the standalone `tokens` command) measures original vs. compressed body only; `analyze_tokens_with_payload` (used by `pack`) measures original vs. just the per-file `summary` — the only per-file field that actually ships in the saved `aif.json`.
4. **`llm.py`** — Gemini REST calls (`gemini-flash-latest`, via `requests`, not the SDK) for per-file summaries, coding-rule inference, and the project-level AI guide. `LLMProvider` (a `typing.Protocol`) is the seam for adding another model — implement `generate(prompt, retry) -> str` and register it in `PROVIDERS`. Retries on HTTP 429/503 with backoff. `PROVIDERS["mock"]` (`MockProvider`) is a working example of that seam: pattern-matches the JSON field name in a prompt's trailing example and returns a fixed, valid response of the right shape, network-free. Select it with `LLM_PROVIDER=mock` for manual runs (read once, at import time, into the module-level `_provider`) — tests instead `monkeypatch.setattr(llm, "_provider", llm.MockProvider())`, which works regardless of import order since `generate()` looks `_provider` up as a module global on every call.
5. **`packager.py`** (`pack()`) — orchestrates 1–4, and owns **checkpointing**: `handle_llm_failure()` lets a failing LLM call be retried, answered manually, or checkpointed to `checkpoint/<project_name>.json` for the next `pack` run on the same path to auto-detect and resume. `pack(..., interactive=False)` (what `--auto-correct` sets) skips every prompt this function and the checkpoint-resume check could otherwise raise — both default to their safe non-interactive behavior (checkpoint-and-exit; always-resume) instead of calling `input()`.
6. **`edits.py`** + **`file/relationship.py`** — the pure, I/O-free editing API (no `input()`/`print()`): field setters, `finalize_aif()` (builds `relationships`, prunes now-redundant `signatures`/`dependencies`/`api`), and the dependency-graph operations (`build_tree`/`move_file`/`has_cycle`). This is the seam a future MCP server or GUI backend would call directly with structured input instead of parsed terminal strings. Detail (especially `has_cycle`'s traversal direction — easy to get backwards): `src/file/CLAUDE.md`.
7. **`corrector.py`** — the thin interactive CLI wrapper around 6: walks the user through project name/guide/rules/summaries/reparenting, calling the matching pure function for each accepted change. `--auto-correct` skips this module entirely and calls `edits.finalize_aif()` directly.
8. **`packager.py`** (`save_aif()`) — splits two things out of `aif` into sibling files: `compressed` per file → `<name>.detail.json`, so the saved `aif.json` only ever carries `summary` per file (files with little to strip, like README/config/lang files, would otherwise cost more tokens shipped than they save); and the flat `_manifest` (a `{file: content hash}` map `pack()` attaches, see `freshness.py` below) → `<name>.cache.json`, packaging-internal bookkeeping that never appears in `aif.json` itself.

**`freshness.py`** sits outside the `pack` sequence like `search.py` below — `pack()` calls `build_manifest()` to attach the hash snapshot `save_aif()` writes to `<name>.cache.json`; later, `check_freshness()` re-hashes a project's current files and diffs them against a loaded manifest (changed/added/removed), with no Tree-sitter parsing and no LLM calls. This only *detects* drift between `aif.json` and the files it was packed from — it doesn't refresh anything itself, that's still a full `pack` re-run. (Stage 2, not built: reusing the same manifest to skip re-summarizing unchanged files on a re-pack — see the `ziplex-roadmap` memory.) Exposed via the `freshness` CLI subcommand and the MCP server's `check_freshness` tool.

**`search.py`** sits outside the `pack` sequence — pure query functions over an already-collected file set or an already-generated `detail.json`, built as MCP prep (see `ziplex-roadmap` memory: benchmarked against repomix's `grep_repomix_output`/`read_repomix_output` MCP tools before writing any MCP code). `search_files()` regex-searches original file content, not `compressed` — a match inside a body-stripped function would otherwise be invisible. `read_detail_range()` slices a `detail.json` entry's `compressed` text by 1-based line range instead of returning it whole. Exposed via the `search`/`detail` CLI subcommands, and (see below) wrapped directly by the MCP server rather than reimplemented there.

**`mcp_server.py`** — the MCP server: seven thin `@mcp.tool()`-decorated wrappers (`get_overview`, `list_files`, `get_dependents`, `get_blast_radius`, `get_detail`, `check_freshness`, `search_project`) over `edits`/`file/relationship`/`search`/`freshness`'s existing pure functions, using the official `mcp` SDK's `MCPServer` (`from mcp.server import MCPServer`; note the class was renamed from the older `FastMCP` in SDK 2.x — don't go looking for `mcp.server.fastmcp`, it no longer exists). Read-only by design: every tool reads an already-packed `aif.json`/`detail.json`/`cache.json`, or (for `search_project` and `check_freshness`) re-collects and re-security-scans the project fresh from disk on every call — none of them re-pack or re-correct a project, since that would bypass the human-correction step that's core to Ziplex's identity (see the `ziplex-roadmap` memory's "deliberately not copied" note re: repomix's per-call reconfigurable packing). `get_dependents`/`get_blast_radius` are the differentiated addition repomix doesn't have: graph queries over the *human-corrected* `relationships` tree, not just flat summary/detail lookup — `get_blast_radius` can legitimately include the queried file itself when it participates in an import cycle (verified against a real two-class mutual-import case; see `file/relationship.py`'s docstring). Run with `python src/mcp_server.py` (stdio transport, the default `mcp.run()` picks).

The final `aif.json` shape: `{ project: {name, prompt}, rules: [...], tokens: {...}, files: {name: {summary}}, relationships: {...} }`, with siblings `<name>.detail.json` shaped `{ file-name: {compressed}, ... }` and `<name>.cache.json` shaped `{ file-name: content-hash, ... }` (both flat, same file-name keys as `files` — not nested under a `files` key).

Every LLM-facing function in `llm.py` follows the same contract: prompt says "JSON only, nothing else," caller does `json.loads()` and falls back to a default (`{}`, `[]`, `""`) on `JSONDecodeError` — callers in `packager.py` loop until they get a non-empty result or the user intervenes via `handle_llm_failure`.
