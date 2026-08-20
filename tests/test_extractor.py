from extract.code.extractor import extract_signatures, extract_dependencies, extract_api


def test_extract_signatures_from_python_file(tmp_path):
    file_path = tmp_path / "mod.py"
    file_path.write_text(
        "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )

    sigs = extract_signatures(str(file_path))
    assert "add(a, b)" in sigs
    assert "sub(a, b)" in sigs


def test_extract_dependencies_from_python_file(tmp_path):
    file_path = tmp_path / "mod.py"
    file_path.write_text("import os\nfrom pathlib import Path\n\nx = 1\n", encoding="utf-8")

    deps = extract_dependencies(str(file_path))
    assert "os" in deps
    assert "pathlib" in deps


def test_extract_api_detects_decorator_based_routes(tmp_path):
    file_path = tmp_path / "app.py"
    file_path.write_text(
        "@app.get('/users')\n"
        "def list_users():\n"
        "    return []\n",
        encoding="utf-8",
    )

    api = extract_api(str(file_path))
    assert "GET /users" in api


def test_unsupported_extension_returns_empty_lists(tmp_path):
    file_path = tmp_path / "notes.xyz"
    file_path.write_text("whatever", encoding="utf-8")

    assert extract_signatures(str(file_path)) == []
    assert extract_dependencies(str(file_path)) == []
    assert extract_api(str(file_path)) == []
