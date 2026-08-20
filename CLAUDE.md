# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Directory-scoped detail lives in nested CLAUDE.md files, loaded automatically when you're working in that subtree — this file stays high-level on purpose:
- `src/extract/CLAUDE.md` — Tree-sitter code compression/extraction (`languages.py`/`parser.py`/`extractor.py`/`compressor.py`) + the non-Tree-sitter text compressors (json/markdown/txt).
- `src/file/CLAUDE.md` — file collection, security scanning, and the dependency-graph API (`collector.py`/`scanner.py`/`selector.py`/`relationship.py`).

## What this is

Ziplex converts a local project into `aif.json` — a structured, token-reduced context format ("AIF") that an AI can consume instantly instead of reading raw files. It combines Tree-sitter-based code compression/extraction, an LLM summarization pass (Gemini), and an optional human correction step.

`aif.json` itself only ever carries summaries + relationships, not full per-file code — see the shape at the bottom of this file.

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
python src/cli.py signatures|dependencies|api|compress|debug <single_file>
```
*`--auto --auto-correct` skips `corrector.py` entirely, but `packager.py`'s `handle_llm_failure()` (when rules/prompt generation exhausts its retries) still falls back to an `input()` prompt regardless of these flags — under heavy LLM rate-limiting this can still block on stdin. Known gap, not yet fixed.

Tests (`tests/`, pytest via `pytest.ini` which puts `src/` on `pythonpath`):
```
pip install -r requirement-dev.txt   # adds pytest on top of requirement.txt
pytest
```
Covers the deterministic, non-LLM logic only — compressors, extractor, `file/collector.py`'s ignore/binary filtering, `file/relationship.py`'s graph ops, `edits.py`'s pure setters, and `tokenizer.py`'s counting. Nothing calls Gemini or needs `GEMINI_API_KEY`. `testfiles/` is separate — sample input for manual, ad-hoc CLI runs, not part of the test suite.

## Architecture

`src/cli.py` is a thin argparse dispatcher; all real logic lives in the modules it calls. The `pack` command runs the full pipeline end to end:

1. **`file/collector.py`** → **`file/scanner.py`** → **`file/selector.py`** — collect, security-scan, and (unless `--auto`) interactively select files. Detail: `src/file/CLAUDE.md`.
2. **`extract/code/*`** + **`extract/text/*`** — Tree-sitter signature/dependency/API extraction and body-stripping compression for code; regex-based compression for JSON/Markdown/plain text. Detail: `src/extract/CLAUDE.md`.
3. **`tokenizer.py`** — counts tokens per model (`tiktoken`). `analyze_tokens_with_compression` (the standalone `tokens` command) measures original vs. compressed body only; `analyze_tokens_with_payload` (used by `pack`) measures original vs. just the per-file `summary` — the only per-file field that actually ships in the saved `aif.json`.
4. **`llm.py`** — Gemini REST calls (`gemini-flash-latest`, via `requests`, not the SDK) for per-file summaries, coding-rule inference, and the project-level AI guide. `LLMProvider` (a `typing.Protocol`) is the seam for adding another model — implement `generate(prompt, retry) -> str` and register it in `PROVIDERS`. Retries on HTTP 429/503 with backoff.
5. **`packager.py`** (`pack()`) — orchestrates 1–4, and owns **checkpointing**: `handle_llm_failure()` lets a failing LLM call be retried, answered manually, or checkpointed to `checkpoint/<project_name>.json` for the next `pack` run on the same path to auto-detect and resume.
6. **`edits.py`** + **`file/relationship.py`** — the pure, I/O-free editing API (no `input()`/`print()`): field setters, `finalize_aif()` (builds `relationships`, prunes now-redundant `signatures`/`dependencies`/`api`), and the dependency-graph operations (`build_tree`/`move_file`/`has_cycle`). This is the seam a future MCP server or GUI backend would call directly with structured input instead of parsed terminal strings. Detail (especially `has_cycle`'s traversal direction — easy to get backwards): `src/file/CLAUDE.md`.
7. **`corrector.py`** — the thin interactive CLI wrapper around 6: walks the user through project name/guide/rules/summaries/reparenting, calling the matching pure function for each accepted change. `--auto-correct` skips this module entirely and calls `edits.finalize_aif()` directly.
8. **`packager.py`** (`save_aif()`) — pulls `compressed` out of each file entry into a sibling `<name>.detail.json`, so the saved `aif.json` only ever carries `summary` per file (files with little to strip, like README/config/lang files, would otherwise cost more tokens shipped than they save).

The final `aif.json` shape: `{ project: {name, prompt}, rules: [...], tokens: {...}, files: {name: {summary}}, relationships: {...} }`, with a sibling `<name>.detail.json` shaped `{ file-name: {compressed}, ... }` (same file-name keys as `files`, flat — not nested under a `files` key).

Every LLM-facing function in `llm.py` follows the same contract: prompt says "JSON only, nothing else," caller does `json.loads()` and falls back to a default (`{}`, `[]`, `""`) on `JSONDecodeError` — callers in `packager.py` loop until they get a non-empty result or the user intervenes via `handle_llm_failure`.
