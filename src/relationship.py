from pathlib import Path


def build_tree(files_data: dict) -> dict:
    """
    files_data:
    {
        "test.py": {"dependencies": ["userservice", "authservice"]},
        "CONFIG_NOTES.txt": {"dependencies": []},
    }
    """
    # 파일명 목록
    file_names = {Path(fp).name for fp in files_data}

    tree = {}

    for file_path, data in files_data.items():
        name = Path(file_path).name
        deps = data.get("dependencies", [])

        # 프로젝트 내부 파일만 연결
        # 외부 라이브러리(userservice 등)는 별도 표시
        internal = [d for d in deps if d in file_names]
        external = [d for d in deps if d not in file_names]

        tree[name] = {
            "internal": internal,  # 프로젝트 내 파일
            "external": external   # 외부 의존성
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