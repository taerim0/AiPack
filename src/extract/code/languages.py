"""Collects per-language Tree-sitter processing config in one place.

Supporting a new extension means adding one LanguageConfig entry here (plus a
dependency handler if needed) — nothing else. extractor.py / compressor.py only
ever reference this config; they don't hardcode per-language node types themselves.
"""

from dataclasses import dataclass
from typing import Callable

from tree_sitter import Language, Node
import tree_sitter_python as tspython
import tree_sitter_java as tsjava
import tree_sitter_typescript as tstypescript

# When an import-statement node is hit, fills results with the module name and
# returns True (handled, stop recursing into children). Returns False for
# non-import nodes so traversal continues. Import syntax differs too much between
# languages (field presence, node names, etc.) to share one generic routine, so
# each language gets its own small handler instead.
DependencyHandler = Callable[[Node, list], bool]


def _py_dependency_handler(node: Node, results: list) -> bool:
    if node.type == "import_from_statement":
        module = node.child_by_field_name("module_name")
        if module:
            results.append(module.text.decode())
        return True

    if node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                results.append(child.text.decode())
        return True

    return False


def _java_dependency_handler(node: Node, results: list) -> bool:
    if node.type == "import_declaration":
        # no field for this, so strip "import"/"static"/";" from the raw text to
        # leave just the module path.
        text = node.text.decode().strip().rstrip(";").strip()
        text = text.removeprefix("import").strip()
        text = text.removeprefix("static").strip()
        if text:
            results.append(text)
        return True

    return False


def _ts_dependency_handler(node: Node, results: list) -> bool:
    if node.type == "import_statement":
        source = node.child_by_field_name("source")
        if source:
            results.append(source.text.decode().strip("'\""))
        return True

    return False


@dataclass(frozen=True)
class LanguageConfig:
    language: Language
    function_types: list[str]              # node types targeted for signature extraction + body compression
    dependency_handler: DependencyHandler   # strategy for extracting import statements


LANGUAGE_CONFIGS: dict[str, LanguageConfig] = {
    ".py": LanguageConfig(
        language=Language(tspython.language()),
        function_types=["function_definition"],
        dependency_handler=_py_dependency_handler,
    ),
    ".java": LanguageConfig(
        language=Language(tsjava.language()),
        function_types=["method_declaration"],
        dependency_handler=_java_dependency_handler,
    ),
    ".ts": LanguageConfig(
        language=Language(tstypescript.language_typescript()),
        function_types=["function_declaration", "method_definition"],
        dependency_handler=_ts_dependency_handler,
    ),
    ".js": LanguageConfig(
        language=Language(tstypescript.language_tsx()),
        function_types=["function_declaration", "method_definition"],
        dependency_handler=_ts_dependency_handler,
    ),
}


def get_language_config(ext: str) -> LanguageConfig | None:
    return LANGUAGE_CONFIGS.get(ext)
