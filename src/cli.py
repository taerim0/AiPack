import argparse
from reader import AIPKReader
from packer import pack


def print_tree(d, prefix=""):
    for k, v in d.items():
        print(prefix + k)
        if isinstance(v, dict):
            print_tree(v, prefix + "  ")


def human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# -------- Commands --------

def cmd_pack(args):
    pack(args.input, args.output, compression=args.compression)


def cmd_ls(args):
    r = AIPKReader(args.file)

    if args.long:
        manifest = r.get_manifest()
        if manifest:
            info_map = {f["path"]: f for f in manifest.get("files", [])}
        else:
            info_map = {}

        for p in r.list():
            entry = info_map.get(p)
            if entry:
                print(f"{p}\t{entry.get('type','?')}")
            else:
                print(p)
    else:
        for p in r.list():
            print(p)


def cmd_info(args):
    r = AIPKReader(args.file)

    manifest = r.get_manifest()
    if manifest:
        print(f"files: {manifest.get('file_count')}")
        print(f"total_size: {human_size(manifest.get('total_size',0))}")
        print(f"type: {manifest.get('primary_type')}")
    else:
        info = r.info()
        print(f"files: {info['files']}")
        print(f"total_size: {human_size(info['total_size'])}")


def cmd_tree(args):
    r = AIPKReader(args.file)

    manifest = r.get_manifest()
    if manifest and "tree" in manifest:
        print_tree(manifest["tree"])
    else:
        tree = r.tree()
        print_tree(tree)


def cmd_cat(args):
    r = AIPKReader(args.file)
    data = r.cat(args.path)

    # 🔥 binary guard
    if b"\x00" in data[:100]:
        print("[binary data]")
        return

    try:
        print(data.decode("utf-8"))
    except Exception:
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


def cmd_manifest(args):
    r = AIPKReader(args.file)
    manifest = r.get_manifest()

    if not manifest:
        print("No manifest found")
        return

    import json
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


# -------- CLI --------

def main():
    parser = argparse.ArgumentParser("aipk")
    sub = parser.add_subparsers(dest="cmd")

    # pack
    p = sub.add_parser("pack", help="Pack folder into aipk")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument(
        "--compression",
        choices=["none", "zlib"],
        default="none",
        help="compression method (default: none)"
    )
    p.set_defaults(func=cmd_pack)

    # ls
    p = sub.add_parser("ls", help="List files")
    p.add_argument("file")
    p.add_argument("-l", "--long", action="store_true", help="Detailed list")
    p.set_defaults(func=cmd_ls)

    # info
    p = sub.add_parser("info", help="Show archive info")
    p.add_argument("file")
    p.set_defaults(func=cmd_info)

    # tree
    p = sub.add_parser("tree", help="Show directory tree")
    p.add_argument("file")
    p.set_defaults(func=cmd_tree)

    # cat
    p = sub.add_parser("cat", help="Print file content")
    p.add_argument("file")
    p.add_argument("path")
    p.set_defaults(func=cmd_cat)

    # extract
    p = sub.add_parser("extract", help="Extract all files")
    p.add_argument("file")
    p.add_argument("output")
    p.set_defaults(func=cmd_extract)

    # extract-one
    p = sub.add_parser("extract-one", help="Extract single file")
    p.add_argument("file")
    p.add_argument("path")
    p.add_argument("output")
    p.set_defaults(func=cmd_extract_one)

    # verify
    p = sub.add_parser("verify", help="Verify checksums")
    p.add_argument("file")
    p.set_defaults(func=cmd_verify)

    # manifest
    p = sub.add_parser("manifest", help="Show manifest JSON")
    p.add_argument("file")
    p.set_defaults(func=cmd_manifest)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()