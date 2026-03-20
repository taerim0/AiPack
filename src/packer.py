import os
import struct
import zlib

MAGIC = b"AIPK"
VERSION = 1

CHECKSUM_CRC32 = 1
COMPRESSION_NONE = 0


def collect_files(root):
    files = []
    for base, _, filenames in os.walk(root):
        for f in filenames:
            full = os.path.join(base, f)
            rel = os.path.relpath(full, root)
            files.append((full, rel.replace("\\", "/")))
    return files


def pack(input_dir, output_file):
    files = collect_files(input_dir)

    with open(output_file, "wb") as out:
        # Header
        out.write(MAGIC)
        out.write(struct.pack("<H", VERSION))

        for full_path, rel_path in files:
            with open(full_path, "rb") as f:
                data = f.read()

            # (현재는 압축 없음)
            compressed = data
            compression = COMPRESSION_NONE

            # 🔥 핵심 변경: ORIGINAL 데이터 기준 checksum
            checksum = zlib.crc32(data) & 0xffffffff

            path_bytes = rel_path.encode("utf-8")

            # ---- META 구성 ----
            meta = b""
            meta += struct.pack("<H", len(path_bytes))
            meta += path_bytes
            meta += struct.pack("<B", 0)  # type=file
            meta += struct.pack("<B", compression)
            meta += struct.pack("<Q", len(data))         # original_size
            meta += struct.pack("<Q", len(compressed))   # compressed_size
            meta += struct.pack("<B", CHECKSUM_CRC32)
            meta += struct.pack("<B", 4)
            meta += struct.pack("<I", checksum)

            block_size = len(meta) + len(compressed)

            # ---- WRITE ----
            out.write(b"FILE")
            out.write(struct.pack("<Q", block_size))
            out.write(meta)
            out.write(compressed)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AIPK v1 packer")
    parser.add_argument("input", help="input directory")
    parser.add_argument("output", help="output .aipk file")

    args = parser.parse_args()

    pack(args.input, args.output)