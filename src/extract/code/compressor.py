from extract.code.languages import get_language_config
from extract.code.parser import get_parser_by_ext
from file.textutil import read_text
from pathlib import Path

MARKER = "    ⋮----"

def compress_file(file_path: str) -> str:
    code = read_text(file_path)
    if code is None:
        # 바이너리 등 텍스트로 읽을 수 없는 파일 → 압축 대상 아님
        return ""

    ext = Path(file_path).suffix
    compressed = compress_code(code, ext)
    if compressed is not None:
        return compressed

    # Tree-sitter 미지원 확장자 -> 텍스트 전용 압축기가 있으면 그걸로, 없으면 그대로 반환
    # (여기서 import하는 이유: extract.text.registry -> markdown_compressor가
    # 코드블록 압축에 이 모듈의 compress_code()를 되받아 쓰므로, 모듈 최상단에서
    # 서로 import하면 순환 참조가 생긴다. 함수 안에서 지연 import하면 두 모듈이
    # 이미 다 로드된 뒤에 참조하므로 순환이 끊긴다.)
    from extract.text.registry import get_text_compressor
    text_compressor = get_text_compressor(ext)
    return text_compressor(code) if text_compressor else code


def compress_code(code: str, ext: str) -> str | None:
    """code 텍스트를 확장자에 맞는 Tree-sitter 문법으로 압축해서 돌려준다.

    ext가 지원하는 언어가 아니면 None (호출부가 다른 폴백을 시도할 수 있게).
    compress_file()과, 마크다운 코드블록 압축(markdown_compressor)이 이 로직을
    공유한다 — 파일이든 마크다운 안의 코드블록이든 "이 언어 코드를 어떻게
    압축할지"는 동일해야 하므로.
    """
    parser = get_parser_by_ext(ext)
    if not parser:
        return None

    config = get_language_config(ext)
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

            # JS/TS/Java처럼 여는 '{'가 시그니처와 같은 줄에 있는 언어는, body 시작
            # 줄을 그대로 지우면 시그니처까지 같이 사라진다. body가 함수 노드와
            # 같은 줄에서 시작할 때만 그 다음 줄부터 지운다. Python은 body(들여쓰기
            # 블록)가 애초에 다음 줄부터 시작하므로 이 보정이 적용되지 않는다.
            if start == node.start_point[0]:
                start += 1

            # 마찬가지로 닫는 '}'만 있는 줄은 지우지 않고 남긴다. 중괄호가 없는
            # 언어(Python)는 body의 마지막 자식이 '}'가 아니므로 그대로 둔다.
            last_child = body.children[-1] if body.children else None
            if last_child and last_child.type == "}":
                end = last_child.start_point[0] - 1

            if end >= start:
                ranges.append((start, end))
        return  # body 내부 순회 안 함

    for child in node.children:
        _collect_bodies(child, ranges, function_types)