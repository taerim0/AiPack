import argparse
import json
from pathlib import Path

from extractor import extract_signatures, extract_dependencies, extract_api, debug_tree
from compressor import compress_file
from collector import collect_files, print_tree
from scanner import scan_files
from tokenizer import analyze_tokens, analyze_tokens_with_compression
from selector import select_files
from llm import analyze_file_summary, analyze_rules, analyze_prompt
from packager import pack, save_aif
from corrector import correct_aif


def main():
    parser = argparse.ArgumentParser(description="AiPack v2")
    sub = parser.add_subparsers(dest="command")

    c = sub.add_parser("compress", help="코드 압축")
    c.add_argument("file", help="파일 경로")

    s = sub.add_parser("signatures", help="시그니처 추출")
    s.add_argument("file", help="파일 경로")

    d = sub.add_parser("dependencies", help="의존성 추출")
    d.add_argument("file", help="파일 경로")

    a = sub.add_parser("api", help="API 추출")
    a.add_argument("file", help="파일 경로")

    db = sub.add_parser("debug", help="트리 구조 출력")
    db.add_argument("file", help="파일 경로")

    col = sub.add_parser("collect", help="파일 수집")
    col.add_argument("path", help="프로젝트 폴더 경로")

    tok = sub.add_parser("tokens", help="토큰 카운팅")
    tok.add_argument("path", help="프로젝트 폴더 경로")

    sel = sub.add_parser("select", help="파일 선택")
    sel.add_argument("path", help="프로젝트 폴더 경로")

    an = sub.add_parser("analyze", help="LLM 분석")
    an.add_argument("path", help="프로젝트 폴더 경로")

    p = sub.add_parser("pack", help="프로젝트 패킹")
    p.add_argument("path", help="프로젝트 폴더 경로")
    p.add_argument("--output", "-o", default="aif.json", help="출력 파일 경로")
    p.add_argument("--auto", action="store_true", help="파일 자동 선택")


    args = parser.parse_args()

    if args.command == "compress":
        print(compress_file(args.file))

    elif args.command == "signatures":
        sigs = extract_signatures(args.file)
        for sig in sigs:
            print(f"  {sig}")

    elif args.command == "dependencies":
        deps = extract_dependencies(args.file)
        for dep in deps:
            print(f"  {dep}")

    elif args.command == "api":
        apis = extract_api(args.file)
        for api in apis:
            print(f"  {api}")

    elif args.command == "debug":
        debug_tree(args.file)

    elif args.command == "collect":
        files = collect_files(args.path)
        scan_result = scan_files(files)

        print(f"\n📁 수집된 파일: {len(files)}개")
        print_tree(files, args.path)

        if scan_result["dangerous"]:
            print(f"\n⚠️  민감 파일 감지: {len(scan_result['dangerous'])}개")
            for f in scan_result["dangerous"]:
                print(f"  ❌ {f}")

        print(f"\n✅ 안전한 파일: {len(scan_result['safe'])}개")

    elif args.command == "tokens":
        files = collect_files(args.path)
        scan_result = scan_files(files)
        safe_files = scan_result["safe"]

        results, _ = analyze_tokens_with_compression(safe_files)
        print(f"\n📊 토큰 분석 ({len(safe_files)}개 파일)\n")
        for model, data in results.items():
            print(f"{model}")
            print(f"  압축 전: {data['original']:,} / {data['max']:,} {data['original_bar']}")
            print(f"  압축 후: {data['compressed']:,} / {data['max']:,} {data['compressed_bar']}")
            print(f"  절감:    {data['saved']:,} 토큰 ({data['saved_pct']}% 감소)\n")

    elif args.command == "select":
        files = collect_files(args.path)
        scan_result = scan_files(files)
        safe_files = scan_result["safe"]

        if scan_result["dangerous"]:
            print(f"\n⚠️  민감 파일 제외됨: {len(scan_result['dangerous'])}개")
            for f in scan_result["dangerous"]:
                print(f"  ❌ {f}")

        selected = select_files(safe_files, args.path)

    elif args.command == "analyze":
        # 1. 파일 수집
        files = collect_files(args.path)
        scan_result = scan_files(files)
        safe_files = scan_result["safe"]

        print(f"\n📁 분석 대상: {len(safe_files)}개 파일\n")

        # 2. 파일별 분석
        signatures_map = {}
        summaries = {}

        for file in safe_files:
            sigs = extract_signatures(file)
            deps = extract_dependencies(file)

            if not sigs and not deps:
                continue

            print(f"  🔍 {Path(file).name} 분석 중...")
            summary = analyze_file_summary(file, sigs, deps)
            try:
                summary_data = json.loads(summary)
                summaries[file] = summary_data.get("summary", "분석 실패")
            except json.JSONDecodeError:
                summaries[file] = "분석 실패"

            signatures_map[file] = sigs

        # 3. 룰 추출
        print(f"\n  📋 코딩 룰 추출 중...")
        rules_response = analyze_rules(signatures_map)
        try:
            rules_data = json.loads(rules_response)
        except json.JSONDecodeError:
            rules_data = {"rules": []}

        # 4. 프롬프트 생성
        print(f"  ✍️  AI 가이드 생성 중...\n")
        prompt_response = analyze_prompt(
            project_name=Path(args.path).name,
            architecture=[],
            rules=rules_data["rules"]
        )
        try:
            prompt_data = json.loads(prompt_response)
        except json.JSONDecodeError:
            prompt_data = {"prompt": "생성 실패"}

        # 5. 결과 출력
        print("=" * 50)
        print("📄 파일별 Summary")
        print("=" * 50)
        for file, summary in summaries.items():
            print(f"  {Path(file).name}: {summary}")

        print("\n" + "=" * 50)
        print("📋 코딩 룰")
        print("=" * 50)
        for rule in rules_data["rules"]:
            print(f"  - {rule}")

        print("\n" + "=" * 50)
        print("✍️  AI 가이드")
        print("=" * 50)
        print(f"  {prompt_data['prompt']}")

    elif args.command == "pack":
        aif = pack(args.path, auto=args.auto)
        if aif:
            # 사용자 보정
            aif = correct_aif(aif)

            # 저장
            save_aif(aif, args.output)

            print("\n" + "=" * 50)
            print("📄 파일별 Summary")
            print("=" * 50)
            for name, data in aif["files"].items():
                if data["summary"]:
                    print(f"  {name}: {data['summary']}")

            print("\n" + "=" * 50)
            print("📋 코딩 룰")
            print("=" * 50)
            for rule in aif["rules"]:
                print(f"  - {rule}")

            print("\n" + "=" * 50)
            print("✍️  AI 가이드")
            print("=" * 50)
            print(f"  {aif['project']['prompt']}")

            print("\n" + "=" * 50)
            print("📊 토큰 분석")
            print("=" * 50)
            for model, data in aif["tokens"].items():
                print(f"  {model}: {data['original']} → {data['compressed']} ({data['saved_pct']}% 절감)")

if __name__ == "__main__":
    main()