"""Detects whether a project's aif.json/detail.json output has drifted from
the actual files on disk -- without re-running any part of pack(). No
Tree-sitter parsing, no LLM calls, just a hash comparison.

aif.json/detail.json are snapshots from the last pack() run, and every MCP
tool except search_project() (which always re-reads files live) trusts that
snapshot as-is. This is the tool to check whether that trust is still
warranted before relying on (or re-packing) a project.

This module only detects drift -- it doesn't refresh anything itself.
packager.pack() is what actually uses check_freshness()'s `unchanged` list,
to reuse a previous run's summary for any file whose content hash hasn't
changed instead of paying for another LLM call.
"""

import hashlib
from dataclasses import dataclass, field

from file.textutil import read_text, relative_key


def hash_file(file_path: str) -> str | None:
    """SHA-256 of a file's text content, or None if it can't be read as text.

    Matches collect_files()'s own binary filter -- a file that wouldn't be
    packed in the first place has no meaningful hash to compare.
    """
    content = read_text(file_path)
    if content is None:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_manifest(file_paths: list[str], root: str) -> dict[str, str]:
    """{relative path: content hash} for every file_paths entry that's
    actually readable as text -- the shape pack() persists alongside its
    output (as <name>.cache.json, via save_aif()) so a later
    check_freshness() call has something to compare against.
    """
    manifest = {}
    for file_path in file_paths:
        digest = hash_file(file_path)
        if digest is not None:
            manifest[relative_key(file_path, root)] = digest
    return manifest


@dataclass(frozen=True)
class FreshnessReport:
    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        return bool(self.changed or self.added or self.removed)


def check_freshness(file_paths: list[str], root: str, manifest: dict[str, str]) -> FreshnessReport:
    """Compares file_paths' current content hashes against a previously
    saved manifest (build_manifest()'s output, e.g. loaded from a
    <name>.cache.json). Doesn't touch aif.json/detail.json itself -- just
    reports whether they're still trustworthy.

    file_paths should be the project's current safe/selected file list
    (e.g. from collect_files() + scan_files()), not just whatever's already
    in `manifest` -- that's what makes added/removed files detectable, not
    only changed ones.
    """
    current = build_manifest(file_paths, root)

    changed = sorted(
        name for name, digest in current.items()
        if name in manifest and manifest[name] != digest
    )
    added = sorted(name for name in current if name not in manifest)
    removed = sorted(name for name in manifest if name not in current)
    unchanged = sorted(
        name for name, digest in current.items()
        if name in manifest and manifest[name] == digest
    )

    return FreshnessReport(changed=changed, added=added, removed=removed, unchanged=unchanged)
