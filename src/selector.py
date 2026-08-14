from pathlib import Path


def display_files(files: list[str], root_path: str) -> None:
    print(f"\n📁 수집된 파일 ({len(files)}개)\n")
    for i, file_path in enumerate(files, 1):
        relative = Path(file_path).relative_to(root_path)
        print(f"  [{i}] {relative}")


def select_files(files: list[str], root_path: str) -> list[str]:
    display_files(files, root_path)

    print("\n선택 (쉼표로 구분 / 전체=a / 취소=q): ", end="")
    user_input = input().strip()

    # 취소
    if user_input.lower() == "q":
        print("취소됨.")
        return []

    # 전체 선택
    if user_input.lower() == "a":
        print(f"\n✅ 전체 {len(files)}개 선택됨")
        return files

    # 번호 선택
    try:
        indices = [int(x.strip()) for x in user_input.split(",")]
        selected = []
        for idx in indices:
            if 1 <= idx <= len(files):
                selected.append(files[idx - 1])
            else:
                print(f"  ⚠️  [{idx}] 범위 초과 → 무시")

        print(f"\n✅ {len(selected)}개 선택됨")
        for f in selected:
            relative = Path(f).relative_to(root_path)
            print(f"  {relative}")

        return selected

    except ValueError:
        print("잘못된 입력입니다.")
        return []