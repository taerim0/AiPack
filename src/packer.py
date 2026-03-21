import os
import json
import struct
import zlib
import sys
import time

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
    total_size = 0

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if not _should_skip(d)]

        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, root_dir)

            if _should_skip(rel):
                continue

            rel = rel.replace("\\", "/")
            file_list.append(rel)
            total_size += os.path.getsize(full)

    return sorted(file_list), total_size


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


def _build_tree(file_list):
    tree = {}
    for path in file_list:
        parts = path.split("/")
        cur = tree
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = "file"
    return tree


def _build_manifest(file_list, total_size):
    return {
        "type": "AIPK_ARCHIVE",
        "version": VERSION,
        "description": "Multi-file archive packaged for AI consumption",
        "file_count": len(file_list),
        "total_size": total_size,
        "primary_type": "multimodal_dataset",
        "files": [
            {
                "path": p,
                "type": _guess_type(p)
            }
            for p in file_list
        ],
        "tree": _build_tree(file_list)
    }


def _write_file_block(f, path, data):
    path_bytes = path.encode("utf-8")

    file_type = 0
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


def _print_progress(current, total, current_bytes, total_bytes, start_time):
    percent = (current / total) * 100 if total else 0
    elapsed = time.time() - start_time
    speed = current_bytes / elapsed if elapsed > 0 else 0

    sys.stdout.write(
        f"\r[{current}/{total}] {percent:.1f}% | {current_bytes/1024:.1f}KB/{total_bytes/1024:.1f}KB | {speed/1024:.1f}KB/s"
    )
    sys.stdout.flush()


def pack(input_dir, output_file):
    files, total_size = _collect_files(input_dir)

    print(f"Packing {len(files)} files...")
    print(f"Total size: {total_size/1024:.1f} KB")

    manifest = _build_manifest(files, total_size)
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

    start_time = time.time()
    processed_bytes = 0

    with open(output_file, "wb") as f:
        # HEADER
        f.write(MAGIC)
        f.write(struct.pack("<H", VERSION))

        # 1. manifest
        _write_file_block(f, "__manifest__.json", manifest_bytes)

        # 2. readme
        readme = (
            "This is an AIPK archive. It contains multiple files packaged into a single file.\n"
            "This file is NOT a single file.\n"
            "See __manifest__.json for structure.\n"
        ).encode("utf-8")
        _write_file_block(f, "__README__.txt", readme)

        # 3. actual files with progress
        for i, rel_path in enumerate(files, 1):
            full_path = os.path.join(input_dir, rel_path)

            with open(full_path, "rb") as rf:
                data = rf.read()

            _write_file_block(f, rel_path, data)

            processed_bytes += len(data)
            _print_progress(i, len(files), processed_bytes, total_size, start_time)

    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: packer.py <input_dir> <output.aipk>")
        sys.exit(1)

    pack(sys.argv[1], sys.argv[2])
