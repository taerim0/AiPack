import argparse
import json
from pathlib import Path

from extract.code.extractor import extract_signatures, extract_dependencies, extract_api, debug_tree
from extract.code.compressor import compress_file
from file.collector import collect_files, print_tree as print_file_tree
from file.scanner import scan_files
from tokenizer import analyze_tokens, analyze_tokens_with_compression
from file.selector import select_files
from llm import analyze_file_summary, analyze_rules, analyze_prompt
from packager import pack, save_aif
from corrector import correct_aif
from edits import finalize_aif
from file.relationship import build_tree, print_tree as print_dependency_tree
from search import search_files, read_detail_range
from freshness import check_freshness


def main():
    parser = argparse.ArgumentParser(description="Ziplex")
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
    p.add_argument("--output", "-o", default=None, help="출력 파일 경로 (기본값: result/<프로젝트 폴더명>.json)")
    p.add_argument("--auto", action="store_true", help="파일 자동 선택 (전체 안전 파일 포함)")
    p.add_argument("--auto-correct", action="store_true", help="LLM 결과 자동 승인 (대화형 보정 건너뜀)")

    tr = sub.add_parser("tree", help="의존성 트리 출력")
    tr.add_argument("path", help="프로젝트 폴더 경로")

    se = sub.add_parser("search", help="프로젝트 전체 검색 (정규식)")
    se.add_argument("path", help="프로젝트 폴더 경로")
    se.add_argument("pattern", help="검색할 정규식 패턴")
    se.add_argument("--context", "-C", type=int, default=0, help="매치 앞뒤로 보여줄 줄 수")
    se.add_argument("--ignore-case", "-i", action="store_true", help="대소문자 무시")

    de = sub.add_parser("detail", help="detail.json에서 파일 일부만 읽기")
    de.add_argument("detail_path", help="<name>.detail.json 경로")
    de.add_argument("file", help="detail.json 안의 파일 키")
    de.add_argument("--start", type=int, default=None, help="시작 줄 번호 (1-based)")
    de.add_argument("--end", type=int, default=None, help="끝 줄 번호 (1-based, 포함)")

    fr = sub.add_parser("freshness", help="aif.json이 최신 상태인지 확인 (해시 비교, LLM 호출 없음)")
    fr.add_argument("path", help="프로젝트 폴더 경로")
    fr.add_argument("cache_path", help="<name>.cache.json 경로")

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
        print_file_tree(files, args.path)

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
        # 1. Collect files
        files = collect_files(args.path)
        scan_result = scan_files(files)
        safe_files = scan_result["safe"]

        print(f"\n📁 분석 대상: {len(safe_files)}개 파일\n")

        # 2. Per-file analysis
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

        # 3. Extract rules
        print(f"\n  📋 코딩 룰 추출 중...")
        rules_response = analyze_rules(signatures_map)
        try:
            rules_data = json.loads(rules_response)
        except json.JSONDecodeError:
            rules_data = {"rules": []}

        # 4. Generate prompt
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

        # 5. Print results
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
        # --auto-correct also means no terminal to prompt if an LLM call
        # keeps failing inside pack() itself (see handle_llm_failure).
        aif = pack(args.path, auto=args.auto, interactive=not args.auto_correct)
        if aif:
            if args.auto_correct:
                aif = finalize_aif(aif)  # skip interactive review, still build relationships
            else:
                aif = correct_aif(aif)  # interactive correct + build relationships
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

    elif args.command == "tree":
        files = collect_files(args.path)
        scan_result = scan_files(files)
        safe_files = scan_result["safe"]

        files_data = {}
        for file_path in safe_files:
            deps = extract_dependencies(file_path)
            files_data[file_path] = {"dependencies": deps}

        tree = build_tree(files_data)
        print_dependency_tree(tree)

    elif args.command == "search":
        files = collect_files(args.path)
        scan_result = scan_files(files)
        safe_files = scan_result["safe"]

        try:
            matches = search_files(
                safe_files, args.path, args.pattern,
                context_lines=args.context, ignore_case=args.ignore_case
            )
        except ValueError as e:
            print(f"⚠️  {e}")
            return

        if not matches:
            print("검색 결과 없음")
        for m in matches:
            print(f"\n{m.file}:{m.line_number}")
            for line in m.context_before:
                print(f"    {line}")
            print(f"  → {m.line}")
            for line in m.context_after:
                print(f"    {line}")

    elif args.command == "detail":
        with open(args.detail_path, "r", encoding="utf-8") as f:
            detail = json.load(f)

        entry = detail.get(args.file)
        if entry is None:
            print(f"⚠️  '{args.file}'는 {args.detail_path}에 없습니다")
            return

        print(read_detail_range(entry.get("compressed", ""), args.start, args.end))

    elif args.command == "freshness":
        with open(args.cache_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        files = collect_files(args.path)
        safe_files = scan_files(files)["safe"]
        report = check_freshness(safe_files, args.path, manifest)

        if not report.is_stale:
            print("✅ 최신 상태 — 변경된 파일 없음")
        else:
            print("⚠️  aif.json이 오래됐습니다")
            if report.changed:
                print(f"  변경됨 ({len(report.changed)}): {', '.join(report.changed)}")
            if report.added:
                print(f"  추가됨 ({len(report.added)}): {', '.join(report.added)}")
            if report.removed:
                print(f"  삭제됨 ({len(report.removed)}): {', '.join(report.removed)}")

if __name__ == "__main__":
    main()