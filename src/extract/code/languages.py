"""언어별 Tree-sitter 처리 설정을 한 곳에 모아둔다.

새 확장자를 지원하려면 이 파일에 LanguageConfig 항목 하나(+ 필요하면 dependency
핸들러 하나)만 추가하면 된다. extractor.py / compressor.py는 이 config만
참조하고, 언어별 노드 타입을 직접 하드코딩하지 않는다.
"""

from dataclasses import dataclass
from typing import Callable

from tree_sitter import Language, Node
import tree_sitter_python as tspython
import tree_sitter_java as tsjava
import tree_sitter_typescript as tstypescript

# import 구문 노드를 만나면 results에 모듈명을 채우고 True(처리 완료, 자식 순회
# 중단)를 반환한다. import 구문이 아니면 False를 반환해 순회가 계속되게 한다.
# 언어마다 import 문법이 완전히 다르므로(필드 유무, 노드 이름 등) 공용 로직으로
# 묶지 않고 언어별로 작은 함수를 따로 둔다.
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
        # 필드가 없어 텍스트에서 "import"/"static"/";"를 걷어내고 모듈 경로만 남긴다.
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
    function_types: list[str]              # 시그니처 추출 + 본문 압축 대상 노드 타입
    dependency_handler: DependencyHandler   # import 구문 추출 전략


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
