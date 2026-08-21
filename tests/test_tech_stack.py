import json

from tech_stack import detect_tech_stack, MAX_DEPENDENCIES


def _write(path, content):
    path.write_text(content, encoding="utf-8")


def test_returns_empty_list_when_no_manifest_present(tmp_path):
    assert detect_tech_stack(str(tmp_path)) == []


def test_detects_package_json(tmp_path):
    _write(tmp_path / "package.json", json.dumps({
        "dependencies": {"react": "^18.0.0"},
        "devDependencies": {"eslint": "^9.0.0"},
    }))
    stacks = detect_tech_stack(str(tmp_path))
    assert len(stacks) == 1
    assert stacks[0]["manifest"] == "package.json"
    assert stacks[0]["language"] == "JavaScript/TypeScript"
    assert stacks[0]["package_manager"] == "npm"
    assert set(stacks[0]["dependencies"]) == {"react", "eslint"}
    assert stacks[0]["dependencies_truncated"] is False


def test_detects_requirements_txt_and_strips_version_specifiers(tmp_path):
    _write(tmp_path / "requirements.txt", "\n".join([
        "flask[async]>=2.0",
        "requests==2.31.0",
        "# a comment",
        "",
        "-r other.txt",
        "numpy",
    ]))
    stacks = detect_tech_stack(str(tmp_path))
    assert len(stacks) == 1
    assert stacks[0]["dependencies"] == ["flask", "requests", "numpy"]


def test_detects_pyproject_toml_pep621_dependencies(tmp_path):
    _write(tmp_path / "pyproject.toml", '\n'.join([
        "[project]",
        'name = "x"',
        'dependencies = ["flask>=2.0", "requests"]',
    ]))
    stacks = detect_tech_stack(str(tmp_path))
    assert len(stacks) == 1
    assert set(stacks[0]["dependencies"]) == {"flask", "requests"}


def test_detects_pyproject_toml_poetry_dependencies_and_excludes_python_itself(tmp_path):
    _write(tmp_path / "pyproject.toml", '\n'.join([
        "[tool.poetry.dependencies]",
        'python = "^3.11"',
        'flask = "^2.0"',
    ]))
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks[0]["dependencies"] == ["flask"]


def test_detects_cargo_toml(tmp_path):
    _write(tmp_path / "Cargo.toml", '\n'.join([
        "[dependencies]",
        'serde = "1.0"',
    ]))
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks[0]["manifest"] == "Cargo.toml"
    assert stacks[0]["dependencies"] == ["serde"]


def test_detects_go_mod_require_block(tmp_path):
    _write(tmp_path / "go.mod", '\n'.join([
        "module example.com/x",
        "",
        "require (",
        "\tgithub.com/gin-gonic/gin v1.9.0",
        "\tgithub.com/stretchr/testify v1.8.0 // indirect",
        ")",
    ]))
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks[0]["dependencies"] == ["github.com/gin-gonic/gin", "github.com/stretchr/testify"]


def test_detects_go_mod_single_line_require(tmp_path):
    _write(tmp_path / "go.mod", "module example.com/x\n\nrequire github.com/gin-gonic/gin v1.9.0\n")
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks[0]["dependencies"] == ["github.com/gin-gonic/gin"]


def test_detects_gemfile(tmp_path):
    _write(tmp_path / "Gemfile", '\n'.join([
        'source "https://rubygems.org"',
        'gem "rails"',
        "gem 'pg'",
    ]))
    stacks = detect_tech_stack(str(tmp_path))
    assert set(stacks[0]["dependencies"]) == {"rails", "pg"}


def test_detects_composer_json_and_excludes_php_platform_entry(tmp_path):
    _write(tmp_path / "composer.json", json.dumps({
        "require": {"php": ">=8.0", "laravel/framework": "^10.0"},
    }))
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks[0]["dependencies"] == ["laravel/framework"]


def test_detects_pom_xml_with_default_namespace(tmp_path):
    _write(tmp_path / "pom.xml", '\n'.join([
        '<project xmlns="http://maven.apache.org/POM/4.0.0">',
        "  <dependencies>",
        "    <dependency>",
        "      <groupId>org.springframework</groupId>",
        "      <artifactId>spring-core</artifactId>",
        "    </dependency>",
        "  </dependencies>",
        "</project>",
    ]))
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks[0]["manifest"] == "pom.xml"
    assert stacks[0]["dependencies"] == ["spring-core"]


def test_dedupes_dependencies_appearing_in_multiple_sections(tmp_path):
    _write(tmp_path / "package.json", json.dumps({
        "dependencies": {"lodash": "^4.0.0"},
        "devDependencies": {"lodash": "^4.0.0"},
    }))
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks[0]["dependencies"] == ["lodash"]


def test_truncates_past_max_dependencies_and_flags_it(tmp_path):
    deps = {f"pkg{i}": "1.0.0" for i in range(MAX_DEPENDENCIES + 5)}
    _write(tmp_path / "package.json", json.dumps({"dependencies": deps}))
    stacks = detect_tech_stack(str(tmp_path))
    assert len(stacks[0]["dependencies"]) == MAX_DEPENDENCIES
    assert stacks[0]["dependencies_truncated"] is True


def test_detects_multiple_manifests_in_stable_order(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"dependencies": {}}))
    _write(tmp_path / "requirements.txt", "flask\n")
    stacks = detect_tech_stack(str(tmp_path))
    assert [s["manifest"] for s in stacks] == ["package.json", "requirements.txt"]


def test_skips_a_malformed_manifest_without_raising(tmp_path):
    _write(tmp_path / "package.json", "{ not valid json")
    stacks = detect_tech_stack(str(tmp_path))
    assert stacks == [{
        "manifest": "package.json",
        "language": "JavaScript/TypeScript",
        "package_manager": "npm",
        "dependencies": [],
        "dependencies_truncated": False,
    }]


def test_ignores_a_manifest_found_in_a_subdirectory(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    _write(nested / "package.json", json.dumps({"dependencies": {"react": "1.0"}}))
    assert detect_tech_stack(str(tmp_path)) == []
