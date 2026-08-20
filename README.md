# Ziplex

**English** | [한국어](README_ko.md)

**Turn any local project into a context file an AI can load instantly — instead of reading through hundreds of raw files.**

Ziplex walks a project, compresses and structures it with Tree-sitter, summarizes it with an LLM, and lets a human correct the result before it ships. The output is `aif.json`: a small, structured "AI context format" file.

> ⚠️ Under active development. Interfaces and output format may still change.

---

## How it works

```
project/  ──►  collect  ──►  security scan  ──►  select  ──►  parse & extract
                                                                     │
              aif.json  ◄──  human correction  ◄──  LLM summarize  ◄┘
             + detail.json
```

1. **Collect** — walk the project, skipping `node_modules/`, build caches (`.gradle/`, `target/`, `.pytest_cache/`, …), and anything the project's own `.gitignore` excludes. Any file that can't be decoded as text (images, binaries, compiled artifacts) is dropped too — no fixed ignore list can name every binary format, so this is checked directly rather than guessed from the filename.
2. **Security scan** — every remaining file is checked for secrets (API keys, passwords, tokens) via `secretlint`, with a regex-based fallback if it isn't installed. Flagged files never enter the pipeline.
3. **Select** — interactively choose which files to include, or skip straight to everything safe with `--auto`.
4. **Parse & extract** — Tree-sitter parses each supported source file to pull out function signatures, imports, and (for decorator-based routes) API endpoints.
5. **Compress** — function bodies are replaced with a single marker, keeping structure while cutting tokens. Non-code text (JSON, Markdown, plain text) gets its own compression pass — Markdown code blocks even reuse the code compressor by detected language.
6. **Summarize** — Gemini generates a one-line summary per file, plus project-wide coding rules inferred from the collected signatures and an AI-facing guide describing the project.
7. **Correct** — a human reviews and edits the project name, guide, rules, and every summary, then can manually reparent files in the dependency tree (with cycle detection) before the final relationship graph is built.
8. **Package** — the lean `aif.json` (summary + relationships) is written for immediate loading; the heavier compressed code goes into a sibling `detail.json`, kept on disk for on-demand use rather than shipped on every file by default.

## Features

- **Multi-language code compression** — Python, Java, TypeScript, and JavaScript today, via a per-language config table (`LanguageConfig`) so adding a new grammar is a single entry, not a rewrite.
- **Text-aware compression beyond code** — dedicated compressors for JSON and Markdown (including embedded code fences) and plain text, using the same body-preserving philosophy as the code compressor.
- **Security scanning built in** — `secretlint` first, regex fallback second; sensitive files never make it past collection.
- **Human-in-the-loop correction, opt-in** — every LLM output (summaries, rules, project guide, dependency tree) is reviewable and editable before anything is saved, or skippable entirely with `--auto-correct`. File selection (`--auto`) and correction (`--auto-correct`) are independent flags, so `pack` can run fully headless for CI or scripted use.
- **Honest token accounting** — `tiktoken`-based before/after comparison across GPT-4o, GPT-3.5, and GPT-4 encodings, measured against what actually ships in `aif.json`, not just the raw compression ratio.
- **Lean output, detail on request** — `aif.json` stays small (summaries + relationships); the full compressed body per file lives in `detail.json`, ready to be fetched on demand once an MCP layer exists.
- **Resilient to LLM flakiness** — retries with backoff on rate limits, and a checkpoint system that lets a failed run resume later instead of restarting from scratch.
- **Provider-agnostic LLM layer** — swapping Gemini for another model is implementing one `generate()` method and registering it, not touching the rest of the pipeline.
- **Not just for git repos** — works on any collection of local files with relationships across extensions: game mods, asset projects, whatever isn't a typical software repo.

## Quick start

```bash
venv\Scripts\activate
pip install -r requirement.txt        # note: filename has no "s"
```

Add a `.env` with `GEMINI_API_KEY=...`, then:

```bash
# Full pipeline: collect, scan, select, compress, summarize, correct
python src/cli.py pack ./your-project/

# Skip interactive file selection, include everything safe
python src/cli.py pack ./your-project/ --auto

# Skip interactive correction, auto-accept whatever the LLM produced
python src/cli.py pack ./your-project/ --auto-correct

# Fully non-interactive (CI, scripted runs) -- file selection and correction
# are independent flags, so any combination of the two works
python src/cli.py pack ./your-project/ --auto --auto-correct

# Custom output path (writes out.json + out.detail.json)
python src/cli.py pack ./your-project/ -o output/out.json
```

<details>
<summary>Every command</summary>

| Command | Description |
|---|---|
| `pack <path>` | Full pipeline — the one most people want |
| `collect <path>` | File collection + security scan only |
| `tokens <path>` | Token count, before/after compression |
| `tree <path>` | Dependency tree only |
| `search <path> <pattern>` | Regex search across all safe files (`--context N`, `--ignore-case`) |
| `detail <name>.detail.json <file-key>` | Partial read of one file's compressed body (`--start`/`--end`) |
| `select <path>` | Interactive file selection only |
| `analyze <path>` | LLM analysis only |
| `signatures \| dependencies \| api \| compress \| debug <file>` | Run one extraction step on a single file |

</details>

## Testing

```bash
pip install -r requirement-dev.txt   # adds pytest on top of requirement.txt
pytest
```

Covers the deterministic core — compressors, the Tree-sitter extractor, the collector's ignore/binary-file filtering, the dependency-graph operations (`build_tree`/`has_cycle`/`move_file`), and the pure `aif`-editing API — plus a full `pack()` run against a network-free `MockProvider` instead of Gemini, exercising checkpointing, parallel summaries, and token counting end to end without the cost or latency of a real LLM call.

Want to smoke-test `pack` against a real project without waiting on Gemini? `LLM_PROVIDER=mock python src/cli.py pack <project> --auto --auto-correct` runs the whole pipeline network-free in under a second.

## Output format

```jsonc
// aif.json — small, loaded up front
{
  "project": { "name": "...", "prompt": "..." },
  "rules": ["..."],
  "tokens": { "GPT-4o": { "original": 3100, "compressed": 749, "saved_pct": 75.8 } },
  "files": { "src/App.tsx": { "summary": "..." } },
  "relationships": { "src/App.tsx": { "internal": ["..."], "external": ["react"] } }
}
```

```jsonc
// out.detail.json — heavier, fetched only when a file actually needs a closer look
{
  "src/App.tsx": { "compressed": "import React ...\n    ⋮----\nexport default App" }
}
```

## Tech stack

Python 3.11 · [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) (Python/Java/TypeScript/JavaScript grammars) · [tiktoken](https://github.com/openai/tiktoken) · Gemini API (`gemini-flash-latest`, plain REST via `requests`) · `secretlint` · `pathspec`

## Roadmap

**MCP integration** — expose `aif.json`/`detail.json` as an MCP server so tools like Claude Code or Cursor can query project context on demand, pulling summaries first and fetching a specific file's detail only when it's actually needed. *The output format was already split into a lean/detail shape to make this a natural next step, not a rewrite.*

**Selective file delivery to AI** — pick specific files in Ziplex and send them straight into a chat with full context attached (dependencies, signature, summary) — no copy-pasting.

**Relationship analysis across all file types** — extend the dependency graph past code files, using LLM inference to connect config, text, and binary assets into the same picture.

**Expanded language support** — broader Tree-sitter coverage for game-specific languages (GDScript, Lua, ZenScript) and additional frameworks.

## License

[MIT](LICENSE)
