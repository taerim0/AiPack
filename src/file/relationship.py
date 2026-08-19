from pathlib import Path


def build_stem_map(file_names) -> dict:
    """파일 stem(확장자 제외 파일명) → 파일명 매핑.
    import 경로("extract.code.parser")의 마지막 segment와 매칭하는 데 쓴다."""
    return {Path(name).stem: name for name in file_names}


def resolve_dependency(dep: str, stem_map: dict) -> str | None:
    """dependencies 항목을 프로젝트 내부 파일명으로 매칭.

    dep는 두 가지 형태로 들어올 수 있다:
    - Tree-sitter가 뽑은 원본 import 경로 (예: "extract.code.extractor")
    - 사용자가 correct_relationships에서 옮겨 붙인, 이미 확정된 파일명 (예: "extractor.py")

    매치되면 파일명을, 외부 의존성이면 None을 돌려준다.
    """
    if dep in stem_map.values():
        return dep
    return stem_map.get(dep.split(".")[-1])


def build_tree(files: dict) -> dict:
    stem_map = build_stem_map(files.keys())
    tree = {}

    for name, data in files.items():
        deps = data.get("dependencies", [])
        internal, external = [], []
        for dep in deps:
            matched = resolve_dependency(dep, stem_map)
            if matched and matched != name:
                internal.append(matched)
            else:
                external.append(dep)
        tree[name] = {
            "internal": list(dict.fromkeys(internal)),   # 순서 유지 + 중복 제거
            "external": list(dict.fromkeys(external))
        }

    return tree


def print_tree(tree: dict):
    print("\n📦 Project Dependency Tree\n")

    all_children = set()
    for deps in tree.values():
        all_children.update(deps["internal"])

    # 아무도 참조하지 않는 파일부터 시작 (전부 사이클이면 그냥 전체를 root로)
    roots = [name for name in tree if name not in all_children] or list(tree.keys())

    def print_node(name, ancestors, depth=1):
        indent = "  " * depth
        deps = tree.get(name, {"internal": [], "external": []})

        for child in deps["internal"]:
            if child in ancestors:
                print(f"{indent}└── 📄 {child} (순환 참조 → 생략)")
                continue
            print(f"{indent}└── 📄 {child}")
            print_node(child, ancestors | {child}, depth + 1)

        for external in deps["external"]:
            print(f"{indent}└── 📦 {external}")

    for name in roots:
        print(f"├── 📄 {name}")
        print_node(name, {name})
