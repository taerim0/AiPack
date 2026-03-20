import os
import struct
import mimetypes
import json
from tqdm import tqdm

MAGIC = b"AIPK"
VERSION = 2
CHUNK_SIZE = 1024 * 1024

COMPRESSION_MAP = {
    "none": 0,
    "zstd": 1
}


def detect_type(path):

    mime, _ = mimetypes.guess_type(path)

    if mime:

        if mime.startswith("text"):
            return 0

        if mime.startswith("image"):
            return 1

        if mime.startswith("video"):
            return 2

        if mime.startswith("audio"):
            return 3

    return 4


def create_compressor(method):

    if method == "none":
        return None

    if method == "zstd":

        import zstandard as zstd

        return zstd.ZstdCompressor(level=3)

    raise ValueError("unsupported compression")


def scan_files(folder):

    files = []

    for root, dirs, fs in os.walk(folder):

        for f in fs:

            path = os.path.join(root, f)
            rel = os.path.relpath(path, folder)

            files.append((path, rel))

    return files


def build_manifest(files):

    samples = []

    for path, rel in files:

        t = detect_type(rel)

        if t == 1:  # image

            label = os.path.basename(os.path.dirname(rel))

            samples.append({
                "image": rel,
                "label": label
            })

    return {
        "samples": samples
    }


def pack(folder, output, compression="none", ai_section=False):

    if compression not in COMPRESSION_MAP:
        raise ValueError("invalid compression")

    files = scan_files(folder)

    total_size = sum(os.path.getsize(p) for p, _ in files)

    compressor = create_compressor(compression)

    manifest = build_manifest(files)

    with open(output, "wb") as out:

        # HEADER

        out.write(MAGIC)
        out.write(struct.pack("<H", VERSION))

        compression_id = COMPRESSION_MAP[compression]
        out.write(struct.pack("<B", compression_id))

        out.write(struct.pack("<Q", len(files)))

        index_pos = out.tell()
        out.write(b"\x00" * 16)

        manifest_pos = out.tell()
        out.write(b"\x00" * 16)

        index = []

        progress = tqdm(total=total_size, unit="B", unit_scale=True)

        # DATA

        for path, rel in files:

            with open(path, "rb") as f:

                data = f.read()

                offset = out.tell()

                if compressor:
                    data = compressor.compress(data)

                out.write(data)

                size = len(data)

            file_type = detect_type(rel)

            index.append((rel, file_type, offset, size))

            progress.update(os.path.getsize(path))

        progress.close()

        # INDEX

        index_offset = out.tell()

        for rel, t, off, size in index:

            p = rel.encode()

            out.write(struct.pack("<H", len(p)))
            out.write(p)

            out.write(struct.pack("<B", t))

            out.write(struct.pack("<Q", off))
            out.write(struct.pack("<Q", size))

        index_end = out.tell()

        # MANIFEST

        manifest_offset = out.tell()

        manifest_bytes = json.dumps(manifest).encode()

        out.write(manifest_bytes)

        manifest_size = len(manifest_bytes)

        end = out.tell()

        # PATCH HEADER

        out.seek(index_pos)
        out.write(struct.pack("<Q", index_offset))
        out.write(struct.pack("<Q", index_end))

        out.seek(manifest_pos)
        out.write(struct.pack("<Q", manifest_offset))
        out.write(struct.pack("<Q", manifest_size))

        # =========================
        # 🔥 AI SECTION (추가 부분)
        # =========================

        if ai_section:

            out.seek(0, 2)  # EOF

            out.write(b"\n---AIP-AI-BEGIN---\n")
            out.write(b"@AIP-AI-V1\n\n")

            # TREE
            out.write(b"@tree\n")
            for rel, _, _, _ in index:
                out.write(rel.encode() + b"\n")

            out.write(b"\n")

            # FILE CONTENT
            for path, rel in files:

                out.write(f"@file {rel}\n".encode())

                with open(path, "rb") as f:
                    data = f.read()

                    try:
                        text = data.decode()
                        out.write(text.encode())
                    except:
                        out.write(b"[BINARY]\n")

                out.write(b"\n")

            out.write(b"\n---AIP-AI-END---\n")