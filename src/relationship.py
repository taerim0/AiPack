from pathlib import Path


def build_tree(files: dict) -> dict:
    file_names = set(files.keys())
    tree = {}

    for name, data in files.items():
        deps = data.get("dependencies", [])
        internal = [d for d in deps if d in file_names]
        external = [d for d in deps if d not in file_names]
        tree[name] = {
            "internal": internal,
            "external": external
        }

    return tree


def print_tree(tree: dict):
    print("\n📦 Project Dependency Tree\n")

    for file_name, deps in tree.items():
        print(f"├── 📄 {file_name}")

        for internal in deps["internal"]:
            print(f"│   ├── 📄 {internal}")

        for external in deps["external"]:
            print(f"│   └── 📦 {external}")