import argparse
from reader import AIPKReader
from packer import pack


def print_tree(d, prefix=""):
    for k, v in d.items():
        print(prefix + k)
        print_tree(v, prefix + "  ")


def cmd_pack(args):
    pack(args.input, args.output)


def cmd_list(args):
    r = AIPKReader(args.file)
    for p in r.list():
        print(p)


def cmd_info(args):
    r = AIPKReader(args.file)
    info = r.info()
    print(f"files: {info['files']}")
    print(f"total_size: {info['total_size']}")


def cmd_tree(args):
    r = AIPKReader(args.file)
    tree = r.tree()
    print_tree(tree)


def cmd_cat(args):
    r = AIPKReader(args.file)
    data = r.cat(args.path)
    try:
        print(data.decode("utf-8"))
    except:
        print(data)


def cmd_extract(args):
    r = AIPKReader(args.file)
    r.extract_all(args.output)


def cmd_extract_one(args):
    r = AIPKReader(args.file)
    r.extract_one(args.path, args.output)


def cmd_verify(args):
    r = AIPKReader(args.file)
    r.verify()
    print("OK")


def main():
    parser = argparse.ArgumentParser("aipk")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("pack")
    p.add_argument("input")
    p.add_argument("output")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("list")
    p.add_argument("file")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("info")
    p.add_argument("file")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("tree")
    p.add_argument("file")
    p.set_defaults(func=cmd_tree)

    p = sub.add_parser("cat")
    p.add_argument("file")
    p.add_argument("path")
    p.set_defaults(func=cmd_cat)

    p = sub.add_parser("extract")
    p.add_argument("file")
    p.add_argument("output")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("extract-one")
    p.add_argument("file")
    p.add_argument("path")
    p.add_argument("output")
    p.set_defaults(func=cmd_extract_one)

    # 🔥 추가 기능
    p = sub.add_parser("verify")
    p.add_argument("file")
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()