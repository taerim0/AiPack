from pathlib import Path

from freshness import hash_file, build_manifest, check_freshness


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_hash_file_is_stable_for_identical_content(tmp_path):
    _write(tmp_path / "a.py", "x = 1\n")
    _write(tmp_path / "b.py", "x = 1\n")
    assert hash_file(str(tmp_path / "a.py")) == hash_file(str(tmp_path / "b.py"))


def test_hash_file_differs_for_different_content(tmp_path):
    _write(tmp_path / "a.py", "x = 1\n")
    _write(tmp_path / "b.py", "x = 2\n")
    assert hash_file(str(tmp_path / "a.py")) != hash_file(str(tmp_path / "b.py"))


def test_hash_file_returns_none_for_binary(tmp_path):
    (tmp_path / "sprite.bin").write_bytes(bytes(range(256)))
    assert hash_file(str(tmp_path / "sprite.bin")) is None


def test_build_manifest_keys_by_relative_path(tmp_path):
    _write(tmp_path / "sub" / "a.py", "x = 1\n")
    manifest = build_manifest([str(tmp_path / "sub" / "a.py")], str(tmp_path))
    assert list(manifest.keys()) == ["sub/a.py"]


def test_check_freshness_reports_no_drift_when_nothing_changed(tmp_path):
    _write(tmp_path / "a.py", "x = 1\n")
    file_path = str(tmp_path / "a.py")
    manifest = build_manifest([file_path], str(tmp_path))

    report = check_freshness([file_path], str(tmp_path), manifest)

    assert report.is_stale is False
    assert report.changed == []
    assert report.added == []
    assert report.removed == []


def test_check_freshness_detects_a_changed_file(tmp_path):
    _write(tmp_path / "a.py", "x = 1\n")
    file_path = str(tmp_path / "a.py")
    manifest = build_manifest([file_path], str(tmp_path))

    _write(tmp_path / "a.py", "x = 2\n")  # edit after the manifest was taken

    report = check_freshness([file_path], str(tmp_path), manifest)

    assert report.is_stale is True
    assert report.changed == ["a.py"]
    assert report.added == []
    assert report.removed == []


def test_check_freshness_detects_added_and_removed_files(tmp_path):
    _write(tmp_path / "a.py", "x = 1\n")
    _write(tmp_path / "b.py", "y = 1\n")
    old_manifest = build_manifest([str(tmp_path / "a.py"), str(tmp_path / "b.py")], str(tmp_path))

    # b.py deleted, c.py added -- only a.py survives unchanged
    (tmp_path / "b.py").unlink()
    _write(tmp_path / "c.py", "z = 1\n")

    current_files = [str(tmp_path / "a.py"), str(tmp_path / "c.py")]
    report = check_freshness(current_files, str(tmp_path), old_manifest)

    assert report.is_stale is True
    assert report.changed == []
    assert report.added == ["c.py"]
    assert report.removed == ["b.py"]
