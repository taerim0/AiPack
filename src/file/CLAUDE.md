# src/file/ — collection, security scan, selection, dependency graph

Scoped notes for `file/collector.py`, `file/scanner.py`, `file/selector.py`, `file/relationship.py`, `file/textutil.py`. See the root `CLAUDE.md` for how these fit into the overall `pack` pipeline.

## collector.py

`collect_files(root_path)` walks the tree and excludes two ways:
- **`DEFAULT_IGNORE`** — a curated pattern list (node_modules/, build caches like `.gradle/`/`target/`/`.pytest_cache/`, OS junk, etc.) plus whatever the project's own `.gitignore` adds, compiled together via `pathspec.PathSpec.from_lines("gitignore", ...)`. (Not `"gitwildmatch"` — that pattern factory is deprecated in the installed `pathspec` version; `"gitignore"` is the behavior-identical replacement.) This list can never be exhaustive across every build tool, and it's cheap to check (skips whole directories before reading any file content), so it's the first filter, not the only one.
- **Content-based binary filter** — any file `read_text()` can't decode as UTF-8 is dropped regardless of name/extension. This is the actual safety net: no fixed ignore list can enumerate every binary format a project might contain, but a file being non-text is directly checkable. Before this existed, a binary file that slipped past `DEFAULT_IGNORE` would still get an LLM summary "hallucinated" purely from its filename (see `packager.py`'s `_request_summary`) — pure token overhead with zero real content behind it.

## scanner.py

`scan_file()` tries `secretlint` as a subprocess first (`_scan_with_secretlint`); if it errors, isn't installed, or its JSON output doesn't parse, falls back to `_scan_with_pattern()` (the `SENSITIVE_PATTERNS` regex list — API keys, passwords, tokens, etc.). Either way a match means the file goes to `scan_files()`'s `"dangerous"` bucket and never reaches Tree-sitter/LLM stages.

## selector.py

Thin interactive terminal prompt (`select_files`) over the scanner's `"safe"` list. Skipped entirely by `pack --auto` (or the `tokens`/`collect` CLI subcommands, which never call it).

## relationship.py

The pure dependency-graph API — no I/O, callable from a terminal flow (`corrector.py`) or anything else (a future MCP server/GUI).

- **`build_stem_map`/`resolve_dependency`** — matches a raw import string (e.g. `"extract.code.extractor"`, or a `.`-separated module path) against the actual collected file names, via the last dotted segment. Handles both a fresh Tree-sitter-extracted import path and an already-pinned file name from a prior `move_file()` call.
- **`build_tree(files)`** — for each file, splits its `dependencies` into `internal` (resolves to another collected file) and `external` (doesn't), deduping and dropping self-references from `internal`. This is what becomes the final `relationships` field in `aif.json`.
- **`has_cycle(files, stem_map, from_file, to_file)`** — checks whether `from_file` already (transitively) depends on `to_file`. **Direction matters and is easy to get backwards**: `move_file()` is about to add the edge "`to_file` depends on `from_file`" (a dependency entry is a *child* in the tree), and that closes a cycle exactly when `from_file` can already reach `to_file` by walking its own existing dependency chain — so the walk starts at `from_file`, not `to_file`. This exact direction was inverted for a while before being caught by `tests/test_relationship.py::test_has_cycle_detects_transitive_cycle_through_a_third_file` (concretely: with `z→y→x` already, moving `z` under `x` produced an undetected `x→z→y→x` cycle). If you touch this function, that test is the regression guard — keep it passing.
- **`move_file(files, file_name, new_parent)`** — reparents `file_name`, first stripping it from wherever it's currently listed as a dependency (regardless of whether that entry was a raw import path or an already-pinned name from an earlier move), then appending it to `new_parent`'s `dependencies`. Raises `ValueError` for an unknown/self target, `CycleError` (via `has_cycle`) if the move would close a loop.
- **`print_tree`** — recursive renderer for the CLI's `tree` subcommand; separate from (but shaped like) `corrector.py`'s own interactive tree renderer, which needs per-line index numbers for file selection that `print_tree` doesn't.
