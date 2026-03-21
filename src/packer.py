import os
import json
import struct
import zlib

MAGIC = b"AIPK"
VERSION = 1

FILE_TAG = b"FILE"

COMPRESSION_NONE = 0
CHECKSUM_CRC32 = 1


def _should_skip(path):
    parts = path.split(os.sep)
    return (
        "__pycache__" in parts
        or any(p.endswith(".pyc") for p in parts)
    )


def _collect_files(root_dir):
    file_list = []
    for root, dirs, files in os.walk(root_dir):
        # filter dirs
        dirs[:] = [d for d in dirs if not _should_skip(d)]

        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), root_dir)
            if _should_skip(rel_path):
                continue
            file_list.append(rel_path.replace("\\", "/"))
    return sorted(file_list)


def _guess_type(path):
    ext = path.lower().split(".")[-1]
    if ext in ["jpg", "jpeg", "png", "gif"]:
        return "image"
    if ext in ["xml"]:
        return "xml"
    if ext in ["json"]:
        return "json"
    if ext in ["txt", "md", "py"]:
        return "text"
    return "binary"


def _build_manifest(file_list):
    return {
        "type": "AIPK_ARCHIVE",
        "version": VERSION,
        "description": "Multi-file archive packaged for AI consumption",
        "file_count": len(file_list),
        "files": [
            {
                "path": p,
                "type": _guess_type(p)
            }
            for p in file_list
        ]
    }


def _write_file_block(f, path, data):
    path_bytes = path.encode("utf-8")

    file_type = 0  # file only
    compression = COMPRESSION_NONE

    original_size = len(data)
    compressed_data = data
    compressed_size = len(compressed_data)

    checksum = zlib.crc32(data) & 0xffffffff
    checksum_bytes = struct.pack("<I", checksum)

    meta = b""
    meta += struct.pack("<H", len(path_bytes))
    meta += path_bytes
    meta += struct.pack("B", file_type)
    meta += struct.pack("B", compression)
    meta += struct.pack("<Q", original_size)
    meta += struct.pack("<Q", compressed_size)
    meta += struct.pack("B", CHECKSUM_CRC32)
    meta += struct.pack("B", len(checksum_bytes))
    meta += checksum_bytes

    block_size = len(meta) + len(compressed_data)

    f.write(FILE_TAG)
    f.write(struct.pack("<Q", block_size))
    f.write(meta)
    f.write(compressed_data)


def pack(input_dir, output_file):
    files = _collect_files(input_dir)

    manifest = _build_manifest(files)
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

    with open(output_file, "wb") as f:
        # HEADER
        f.write(MAGIC)
        f.write(struct.pack("<H", VERSION))

        # 🔥 1. WRITE MANIFEST FIRST (AI 핵심)
        _write_file_block(f, "__manifest__.json", manifest_bytes)

        # 🔥 2. OPTIONAL README
        readme = (
            "This is an AIPK archive. It contains multiple files packaged into a single file.\n"
            "See __manifest__.json for structure.\n"
        ).encode("utf-8")
        _write_file_block(f, "__README__.txt", readme)

        # 🔥 3. WRITE ACTUAL FILES
        for rel_path in files:
            full_path = os.path.join(input_dir, rel_path)
            with open(full_path, "rb") as rf:
                data = rf.read()
            _write_file_block(f, rel_path, data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: packer.py <input_dir> <output.aipk>")
        sys.exit(1)

    pack(sys.argv[1], sys.argv[2])
