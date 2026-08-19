import json
import time
from pathlib import Path

from file.collector import collect_files
from file.scanner import scan_files
from file.selector import select_files
from extract.code.extractor import extract_signatures, extract_dependencies, extract_api
from extract.code.compressor import compress_file
from tokenizer import analyze_tokens_with_compression
from llm import analyze_file_summary, analyze_text_summary, analyze_rules, analyze_prompt

CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoint"


def save_checkpoint(root_path: str, data: dict) -> None:
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    name = Path(root_path).name
    path = CHECKPOINT_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 체크포인트 저장됨: {path}")


def load_checkpoint(root_path: str) -> dict | None:
    name = Path(root_path).name
    path = CHECKPOINT_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_checkpoint(root_path: str) -> None:
    name = Path(root_path).name
    path = CHECKPOINT_DIR / f"{name}.json"
    if path.exists():
        path.unlink()


def handle_llm_failure(name: str, field: str, current_aif: dict, root_path: str) -> str | None:
    print(f"\n  ⚠️  {name} {field} 생성 실패")
    print("  [1] 재시도")
    print("  [2] 직접 입력")
    print("  [3] 저장 후 종료")
    choice = input("  선택: ").strip()

    if choice == "1":
        return None
    elif choice == "2":
        return input(f"  {field} 직접 입력: ").strip()
    elif choice == "3":
        save_checkpoint(root_path, current_aif)
        return "EXIT"

    return None


def _current_aif_snapshot(root_name: str, files_data: dict, rules: list = None, prompt: str = "") -> dict:
    return {
        "project": {"name": root_name, "prompt": prompt},
        "rules": rules or [],
        "files_data": {
            Path(fp).name: d
            for fp, d in files_data.items()
        }
    }


def pack(root_path: str, auto: bool = False) -> dict:
    root = Path(root_path)

    # 체크포인트 자동 감지
    checkpoint = load_checkpoint(root_path)
    if checkpoint:
        print(f"\n  📂 체크포인트 발견")
        print("  [1] 이어서 진행")
        print("  [2] 처음부터 시작")
        choice = input("  선택: ").strip()
        if choice == "2":
            checkpoint = None
            delete_checkpoint(root_path)

    # 체크포인트에서 복원
    restored_rules = checkpoint.get("rules", []) if checkpoint else []
    restored_prompt = checkpoint.get("project", {}).get("prompt", "") if checkpoint else ""

    # 1. 파일 수집
    print("\n📁 파일 수집 중...")
    files = collect_files(root_path)

    # 2. 보안 스캔
    print("🔒 보안 스캔 중...")
    scan_result = scan_files(files)
    safe_files = scan_result["safe"]

    if scan_result["dangerous"]:
        print(f"  ⚠️  민감 파일 제외: {len(scan_result['dangerous'])}개")
        for f in scan_result["dangerous"]:
            print(f"  ❌ {Path(f).name}")

    # 3. 파일 선택
    if auto:
        selected = safe_files
        print(f"  ✅ 전체 {len(selected)}개 파일 선택됨")
    else:
        selected = select_files(safe_files, root_path)

    if not selected:
        print("선택된 파일 없음.")
        return {}

    # 4. Tree-sitter 분석
    print("\n🔍 코드 구조 분석 중...")
    files_data = {}
    signatures_map = {}

    for file_path in selected:
        name = Path(file_path).name

        # 체크포인트에서 복원
        if checkpoint and name in checkpoint.get("files_data", {}):
            print(f"  ✅ {name} (체크포인트에서 복원)")
            files_data[file_path] = checkpoint["files_data"][name]
            if files_data[file_path].get("signatures"):
                signatures_map[file_path] = files_data[file_path]["signatures"]
            continue

        sigs = extract_signatures(file_path)
        deps = extract_dependencies(file_path)
        apis = extract_api(file_path)
        compressed = compress_file(file_path)

        files_data[file_path] = {
            "signatures": sigs,
            "dependencies": deps,
            "api": apis,
            "compressed": compressed,
            "summary": ""
        }

        if sigs or deps:
            signatures_map[file_path] = sigs

        print(f"  ✅ {name}")

    # 5. LLM 분석
    print("\n🤖 LLM 분석 중...")
    for file_path, data in files_data.items():
        name = Path(file_path).name

        if data.get("summary"):
            continue

        summary = ""
        while not summary:
            print(f"  📄 {name} summary 생성 중...")

            if data["signatures"] or data["dependencies"]:
                summary_response = analyze_file_summary(
                    file_path,
                    data["signatures"],
                    data["dependencies"]
                )
            else:
                try:
                    content = open(file_path, "r", encoding="utf-8").read()
                except:
                    content = ""
                summary_response = analyze_text_summary(file_path, content)

            try:
                summary_data = json.loads(summary_response)
                summary = summary_data.get("summary", "")
            except json.JSONDecodeError:
                summary = ""

            if not summary:
                result = handle_llm_failure(
                    name, "summary",
                    _current_aif_snapshot(root.name, files_data),
                    root_path
                )
                if result == "EXIT":
                    return {}
                elif result is None:
                    continue
                else:
                    summary = result

        files_data[file_path]["summary"] = summary

    # 룰 추출 (체크포인트에서 복원)
    rules = restored_rules
    if not rules:
        print("  📋 코딩 룰 추출 중...")
        while not rules:
            rules_response = analyze_rules(signatures_map)
            try:
                rules_data = json.loads(rules_response)
                rules = rules_data.get("rules", [])
            except json.JSONDecodeError:
                rules = []

            if not rules:
                result = handle_llm_failure(
                    "rules", "코딩 룰",
                    _current_aif_snapshot(root.name, files_data),
                    root_path
                )
                if result == "EXIT":
                    return {}
                elif result is None:
                    continue
                else:
                    rules = [r.strip() for r in result.split(",")]
    else:
        print("  📋 코딩 룰 (체크포인트에서 복원)")

    # 프롬프트 생성 (체크포인트에서 복원)
    prompt = restored_prompt
    if not prompt:
        print("  ✍️  AI 가이드 생성 중...")
        while not prompt:
            prompt_response = analyze_prompt(
                project_name=root.name,
                architecture=[],
                rules=rules
            )
            try:
                prompt_data = json.loads(prompt_response)
                prompt = prompt_data.get("prompt", "")
            except json.JSONDecodeError:
                prompt = ""

            if not prompt:
                result = handle_llm_failure(
                    "prompt", "AI 가이드",
                    _current_aif_snapshot(root.name, files_data, rules),
                    root_path
                )
                if result == "EXIT":
                    return {}
                elif result is None:
                    continue
                else:
                    prompt = result
    else:
        print("  ✍️  AI 가이드 (체크포인트에서 복원)")

    # 6. 토큰 카운팅
    print("\n📊 토큰 분석 중...")
    token_results, _ = analyze_tokens_with_compression(selected)

    # 7. AIF.json 조립
    aif = {
        "project": {
            "name": root.name,
            "prompt": prompt
        },
        "rules": rules,
        "tokens": {
            model: {
                "original": data["original"],
                "compressed": data["compressed"],
                "saved_pct": data["saved_pct"]
            }
            for model, data in token_results.items()
        },
        "files": {
            Path(fp).name: {
                "summary": data["summary"],
                "signatures": data["signatures"],
                "dependencies": data["dependencies"],
                "api": data["api"],
                "compressed": data["compressed"]
            }
            for fp, data in files_data.items()
        }
    }

    # 완료 시 체크포인트 삭제
    delete_checkpoint(root_path)

    return aif


def save_aif(aif: dict, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(aif, f, ensure_ascii=False, indent=2)
    print(f"\n✅ AIF.json 저장됨: {output_path}")