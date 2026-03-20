import argparse

from packer import pack
from unpacker import unpack
from reader import list_files
from reader import dataset_info
from reader import tree
from reader import cat_file
from unpacker import extract_one


def main():

    parser = argparse.ArgumentParser(prog="aip")

    sub = parser.add_subparsers(dest="command")

    # pack
    pack_parser = sub.add_parser("pack")
    pack_parser.add_argument("input_folder")
    pack_parser.add_argument("output_file")
    pack_parser.add_argument("--compression", default="none")
    pack_parser.add_argument("--ai", action="store_true")  # 🔥 추가

    # list
    list_parser = sub.add_parser("list")
    list_parser.add_argument("aip_file")

    # info
    info_parser = sub.add_parser("info")
    info_parser.add_argument("aip_file")

    # tree
    tree_parser = sub.add_parser("tree")
    tree_parser.add_argument("aip_file")

    # cat
    cat_parser = sub.add_parser("cat")
    cat_parser.add_argument("aip_file")
    cat_parser.add_argument("file_path")

    # extract
    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("aip_file")
    extract_parser.add_argument("output_folder")

    # extract-one
    extract_one_parser = sub.add_parser("extract-one")
    extract_one_parser.add_argument("aip_file")
    extract_one_parser.add_argument("file_path")
    extract_one_parser.add_argument("output_folder")

    args = parser.parse_args()

    if args.command == "pack":

        pack(
            args.input_folder,
            args.output_file,
            compression=args.compression,
            ai_section=args.ai  # 🔥 추가
        )

    elif args.command == "list":

        list_files(args.aip_file)

    elif args.command == "info":

        dataset_info(args.aip_file)

    elif args.command == "tree":

        tree(args.aip_file)

    elif args.command == "cat":

        cat_file(args.aip_file, args.file_path)

    elif args.command == "extract":

        unpack(
            args.aip_file,
            args.output_folder
        )

    elif args.command == "extract-one":

        extract_one(
            args.aip_file,
            args.file_path,
            args.output_folder
        )

    else:

        parser.print_help()


if __name__ == "__main__":
    main()