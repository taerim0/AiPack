import argparse
from extractor import extract_signatures, extract_dependencies, extract_api, debug_tree
from compressor import compress_file
from collector import collect_files, print_tree
from scanner import scan_files
from tokenizer import analyze_tokens
from selector import select_files

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

        results, _ = analyze_tokens(safe_files)
        print(f"\n📊 토큰 분석 ({len(safe_files)}개 파일)\n")
        for model, data in results.items():
            print(f"{model:10} : {data['tokens']:,} / {data['max']:,} ({data['percentage']}%) {data['bar']}")

    elif args.command == "select":
        files = collect_files(args.path)
        scan_result = scan_files(files)
        safe_files = scan_result["safe"]

        if scan_result["dangerous"]:
            print(f"\n⚠️  민감 파일 제외됨: {len(scan_result['dangerous'])}개")
            for f in scan_result["dangerous"]:
                print(f"  ❌ {f}")

        selected = select_files(safe_files, args.path)
if __name__ == "__main__":
    main()