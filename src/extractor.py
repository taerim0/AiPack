from parser import get_parser

def extract_signatures(file_path: str) -> list[str]:
    code = open(file_path, "r", encoding="utf-8").read()
    parser = get_parser(file_path)
    if not parser:
        return []

    tree = parser.parse(bytes(code, "utf8"))
    results = []
    _traverse(tree.root_node, results)
    return results


def _traverse(node, results: list):

    # 함수 정의 노드 발견
    if node.type == "function_definition":
        name   = node.child_by_field_name("name")
        params = node.child_by_field_name("parameters")
        ret    = node.child_by_field_name("return_type")

        if name and params:
            sig = f"{name.text.decode()}{params.text.decode()}"
            if ret:
                sig += f" -> {ret.text.decode()}"
            results.append(sig)

        return  # body 내부 순회 안 함

    # 나머지 노드는 계속 순회
    for child in node.children:
        _traverse(child, results)