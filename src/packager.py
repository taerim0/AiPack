import json
import time
from pathlib import Path

from collector import collect_files
from scanner import scan_files
from selector import select_files
from extractor import extract_signatures, extract_dependencies, extract_api
from compressor import compress_file
from tokenizer import analyze_tokens_with_compression
from llm import analyze_file_summary, analyze_rules, analyze_prompt


def pack(root_path: str, auto: bool = False) -> dict:
    root = Path(root_path)

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
        if not data["signatures"] and not data["dependencies"]:
            continue

        print(f"  📄 {name} summary 생성 중...")
        summary_response = analyze_file_summary(
            file_path,
            data["signatures"],
            data["dependencies"]
        )
        try:
            summary_data = json.loads(summary_response)
            files_data[file_path]["summary"] = summary_data.get("summary", "")
        except json.JSONDecodeError:
            files_data[file_path]["summary"] = ""

        time.sleep(3)  # 무료 티어 한도 방지

    # 룰 추출
    print("  📋 코딩 룰 추출 중...")
    rules_response = analyze_rules(signatures_map)
    try:
        rules_data = json.loads(rules_response)
        rules = rules_data.get("rules", [])
    except json.JSONDecodeError:
        rules = []

    time.sleep(3)

    # 프롬프트 생성
    print("  ✍️  AI 가이드 생성 중...")
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

    return aif


def save_aif(aif: dict, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(aif, f, ensure_ascii=False, indent=2)
    print(f"\n✅ AIF.json 저장됨: {output_path}")