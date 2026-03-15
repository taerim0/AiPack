import argparse

from packer import pack
from unpacker import unpack
from reader import list_files


def main():

    parser = argparse.ArgumentParser(prog="aip")

    sub = parser.add_subparsers(dest="command")

    # pack
    pack_parser = sub.add_parser("pack")
    pack_parser.add_argument("input_folder")
    pack_parser.add_argument("output_file")
    pack_parser.add_argument("--compression", default="none")

    # list
    list_parser = sub.add_parser("list")
    list_parser.add_argument("aip_file")

    # extract
    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("aip_file")
    extract_parser.add_argument("output_folder")

    args = parser.parse_args()

    if args.command == "pack":

        pack(
            args.input_folder,
            args.output_file,
            compression=args.compression
        )

    elif args.command == "list":

        list_files(args.aip_file)

    elif args.command == "extract":

        unpack(
            args.aip_file,
            args.output_folder
        )

    else:

        parser.print_help()


if __name__ == "__main__":
    main()