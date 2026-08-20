from pathlib import Path


def build_stem_map(file_names) -> dict:
    """Maps file stem (file name without extension) -> file name.
    Used to match against the last segment of an import path (e.g. "extract.code.parser")."""
    return {Path(name).stem: name for name in file_names}


def resolve_dependency(dep: str, stem_map: dict) -> str | None:
    """Matches a dependencies entry against an internal project file name.

    dep can come in two shapes:
    - a raw import path extracted by Tree-sitter (e.g. "extract.code.extractor")
    - an already-pinned file name from a prior move in correct_relationships
      (e.g. "extractor.py")

    Returns the file name on a match, or None for an external dependency.
    """
    if dep in stem_map.values():
        return dep
    return stem_map.get(dep.split(".")[-1])


class CycleError(Exception):
    """Raised by move_file() when reparenting a file would create a dependency cycle."""

    def __init__(self, from_file: str, to_file: str):
        self.from_file = from_file
        self.to_file = to_file
        super().__init__(f"moving {from_file!r} under {to_file!r} would create a cycle")


def has_cycle(files: dict, stem_map: dict, from_file: str, to_file: str) -> bool:
    """Checks whether from_file already (transitively) depends on to_file.

    move_file() is about to add the edge "to_file depends on from_file" (a
    dependency entry is a "child" in the tree: see build_tree()/print_tree()).
    That edge closes a cycle exactly when from_file can already reach to_file
    by walking its own existing dependency chain (from_file -> ... -> to_file)
    -- the new edge would then complete the loop to_file -> from_file -> ...
    -> to_file. So this walks from from_file, not to_file.
    """
    visited = set()
    queue = [from_file]
    while queue:
        current = queue.pop()
        if current == to_file:
            return True
        if current in visited:
            continue
        visited.add(current)
        for dep in files.get(current, {}).get("dependencies", []):
            matched = resolve_dependency(dep, stem_map)
            if matched:
                queue.append(matched)
    return False


def move_file(files: dict, file_name: str, new_parent: str) -> dict:
    """Reparents file_name under new_parent, removing it from wherever it
    currently sits in the dependency tree first -- regardless of whether its
    old entry there was a raw import path or an already-pinned file name from
    an earlier move.

    Raises ValueError if file_name/new_parent aren't both in `files` (or are
    the same file), and CycleError if the move would create a cycle. Mutates
    and returns `files`.
    """
    if file_name not in files:
        raise ValueError(f"unknown file: {file_name}")
    if new_parent not in files:
        raise ValueError(f"unknown file: {new_parent}")
    if file_name == new_parent:
        raise ValueError("a file can't be its own parent")

    stem_map = build_stem_map(files.keys())
    if has_cycle(files, stem_map, file_name, new_parent):
        raise CycleError(file_name, new_parent)

    # remove file_name from wherever it's currently listed as a dependency
    for data in files.values():
        deps = data.get("dependencies", [])
        data["dependencies"] = [d for d in deps if resolve_dependency(d, stem_map) != file_name]

    files.setdefault(new_parent, {}).setdefault("dependencies", [])
    files[new_parent]["dependencies"].append(file_name)

    return files


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
            "internal": list(dict.fromkeys(internal)),   # keep order, drop duplicates
            "external": list(dict.fromkeys(external))
        }

    return tree


def print_tree(tree: dict):
    print("\n📦 Project Dependency Tree\n")

    all_children = set()
    for deps in tree.values():
        all_children.update(deps["internal"])

    # start from files nobody references (if it's all one cycle, treat everything as root)
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
