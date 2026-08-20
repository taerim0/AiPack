"""Ziplex MCP server: exposes an already-packed project (`aif.json` plus its
sibling `<name>.detail.json`) as MCP tools, plus project-wide search.

Read-only by design -- this serves a human-curated pack (see edits.py /
corrector.py), it never re-packs or re-corrects a project on its own. That's
a deliberate choice, not a missing feature: Ziplex's identity is "a human
curates once, this serves that curated result," and letting an agent
silently trigger a fresh (uncorrected) pack would undercut the reason the
correction step exists. See the `ziplex-roadmap` memory for the full
benchmarking against repomix's MCP server that this design is based on.

Every tool below is a thin wrapper over an existing pure function
(edits.py / file/relationship.py / search.py) -- nothing here has logic of
its own beyond loading JSON off disk and shaping the response, by design:
the same functions are exercised directly (and faster) by the pytest suite.

Run directly:
    python src/mcp_server.py
Add to Claude Code (from the repo root):
    claude mcp add ziplex -- python src/mcp_server.py
"""

import json
from pathlib import Path

from mcp.server import MCPServer

from file.collector import collect_files
from file.scanner import scan_files
from file.relationship import get_dependents as _get_dependents, get_blast_radius as _get_blast_radius
from search import search_files, read_detail_range
from freshness import check_freshness as _check_freshness

mcp = MCPServer("ziplex")


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _detail_path(aif_path: str) -> Path:
    """<name>.detail.json sits next to aif.json under the same stem -- the
    convention save_aif() writes to (packager.py). Not configurable, so
    every tool that needs detail content just derives it from aif_path.
    """
    p = Path(aif_path)
    return p.with_name(f"{p.stem}.detail.json")


def _cache_path(aif_path: str) -> Path:
    """<name>.cache.json, same sibling-file convention as _detail_path()."""
    p = Path(aif_path)
    return p.with_name(f"{p.stem}.cache.json")


@mcp.tool()
def get_overview(aif_path: str) -> dict:
    """Project name, AI-facing guide, inferred coding rules, and token stats
    for an already-packed project. Call this first -- it's the cheapest,
    always-affordable view of a project, and enough context for many
    questions on its own without fetching any file's detail.
    """
    aif = _load_json(aif_path)
    return {
        "project": aif.get("project", {}),
        "rules": aif.get("rules", []),
        "tokens": aif.get("tokens", {}),
        "file_count": len(aif.get("files", {})),
    }


@mcp.tool()
def list_files(aif_path: str) -> dict:
    """Every file in the project mapped to its one-line summary and a
    heuristic confidence score (0.0-1.0, see src/confidence.py) for how well
    that summary's wording actually matches the file's extracted signatures
    -- not a correctness guarantee, but a low score is a real reason to
    fetch get_detail and check for yourself before trusting the summary.
    Use this to decide which file (if any) is worth that closer look --
    summaries are already loaded here at effectively no cost; full source
    is not.
    """
    aif = _load_json(aif_path)
    return {
        name: {"summary": data.get("summary", ""), "confidence": data.get("confidence", 1.0)}
        for name, data in aif.get("files", {}).items()
    }


@mcp.tool()
def get_dependents(aif_path: str, file: str) -> list[str]:
    """Files that directly depend on `file` -- who would need a second look
    if `file` changes. `file` is a key from list_files()'s result.
    """
    aif = _load_json(aif_path)
    return _get_dependents(aif.get("relationships", {}), file)


@mcp.tool()
def get_blast_radius(aif_path: str, file: str) -> list[str]:
    """Every file affected by a change to `file`, directly or transitively --
    the full impact set, not just its immediate dependents. Built on the
    same human-corrected dependency graph as get_dependents(), which is why
    this is worth calling instead of guessing from imports yourself.
    """
    aif = _load_json(aif_path)
    return _get_blast_radius(aif.get("relationships", {}), file)


@mcp.tool()
def get_detail(aif_path: str, file: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """The compressed source for one file -- structure and signatures kept,
    function bodies elided. Fetch this only once a summary or a dependents/
    blast-radius query says `file` is actually worth a closer look; it costs
    far more tokens than the summary every other tool here returns. Pass
    start_line/end_line (1-based, inclusive) to read part of a large file
    instead of the whole thing.
    """
    detail = _load_json(str(_detail_path(aif_path)))
    entry = detail.get(file)
    if entry is None:
        raise ValueError(f"{file!r} not found in {_detail_path(aif_path)}")
    return read_detail_range(entry.get("compressed", ""), start_line, end_line)


@mcp.tool()
def check_freshness(project_path: str, aif_path: str) -> dict:
    """Checks whether aif_path's pack is still current relative to
    project_path's actual files on disk -- a hash comparison, no LLM calls
    and no re-extraction, so it's cheap enough to call before trusting
    get_overview/list_files/get_dependents/get_blast_radius/get_detail on a
    project you suspect has changed since it was last packed. (search_project
    never needs this -- it always reads files live, never aif.json/
    detail.json.) Reports which files changed, were added, were removed, or
    are unchanged since the pack aif_path came from; doesn't fix anything
    itself -- a stale result still means re-running `pack`.
    """
    manifest = _load_json(str(_cache_path(aif_path)))
    files = collect_files(project_path)
    safe_files = scan_files(files)["safe"]
    report = _check_freshness(safe_files, project_path, manifest)
    return {
        "is_stale": report.is_stale,
        "changed": report.changed,
        "added": report.added,
        "removed": report.removed,
        "unchanged": report.unchanged,
    }


@mcp.tool()
def search_project(project_path: str, pattern: str, context_lines: int = 0, ignore_case: bool = False) -> list[dict]:
    """Regex search across the project's original files -- use this when you
    don't already know which file has what you're after (get_detail needs a
    filename; this doesn't). Unlike the other tools here, this doesn't read
    aif.json/detail.json at all: it re-collects and re-security-scans the
    project fresh on every call, straight from project_path, so results are
    always current even if aif.json is stale and secrets are still filtered
    even if the project changed since the last pack.
    """
    files = collect_files(project_path)
    safe_files = scan_files(files)["safe"]
    matches = search_files(safe_files, project_path, pattern, context_lines, ignore_case)
    return [
        {
            "file": m.file,
            "line": m.line_number,
            "text": m.line,
            "context_before": m.context_before,
            "context_after": m.context_after,
        }
        for m in matches
    ]


if __name__ == "__main__":
    mcp.run()
