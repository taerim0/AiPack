import os
import json
import struct
import sys
import hashlib
import zlib

MAGIC = b"AIPK"
VERSION = 1


def collect_files(input_dir):
    file_list = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, input_dir)
            file_list.append((rel_path.replace("\\", "/"), full_path))
    return file_list


def print_progress(i, total, path):
    percent = (i / total) * 100
    sys.stdout.write(f"\r[{i}/{total}] {percent:.1f}% - {path}   ")
    sys.stdout.flush()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def compress_data(data, method):
    if method == "zlib":
        compressed = zlib.compress(data)
        if len(compressed) < len(data):
            return compressed, True
    return data, False


def pack(input_dir, output_file, compression="none"):
    files = collect_files(input_dir)
    total_files = len(files)

    file_entries = []
    data_blocks = []

    print(f"Packing {total_files} files...")

    # 1. 파일 읽기 + 압축 + 체크섬
    for i, (rel_path, full_path) in enumerate(files, 1):
        print_progress(i, total_files, rel_path)

        with open(full_path, "rb") as f:
            raw = f.read()

        checksum = sha256(raw)

        data, compressed_flag = compress_data(raw, compression)

        entry = {
            "path": rel_path,
            "offset": 0,
            "size": len(data),
            "original_size": len(raw),
            "compressed": compressed_flag,
            "compression": compression if compressed_flag else "none",
            "checksum": checksum
        }

        file_entries.append(entry)
        data_blocks.append(data)

    print("\nBuilding manifest...")

    manifest = {
        "type": "AIPK_ARCHIVE",
        "version": 2,
        "file_count": len(file_entries),
        "total_size": sum(e["original_size"] for e in file_entries),
        "files": [
            {
                "path": e["path"],
                "size": e["original_size"],
                "checksum": e["checksum"]
            }
            for e in file_entries
        ]
    }

    manifest_bytes = json.dumps(
        manifest, indent=2, ensure_ascii=False
    ).encode("utf-8")

    # manifest도 동일하게 처리
    m_checksum = sha256(manifest_bytes)
    m_data, m_compressed = compress_data(manifest_bytes, compression)

    manifest_entry = {
        "path": "__manifest__.json",
        "offset": 0,
        "size": len(m_data),
        "original_size": len(manifest_bytes),
        "compressed": m_compressed,
        "compression": compression if m_compressed else "none",
        "checksum": m_checksum
    }

    file_entries.insert(0, manifest_entry)
    data_blocks.insert(0, m_data)

    # 2. offset 계산
    offset = 0
    for entry, data in zip(file_entries, data_blocks):
        entry["offset"] = offset
        offset += len(data)

    # 3. index 생성
    index_json = json.dumps(
        file_entries, indent=2, ensure_ascii=False
    ).encode("utf-8")

    index_size = len(index_json)

    print("Writing archive...")

    # 4. 파일 쓰기
    with open(output_file, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<H", VERSION))

        f.write(struct.pack("<I", index_size))
        f.write(index_json)

        for data in data_blocks:
            f.write(data)

    print("Done.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument(
        "--compression",
        choices=["none", "zlib"],
        default="none",
        help="compression method"
    )

    args = parser.parse_args()

    pack(args.input, args.output, compression=args.compression)