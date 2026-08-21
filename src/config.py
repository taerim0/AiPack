"""Per-project Ziplex configuration -- an optional `.ziplex.json` living in
the *target* project's own root (not Ziplex's own repo), analogous to
repomix's repomix.config.json but always optional: every setting has a
safe default, and pack() behaves identically to today with no config file
at all.

Deliberately small in scope for now: include/ignore glob patterns only --
the gap flagged when comparing against repomix's CLI (file selection used
to be all-or-nothing: everything safe via --auto, or one file at a time via
the interactive picker, with no way to scope a pack to e.g. just `src/**`
up front without clicking through everything else to exclude it).

Living in the target project (not Ziplex's own repo) means it's committable
there the same way a team already commits aif.json/detail.json/cache.json
(see the README's "Team use" section) -- it documents "how this project
gets packed" alongside the project itself, not as Ziplex-side state keyed
by a path that could move.
"""
import json
from pathlib import Path

CONFIG_FILENAME = ".ziplex.json"

DEFAULT_CONFIG = {
    "include": [],
    "ignore": [],
}


def load_config(project_path: str) -> dict:
    """Reads <project_path>/.ziplex.json if it exists, merged over
    DEFAULT_CONFIG so a partial file (or no file at all) still yields every
    key `pack()`/`collect_files()` expect. Never raises: a missing file, an
    unreadable file, invalid JSON, or a JSON value that isn't an object all
    fall back to DEFAULT_CONFIG unchanged -- a broken config file shouldn't
    be able to block a pack, only fail to customize it.
    """
    config = dict(DEFAULT_CONFIG)
    config_path = Path(project_path) / CONFIG_FILENAME
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError):
        return config

    if isinstance(loaded, dict):
        for key in DEFAULT_CONFIG:
            if key in loaded:
                config[key] = loaded[key]
    return config


def init_config(project_path: str) -> str:
    """Writes a starter .ziplex.json (DEFAULT_CONFIG's empty include/ignore
    -- JSON has no comments, so example patterns can't live inline the way
    a repomix.config.json's generated comments do; the README documents the
    syntax instead) to project_path, unless one already exists there.

    Idempotent and non-destructive: an existing config is left untouched
    and its path is returned as-is, exactly like a fresh write would --
    callers can't tell from the return value alone whether a file was
    created or already existed (see the CLI's own message for that).
    """
    config_path = Path(project_path) / CONFIG_FILENAME
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return str(config_path)
