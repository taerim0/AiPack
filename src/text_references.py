"""Detects references to other collected project files inside non-code
text content (JSON, Markdown, plain text, Godot .tscn/.tres scenes, etc.)
-- files with no Tree-sitter grammar, so extract_dependencies() always
returns [] for them, meaning they never showed up as anything but leaves
in `relationships` even when they obviously reference other project files
(a Godot scene's `[ext_resource path="res://player.gd"]`, a Markdown link,
a config value naming another file).

Deliberately not LLM-based: matching against the *actual* list of already-
collected file paths (not a generic "looks like a path" regex) makes this
free and precise -- unlike extract_dependencies()'s raw import strings,
which need resolve_dependency() to check later whether they match a real
file, a match found here already IS a real collected file, so it can go
straight into `dependencies` the same way a resolved import would (see
packager.py's per-file loop -- it's appended there, not routed through any
separate resolve step).
"""

import re


def find_text_references(content: str, self_path: str, other_paths: list[str]) -> list[str]:
    """Returns the subset of other_paths (relative, POSIX-style keys -- see
    file/textutil.py's relative_key(), which is what produces them) that
    appear referenced inside content. self_path is excluded even if
    pathologically self-referential.

    Two match forms per candidate, both word-boundary anchored (so
    "player.gd" doesn't match inside "multiplayer.gd" or "player.gdx"):
    - the full relative path ("scenes/player.gd") -- how Godot's res://
      scheme and a relative Markdown link actually write it.
    - just the filename+extension ("player.gd") -- the common case of a
      reference that omits the directory (a config value, "see player.gd"
      in a doc).

    Bare stems (no extension, e.g. "player") are deliberately never
    matched -- "config"/"main"/"index"/"utils" are common enough words that
    matching them against arbitrary prose would produce far more noise than
    signal; requiring the extension is most of what keeps this precise.
    """
    found = []
    for other in other_paths:
        if other == self_path:
            continue
        filename = other.rsplit("/", 1)[-1]
        if _contains_token(content, other) or _contains_token(content, filename):
            found.append(other)
    return found


def _contains_token(content: str, token: str) -> bool:
    """Word-boundary-anchored substring search. re.escape(token) so path
    separators/dots in it are matched literally, not as regex metacharacters.
    (?<!\\w)/(?!\\w) rather than plain \\b: \\b only fires at a \\w/\\W
    transition, and "/"/"." are already \\W, so a plain \\b placed right
    before a leading path separator or after a trailing one doesn't reliably
    require what we actually want -- only an *adjacent letter/digit/
    underscore* should disqualify a match as "part of a different, larger
    token" (a leading "/" or "." is a normal, expected path delimiter, not a
    sign of a false positive).
    """
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", content) is not None
