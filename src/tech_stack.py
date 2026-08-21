"""Free (no LLM call), manifest-file-based tech-stack detection -- a
deterministic sibling to `llm.analyze_rules()`, not a replacement for it.
Scans a project's root directory (top-level only; monorepo submodules each
with their own manifest aren't chased) for known package-manager manifest
files and reads out language/ecosystem + a capped list of declared
top-level dependency names.

`rules` already gestures at a project's tech stack indirectly, by having an
LLM infer coding conventions from Tree-sitter signatures -- but that's a
guess from code *shape*, not a read of the actual manifest a package manager
would resolve. This is cheaper (no LLM call at all) and strictly more
accurate for the one narrow fact it covers: what's declared as a dependency,
not what conventions look like in practice.

Deliberately shallow: no lockfile resolution (package-lock.json/poetry.lock/
Cargo.lock/go.sum), no transitive dependency walking, no version-constraint
parsing beyond stripping it off the declared name. This is "what does this
project say it depends on," not a full dependency graph -- a lockfile-
accurate one would need per-ecosystem tooling this project has no reason to
vendor.
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# Caps dependency list length per manifest so a project with hundreds of npm
# packages doesn't blow up aif.json's project section for a field that's
# meant to be a quick fact block, not a full lockfile dump.
MAX_DEPENDENCIES = 40


def _parse_package_json(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    return list(data.get("dependencies", {}) or {}) + list(data.get("devDependencies", {}) or {})


def _parse_requirements_txt(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    names = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-r", "-e", "--", "-c")):
            continue
        # strip version specifiers/extras/env markers: "flask[async]>=2.0; python_version>='3.8'" -> "flask"
        name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip()
        if name:
            names.append(name)
    return names


def _parse_pyproject_toml(path: Path) -> list[str]:
    try:
        import tomllib
    except ImportError:
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []

    names = []
    # PEP 621: [project.dependencies], a list of PEP 508 requirement strings.
    for dep in data.get("project", {}).get("dependencies", []) or []:
        name = re.split(r"[<>=!~\[; ]", dep, maxsplit=1)[0].strip()
        if name:
            names.append(name)
    # Poetry: [tool.poetry.dependencies], a table keyed by name (including a
    # "python" entry for the interpreter constraint itself -- not a real
    # dependency, excluded).
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}
    names.extend(name for name in poetry_deps if name.lower() != "python")
    return names


def _parse_cargo_toml(path: Path) -> list[str]:
    try:
        import tomllib
    except ImportError:
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return list(data.get("dependencies", {}) or {})


def _parse_go_mod(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    names = []
    in_require_block = False
    for raw_line in content.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if line.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block:
            if line == ")":
                in_require_block = False
            elif line:
                names.append(line.split()[0])
        elif line.startswith("require "):
            parts = line[len("require "):].split()
            if parts:
                names.append(parts[0])
    return names


def _parse_gemfile(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return re.findall(r'^\s*gem\s+["\']([^"\']+)["\']', content, re.MULTILINE)


def _parse_composer_json(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    names = list(data.get("require", {}) or {}) + list(data.get("require-dev", {}) or {})
    # "php" itself is a platform-version constraint, not a real dependency.
    return [n for n in names if n != "php"]


def _parse_pom_xml(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    # Strip the default Maven namespace declaration so plain tag lookups
    # ("dependencies/dependency"/"artifactId") work without namespace-
    # prefixed XPath, which ElementTree's limited XPath subset can't express
    # for a default (unprefixed) namespace anyway.
    content = re.sub(r'\sxmlns="[^"]*"', "", content, count=1)
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    names = []
    for dep in root.findall(".//dependencies/dependency"):
        artifact = dep.find("artifactId")
        if artifact is not None and artifact.text:
            names.append(artifact.text.strip())
    return names


# (manifest filename, language/ecosystem label, package-manager label, parser)
_MANIFESTS = [
    ("package.json",     "JavaScript/TypeScript", "npm",         _parse_package_json),
    ("requirements.txt", "Python",                 "pip",         _parse_requirements_txt),
    ("pyproject.toml",   "Python",                 "poetry/pip",  _parse_pyproject_toml),
    ("Cargo.toml",       "Rust",                    "cargo",       _parse_cargo_toml),
    ("go.mod",           "Go",                      "go modules",  _parse_go_mod),
    ("Gemfile",          "Ruby",                     "bundler",     _parse_gemfile),
    ("composer.json",    "PHP",                       "composer",    _parse_composer_json),
    ("pom.xml",          "Java",                       "maven",       _parse_pom_xml),
]


def detect_tech_stack(root_path: str) -> list[dict]:
    """Scans root_path's top level for known package-manager manifest files.
    Returns one entry per manifest actually found, in _MANIFESTS' fixed
    order -- so output is stable across runs/platforms, not directory-
    listing order (which isn't guaranteed).

    Never raises -- a manifest that exists but fails to parse (malformed
    JSON/TOML/XML) is silently skipped, not fatal to the rest of pack();
    this is a convenience fact block, not something pack() should abort
    over just because one manifest is broken.
    """
    root = Path(root_path)
    stacks = []
    for filename, language, package_manager, parser in _MANIFESTS:
        manifest_path = root / filename
        if not manifest_path.is_file():
            continue

        # de-dupe while preserving order (a manifest can list the same name
        # twice, e.g. across dependencies/devDependencies)
        seen = set()
        deps = []
        for dep in parser(manifest_path):
            if dep not in seen:
                seen.add(dep)
                deps.append(dep)

        stacks.append({
            "manifest": filename,
            "language": language,
            "package_manager": package_manager,
            "dependencies": deps[:MAX_DEPENDENCIES],
            "dependencies_truncated": len(deps) > MAX_DEPENDENCIES,
        })
    return stacks
