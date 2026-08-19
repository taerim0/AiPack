from core.parser import get_parser
from pathlib import Path

FUNCTION_NODE_TYPES = {
    ".py":   ["function_definition"],
    ".java": ["method_declaration"],
    ".ts":   ["function_declaration", "method_definition"],
    ".js":   ["function_declaration", "method_definition"],
}

def extract_signatures(file_path: str) -> list[str]:
    code = open(file_path, "r", encoding="utf-8").read()
    parser = get_parser(file_path)
    if not parser:
        return []

    ext = Path(file_path).suffix
    node_types = FUNCTION_NODE_TYPES.get(ext, [])

    tree = parser.parse(bytes(code, "utf8"))
    results = []
    _traverse_signatures(tree.root_node, results, node_types)
    return results


def extract_dependencies(file_path: str) -> list[str]:
    code = open(file_path, "r", encoding="utf-8").read()
    parser = get_parser(file_path)
    if not parser:
        return []

    tree = parser.parse(bytes(code, "utf8"))
    results = []
    _traverse_dependencies(tree.root_node, results)
    return results


def extract_api(file_path: str) -> list[str]:
    code = open(file_path, "r", encoding="utf-8").read()
    parser = get_parser(file_path)
    if not parser:
        return []

    tree = parser.parse(bytes(code, "utf8"))
    results = []
    _traverse_api(tree.root_node, results)
    return results


def _traverse_signatures(node, results: list, node_types: list):
    if node.type in node_types:
        name   = node.child_by_field_name("name")
        params = node.child_by_field_name("parameters")
        ret    = node.child_by_field_name("return_type")

        if name and params:
            sig = f"{name.text.decode()}{params.text.decode()}"
            if ret:
                sig += f" -> {ret.text.decode()}"
            results.append(sig)
        return

    for child in node.children:
        _traverse_signatures(child, results, node_types)


def _traverse_dependencies(node, results: list):
    if node.type == "import_from_statement":
        module = node.child_by_field_name("module_name")
        if module:
            results.append(module.text.decode())
        return

    if node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                results.append(child.text.decode())
        return

    for child in node.children:
        _traverse_dependencies(child, results)


def _traverse_api(node, results: list):
    if node.type == "decorated_definition":
        decorator = None
        for child in node.children:
            if child.type == "decorator":
                decorator = child
                break

        if decorator:
            method = None
            path = None

            for n in _walk(decorator):
                if n.type == "attribute":
                    attr_text = n.text.decode()
                    if ".get"      in attr_text: method = "GET"
                    elif ".post"   in attr_text: method = "POST"
                    elif ".put"    in attr_text: method = "PUT"
                    elif ".delete" in attr_text: method = "DELETE"
                    elif ".patch"  in attr_text: method = "PATCH"
                    break

            for n in _walk(decorator):
                if n.type == "string_content":
                    path = n.text.decode()
                    break

            if method and path:
                results.append(f"{method} {path}")
        return

    for child in node.children:
        _traverse_api(child, results)


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def debug_tree(file_path: str):
    code = open(file_path, "r", encoding="utf-8").read()
    parser = get_parser(file_path)
    tree = parser.parse(bytes(code, "utf8"))
    _print_tree(tree.root_node, 0)


def _print_tree(node, depth: int):
    indent = "  " * depth
    print(f"{indent}{node.type}: {repr(node.text.decode()[:30])}")
    for child in node.children:
        _print_tree(child, depth + 1)