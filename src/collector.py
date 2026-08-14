import os
from pathlib import Path
import pathspec

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
        for filename in filenames:
            file_path = Path(dirpath) / filename
            relative = file_path.relative_to(root)
            if spec.match_file(str(relative)):
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