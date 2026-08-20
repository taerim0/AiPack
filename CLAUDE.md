# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Ziplex converts a local project into `aif.json` — a structured, token-reduced context format ("AIF") that an AI can consume instantly instead of reading raw files. It combines Tree-sitter-based code compression/extraction, an LLM summarization pass (Gemini), and a human correction step.

`aif.json` itself only ever carries summaries + relationships, not full per-file code — see `pack` output below.

## Commands

Setup (Windows, matches the existing `venv/` in this repo):
```
venv\Scripts\activate
pip install -r requirement.txt   # note: filename has no "s"
```

Requires a `.env` with `GEMINI_API_KEY=...` (read via `python-dotenv` in `src/llm.py`).

Run any subcommand from repo root:
```
python src/cli.py pack <project_path>              # full pipeline, interactive file selection + correction
python src/cli.py pack <project_path> --auto        # skip interactive selection, include all safe files
python src/cli.py pack <project_path> -o out.json   # custom output path (also writes out.detail.json)

python src/cli.py collect <project_path>            # just file collection + security scan
python src/cli.py tokens <project_path>             # token count, before/after compression
python src/cli.py tree <project_path>                # dependency tree only
python src/cli.py signatures|dependencies|api|compress|debug <single_file>
```

There is no automated test suite (no `tests/`, no pytest config). `testfiles/` is sample input used for manual, ad-hoc runs of the CLI against — not a test harness.

## Architecture

`src/cli.py` is a thin argparse dispatcher; all real logic lives in the modules it calls. The `pack` command runs the full pipeline end to end, in this order:

1. **`file/collector.py`** — walks the target project, excluding `DEFAULT_IGNORE` patterns plus anything in the project's own `.gitignore` (via `pathspec`).
2. **`file/scanner.py`** — security pass over collected files. Tries `secretlint` as a subprocess first; if secretlint isn't available or errors, falls back to a regex pattern list (`SENSITIVE_PATTERNS`). Files flagged here are excluded from everything downstream.
3. **`file/selector.py`** — interactive terminal prompt for the user to pick which safe files to include (skipped by `--auto`).
4. **`extract/code/parser.py`** — maps file extension → Tree-sitter `Language`/`Parser` (`LANGUAGE_MAP`: `.py`, `.java`, `.ts`, `.js`). Extending language support means adding an entry here.
5. **`extract/code/extractor.py`** — walks the Tree-sitter AST to pull `signatures` (function defs, per `FUNCTION_NODE_TYPES`), `dependencies` (import statements), and `api` (decorator-based route detection, e.g. Flask-style `@app.get(...)`).
6. **`extract/code/compressor.py`** — strips function bodies (replaces with a `⋮----` marker) while keeping signatures/structure, to cut tokens without losing shape.
7. **`tokenizer.py`** — counts tokens per model encoding (`MODEL_ENCODINGS`/`MODEL_MAX_TOKENS`) using `tiktoken`. Two comparisons live here and are not interchangeable: `analyze_tokens_with_compression` (used by the standalone `tokens` CLI command, before any LLM call) measures original vs. just the compressed body text; `analyze_tokens_with_payload` (used by `pack`, after summaries exist) measures original vs. just the per-file `summary` — the only per-file field that actually ships in the saved `aif.json` (see step 12) — which is what an AI reading `aif.json` really pays for.
8. **`llm.py`** — calls the Gemini API (`gemini-flash-latest`) directly via `requests` (not the Gemini SDK) for four jobs: per-file summary (code files are summarized from their extracted `signatures`/`dependencies`; non-code files are summarized from their already-compressed text, not a fresh raw read), coding-rule inference across all signatures, a project-level AI guide prompt, and (unused by `pack` currently) cross-file relationship inference. Retries on HTTP 429/503 with backoff; expects strict-JSON responses and strips markdown code fences (`clean_json`).
9. **`packager.py`** (`pack()`) — orchestrates steps 1–8, and owns **checkpointing**: if an LLM call keeps failing, `handle_llm_failure()` lets the user retry, type a manual value, or save a checkpoint to `checkpoint/<project_name>.json` and exit; the next `pack` run on the same path auto-detects and offers to resume from it. `pack()`'s returned `files.{name}` still carries all five fields (`summary`, `signatures`, `dependencies`, `api`, `compressed`) — steps 10 and 12 below are what pare it down for the saved output.
10. **`corrector.py`** (`correct_aif()`) — after packing, walks the user through correcting the project name, AI guide, rules, and per-file summaries, then interactively lets them reparent files in the dependency tree (with cycle detection) before building the final `relationships` map. `signatures`/`dependencies`/`api` are working state up to this point (dependencies drives the reparenting and `relationships`; signatures fed the rules pass back in `packager.py`) — once `relationships` is built, `correct_aif()` prunes all three from each file entry before returning: `dependencies` is now fully represented by `relationships`, and `signatures`/`api` duplicate what's already inline in `compressed` (only function bodies are stripped, not signatures/imports/decorators).
11. **`file/relationship.py`** — builds/prints the dependency tree, splitting each file's deps into `internal` (another collected file) vs `external` (third-party/stdlib).
12. **`packager.py`** (`save_aif()`) — the last split before disk: pulls `compressed` out of each file entry into a sibling `<name>.detail.json` (`{file: {compressed}}`), so the saved `aif.json` only ever carries `summary` per file. This is deliberate, not an oversight — for files with little or nothing to strip (README, config, lang files, ...) `compressed` is close to the raw original, so shipping it on every file unconditionally would undo the token savings for exactly the files that benefit least from it. Fetching `detail.json` on demand per file (e.g. via an MCP tool, once summary + relationships suggest it's worth a closer look) is future work — for now the data is just kept on disk, not wired up to anything that reads it back in.

The final `aif.json` shape: `{ project: {name, prompt}, rules: [...], tokens: {...}, files: {name: {summary}}, relationships: {...} }`, with a sibling `<name>.detail.json` shaped `{ file-name: {compressed}, ... }` (same file-name keys as `files`, flat — not nested under a `files` key).

Every LLM-facing function in `llm.py` follows the same contract: prompt says "JSON only, nothing else," caller does `json.loads()` and falls back to a default (`{}`, `[]`, `""`) on `JSONDecodeError` — callers in `packager.py` loop until they get a non-empty result or the user intervenes via `handle_llm_failure`.
