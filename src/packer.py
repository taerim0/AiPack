import os
import struct
import zlib
from pathlib import Path

MAGIC_HEADER = b"AIPK"
MAGIC_FILE = b"FILE"
VERSION = 3

IGNORE = set()
IGNORE_EXT = set()


def should_ignore(path: Path):
    return False


def iter_files(root):
    for p in Path(root).rglob("*"):
        if p.is_file() and not should_ignore(p):
            yield p


def pack(input_dir, output_file, compress=True):
    files = list(iter_files(input_dir))

    with open(output_file, "wb") as f:
        # HEADER
        f.write(MAGIC_HEADER)
        f.write(struct.pack("<H", VERSION))
        f.write(struct.pack("<B", int(compress)))
        f.write(struct.pack("<Q", len(files)))

        index_entries = []

        for file_path in files:
            rel_path = str(file_path.relative_to(input_dir)).replace("\\", "/")
            path_bytes = rel_path.encode("utf-8")

            with open(file_path, "rb") as rf:
                data = rf.read()

            original_size = len(data)

            if compress:
                data = zlib.compress(data)

            compressed_size = len(data)
            checksum = zlib.crc32(data)

            offset = f.tell()

            # FILE BLOCK
            f.write(MAGIC_FILE)
            f.write(struct.pack("<H", len(path_bytes)))
            f.write(path_bytes)
            f.write(struct.pack("<Q", original_size))
            f.write(struct.pack("<Q", compressed_size))
            f.write(struct.pack("<I", checksum))
            f.write(struct.pack("<B", int(compress)))
            f.write(data)

            index_entries.append((rel_path, offset, compressed_size))

        # INDEX (JSON-like simple format)
        index_start = f.tell()
        f.write(b"AIDX")

        for path, offset, size in index_entries:
            pb = path.encode("utf-8")
            f.write(struct.pack("<H", len(pb)))
            f.write(pb)
            f.write(struct.pack("<Q", offset))
            f.write(struct.pack("<Q", size))

        index_end = f.tell()

        # FOOTER
        f.write(b"AEND")
        f.write(struct.pack("<Q", index_start))
        f.write(struct.pack("<Q", index_end))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AIPK v3 packer")
    parser.add_argument("input", help="Input directory")
    parser.add_argument("output", help="Output .aip file")
    parser.add_argument("--no-compress", action="store_true")

    args = parser.parse_args()

    pack(args.input, args.output, compress=not args.no_compress)
