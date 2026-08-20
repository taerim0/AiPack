from extract.code.languages import get_language_config
from extract.code.parser import get_parser
from file.textutil import read_text
from pathlib import Path

MARKER = "    ⋮----"

def compress_file(file_path: str) -> str:
    code = read_text(file_path)
    if code is None:
        # 바이너리 등 텍스트로 읽을 수 없는 파일 → 압축 대상 아님
        return ""

    parser = get_parser(file_path)

    # 지원 안 하는 언어면 그대로 반환
    if not parser:
        return code

    config = get_language_config(Path(file_path).suffix)
    function_types = config.function_types if config else []

    tree = parser.parse(bytes(code, "utf8"))
    lines = code.splitlines()

    # body 라인 범위 수집
    body_ranges = []
    _collect_bodies(tree.root_node, body_ranges, function_types)

    # 라인 단위로 body 제거
    result = []
    i = 0
    while i < len(lines):
        removed = False
        for start, end in body_ranges:
            if i == start:
                result.append(MARKER)
                i = end + 1
                removed = True
                break
        if not removed:
            result.append(lines[i])
            i += 1

    return "\n".join(result)


def _collect_bodies(node, ranges: list, function_types: list):

    if node.type in function_types:
        body = node.child_by_field_name("body")
        if body:
            start = body.start_point[0]
            end   = body.end_point[0]
            ranges.append((start, end))
        return  # body 내부 순회 안 함

    for child in node.children:
        _collect_bodies(child, ranges, function_types)