import argparse
from extractor import extract_signatures
from compressor import compress_file

def main():
    parser = argparse.ArgumentParser(description="AiPack v2")
    sub = parser.add_subparsers(dest="command")

    # compress 명령어
    c = sub.add_parser("compress", help="코드 압축")
    c.add_argument("file", help="파일 경로")

    # signatures 명령어
    s = sub.add_parser("signatures", help="시그니처 추출")
    s.add_argument("file", help="파일 경로")

    args = parser.parse_args()

    if args.command == "compress":
        print(compress_file(args.file))

    elif args.command == "signatures":
        sigs = extract_signatures(args.file)
        for sig in sigs:
            print(f"  {sig}")

if __name__ == "__main__":
    main()