import os
import json
import struct
import sys

MAGIC = b"AIPK"
VERSION = 2


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


def pack(input_dir, output_file):
    files = collect_files(input_dir)
    total_files = len(files)

    file_entries = []
    data_blocks = []

    print(f"Packing {total_files} files...")

    # 1. 파일 읽기 (기존 흐름 유지)
    for i, (rel_path, full_path) in enumerate(files, 1):
        print_progress(i, total_files, rel_path)

        with open(full_path, "rb") as f:
            data = f.read()

        file_entries.append({
            "path": rel_path,
            "size": len(data),
            "offset": 0
        })

        data_blocks.append(data)

    print("\nBuilding manifest...")

    # 2. manifest (기존처럼 포함)
    manifest = {
        "type": "AIPK_ARCHIVE",
        "version": 2,
        "file_count": len(file_entries),
        "total_size": sum(e["size"] for e in file_entries),
        "files": [{"path": e["path"], "size": e["size"]} for e in file_entries]
    }

    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

    file_entries.insert(0, {
        "path": "__manifest__.json",
        "size": len(manifest_bytes),
        "offset": 0
    })
    data_blocks.insert(0, manifest_bytes)

    # 3. offset 계산
    offset = 0
    for entry, data in zip(file_entries, data_blocks):
        entry["offset"] = offset
        offset += len(data)

    # 4. index 생성
    index_json = json.dumps(file_entries, indent=2, ensure_ascii=False).encode("utf-8")
    index_size = len(index_json)

    print("Writing archive...")

    # 5. 파일 쓰기
    with open(output_file, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<H", VERSION))

        # index
        f.write(struct.pack("<I", index_size))
        f.write(index_json)

        # data
        for data in data_blocks:
            f.write(data)

    print("Done.")