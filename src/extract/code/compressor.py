from core.parser import get_parser

MARKER = "    ⋮----"

def compress_file(file_path: str) -> str:
    code = open(file_path, "r", encoding="utf-8").read()
    parser = get_parser(file_path)

    # 지원 안 하는 언어면 그대로 반환
    if not parser:
        return code

    tree = parser.parse(bytes(code, "utf8"))
    lines = code.splitlines()

    # body 라인 범위 수집
    body_ranges = []
    _collect_bodies(tree.root_node, body_ranges)

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


def _collect_bodies(node, ranges: list):

    if node.type == "function_definition":
        body = node.child_by_field_name("body")
        if body:
            start = body.start_point[0]
            end   = body.end_point[0]
            ranges.append((start, end))
        return  # body 내부 순회 안 함

    for child in node.children:
        _collect_bodies(child, ranges)