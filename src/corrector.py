import json
from pathlib import Path


def correct_aif(aif: dict) -> dict:
    print("\n" + "=" * 50)
    print("✏️  사용자 보정 (엔터 = 유지, 내용 입력 = 수정)")
    print("=" * 50)

    # 1. 프로젝트 이름 수정
    current_name = aif["project"]["name"]
    print(f"\n📌 프로젝트 이름: {current_name}")
    new_name = input("  수정 (엔터=유지): ").strip()
    if new_name:
        aif["project"]["name"] = new_name

    # 2. AI 가이드 수정
    current_prompt = aif["project"]["prompt"]
    print(f"\n✍️  AI 가이드:\n  {current_prompt}")
    new_prompt = input("  수정 (엔터=유지): ").strip()
    if new_prompt:
        aif["project"]["prompt"] = new_prompt

    # 3. 코딩 룰 수정
    print(f"\n📋 코딩 룰:")
    for i, rule in enumerate(aif["rules"], 1):
        print(f"  [{i}] {rule}")

    print("\n  룰 추가 (a), 삭제 (d번호), 유지 (엔터): ", end="")
    rule_input = input().strip()

    if rule_input.lower() == "a":
        new_rule = input("  추가할 룰 입력: ").strip()
        if new_rule:
            aif["rules"].append(new_rule)
            print(f"  ✅ 추가됨: {new_rule}")

    elif rule_input.lower().startswith("d"):
        try:
            idx = int(rule_input[1:]) - 1
            if 0 <= idx < len(aif["rules"]):
                removed = aif["rules"].pop(idx)
                print(f"  ✅ 삭제됨: {removed}")
        except (ValueError, IndexError):
            print("  ⚠️  잘못된 입력")

    # 4. 파일별 summary 수정
    print(f"\n📄 파일별 Summary:")
    for file_name, data in aif["files"].items():
        print(f"\n  {file_name}: {data['summary']}")
        new_summary = input("  수정 (엔터=유지): ").strip()
        if new_summary:
            aif["files"][file_name]["summary"] = new_summary

    print("\n✅ 보정 완료")
    return aif