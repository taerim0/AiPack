from pathlib import Path

from file.collector import collect_files


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collects_plain_text_files(tmp_path):
    _write(tmp_path / "main.py", "print('hi')\n")
    _write(tmp_path / "README.md", "# hello\n")

    collected = {Path(f).relative_to(tmp_path).as_posix() for f in collect_files(str(tmp_path))}
    assert collected == {"main.py", "README.md"}


def test_skips_default_ignore_directories(tmp_path):
    _write(tmp_path / "src" / "app.py", "x = 1\n")
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "module.exports = {};\n")
    _write(tmp_path / ".gradle" / "cache.properties", "k=v\n")

    collected = {Path(f).relative_to(tmp_path).as_posix() for f in collect_files(str(tmp_path))}
    assert collected == {"src/app.py"}


def test_respects_project_gitignore(tmp_path):
    _write(tmp_path / ".gitignore", "secrets/\n*.local\n")
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "secrets" / "keys.txt", "shh\n")
    _write(tmp_path / "notes.local", "private\n")

    collected = {Path(f).relative_to(tmp_path).as_posix() for f in collect_files(str(tmp_path))}
    # .gitignore itself isn't matched by its own patterns, so it's collected too
    assert collected == {"app.py", ".gitignore"}


def test_skips_files_that_are_not_decodable_as_text(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    (tmp_path / "sprite.bin").write_bytes(bytes(range(256)))  # not valid utf-8

    collected = {Path(f).relative_to(tmp_path).as_posix() for f in collect_files(str(tmp_path))}
    assert collected == {"app.py"}
