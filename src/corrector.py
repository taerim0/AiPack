"""Interactive terminal flow for reviewing/editing an `aif` dict before it ships.

This module owns all the input()/print() calls; every actual edit is
delegated to a pure function in edits.py or file/relationship.py. That split
means the same edits are reachable from something other than a terminal (a
future MCP server or GUI backend) without touching this file -- see edits.py
and file/relationship.py's move_file()/build_tree() for the reusable part.
`pack --auto-correct` skips this module entirely and calls
edits.finalize_aif() directly instead.
"""

from edits import (
    set_project_name,
    set_project_prompt,
    add_rule,
    remove_rule,
    set_file_summary,
    finalize_aif,
)
from file.relationship import build_stem_map, resolve_dependency, move_file, CycleError


def correct_relationships(aif: dict) -> dict:
    print(f"\n🔗 파일 간 관계 수정")
    print("(완료=q, 엔터=유지)\n")

    files = list(aif["files"].keys())
    stem_map = build_stem_map(files)

    def resolve(dep: str) -> str | None:
        return resolve_dependency(dep, stem_map)

    def print_current_tree():
        all_children = set()
        for name in files:
            deps = aif["files"][name].get("dependencies", [])
            for dep in deps:
                matched = resolve(dep)
                if matched:
                    all_children.add(matched)

        def print_node(name, ancestors, depth=1):
            indent = "  " * depth
            deps = aif["files"].get(name, {}).get("dependencies", [])
            for dep in deps:
                matched = resolve(dep)
                if matched:
                    if matched in ancestors:
                        print(f"{indent}   └── 📄 {matched} (순환 참조 → 생략)")
                        continue
                    print(f"{indent}   └── 📄 {matched}")
                    print_node(matched, ancestors | {matched}, depth + 1)
                else:
                    print(f"{indent}   └── 📦 {dep}")

        for i, name in enumerate(files, 1):
            if name in all_children:
                continue
            print(f"  [{i}] {name}")
            print_node(name, {name})

    # loop so the user can make multiple moves
    while True:
        print_current_tree()
        print("\n  이동할 파일 번호 (완료=q): ", end="")
        move_input = input().strip()

        if move_input.lower() == "q" or not move_input:
            break

        try:
            move_idx = int(move_input) - 1
            if move_idx < 0 or move_idx >= len(files):
                print("  ⚠️  범위 초과")
                continue

            move_file_name = files[move_idx]

            print(f"  [{move_file_name}] 을 어느 파일의 자식으로?")
            print("  부모 파일 번호 (취소=q): ", end="")
            parent_input = input().strip()

            if parent_input.lower() == "q" or not parent_input:
                continue

            parent_idx = int(parent_input) - 1
            if parent_idx < 0 or parent_idx >= len(files):
                print("  ⚠️  범위 초과")
                continue

            parent_file = files[parent_idx]

            if move_file_name == parent_file:
                print("  ⚠️  같은 파일 선택 불가")
                continue

            try:
                move_file(aif["files"], move_file_name, parent_file)
            except CycleError:
                print(f"  ⚠️  순환 참조 발생 → 이동 불가")
                continue

            print(f"  ✅ {move_file_name} → {parent_file} 자식으로 이동\n")

        except (ValueError, IndexError):
            print("  ⚠️  잘못된 입력")

    return aif


def correct_aif(aif: dict) -> dict:
    print("\n" + "=" * 50)
    print("✏️  사용자 보정 (엔터 = 유지, 내용 입력 = 수정)")
    print("=" * 50)

    # 1. Correct project name
    print(f"\n📌 프로젝트 이름: {aif['project']['name']}")
    new_name = input("  수정 (엔터=유지): ").strip()
    if new_name:
        set_project_name(aif, new_name)

    # 2. Correct AI guide
    print(f"\n✍️  AI 가이드:\n  {aif['project']['prompt']}")
    new_prompt = input("  수정 (엔터=유지): ").strip()
    if new_prompt:
        set_project_prompt(aif, new_prompt)

    # 3. Correct coding rules
    print(f"\n📋 코딩 룰:")
    for i, rule in enumerate(aif["rules"], 1):
        print(f"  [{i}] {rule}")

    print("\n  룰 추가 (a), 삭제 (d번호), 유지 (엔터): ", end="")
    rule_input = input().strip()

    if rule_input.lower() == "a":
        new_rule = input("  추가할 룰 입력: ").strip()
        if new_rule:
            add_rule(aif, new_rule)
            print(f"  ✅ 추가됨: {new_rule}")

    elif rule_input.lower().startswith("d"):
        try:
            idx = int(rule_input[1:]) - 1
            if 0 <= idx < len(aif["rules"]):
                removed = aif["rules"][idx]
                remove_rule(aif, idx)
                print(f"  ✅ 삭제됨: {removed}")
        except (ValueError, IndexError):
            print("  ⚠️  잘못된 입력")

    # 4. Correct per-file summaries
    print(f"\n📄 파일별 Summary:")
    for file_name, data in aif["files"].items():
        print(f"\n  {file_name}: {data['summary']}")
        new_summary = input("  수정 (엔터=유지): ").strip()
        if new_summary:
            set_file_summary(aif, file_name, new_summary)

    aif = correct_relationships(aif)
    aif = finalize_aif(aif)

    print("\n✅ 보정 완료")
    return aif
