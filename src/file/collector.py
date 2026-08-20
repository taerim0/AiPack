import os
from pathlib import Path
import pathspec

from file.textutil import read_text

# Common reproducible build outputs / dependency & tool caches, across
# ecosystems beyond the JS/Python ones already listed above. Not exhaustive
# (no fixed list can be) -- the content-based binary filter in collect_files()
# below is the general safety net; this just pre-skips whole directories that
# would otherwise get walked and read one file at a time for no reason.
DEFAULT_IGNORE = [
    "node_modules/",
    ".git/",
    "__pycache__/",
    "*.pyc",
    "dist/",
    "build/",
    "*.log",
    "*.lock",
    ".env",
    "venv/",
    ".venv/",

    ".gradle/",
    ".mvn/",
    "target/",
    ".next/",
    ".nuxt/",
    ".cache/",
    ".parcel-cache/",
    ".turbo/",

    ".pytest_cache/",
    ".mypy_cache/",
    ".tox/",
    ".ruff_cache/",
    "coverage/",
    ".nyc_output/",

    ".terraform/",
    ".DS_Store",
    "Thumbs.db",
]

def collect_files(root_path: str) -> list[str]:
    root = Path(root_path)

    ignore_patterns = DEFAULT_IGNORE.copy()
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8") as f:
            gitignore_lines = [
                line.strip()
                for line in f.readlines()
                if line.strip() and not line.startswith("#")
            ]
        ignore_patterns.extend(gitignore_lines)

    spec = pathspec.PathSpec.from_lines("gitwildmatch", ignore_patterns)

    collected = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip walking into excluded directories entirely
        dirnames[:] = [
            d for d in dirnames
            if not spec.match_file(
                str(Path(dirpath).relative_to(root) / d) + "/"
            )
        ]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            relative = file_path.relative_to(root)
            if spec.match_file(str(relative)):
                continue

            # No name-pattern list can enumerate every binary format a project
            # might contain (images, fonts, compiled artifacts, checksums...).
            # Detect it directly instead: a file unreadable as text has nothing
            # for the LLM to summarize, and letting it through just means a
            # summary hallucinated from the filename alone, wasted tokens in
            # every downstream step, and a wasted LLM call.
            if read_text(str(file_path)) is None:
                continue

            collected.append(str(file_path))

    return sorted(collected)


def print_tree(files: list[str], root_path: str):
    root = Path(root_path)
    print(f"\n{root.name}/")
    for file_path in files:
        relative = Path(file_path).relative_to(root)
        depth = len(relative.parts) - 1
        indent = "  " * depth
        print(f"{indent}├── {relative.name}")