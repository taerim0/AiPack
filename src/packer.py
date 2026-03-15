import os
import struct
import mimetypes
from tqdm import tqdm

MAGIC = b"AIPK"
VERSION = 1

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

    ext = os.path.splitext(path)[1].lower()

    text_ext = {
        ".txt", ".md", ".xml", ".json", ".yaml", ".yml",
        ".csv", ".html", ".htm"
    }

    image_ext = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"
    }

    video_ext = {
        ".mp4", ".avi", ".mov", ".mkv", ".webm"
    }

    audio_ext = {
        ".mp3", ".wav", ".flac", ".aac", ".ogg"
    }

    if ext in text_ext:
        return 0

    if ext in image_ext:
        return 1

    if ext in video_ext:
        return 2

    if ext in audio_ext:
        return 3

    return 4


def scan_files(folder):

    files = []

    for root, dirs, fs in os.walk(folder):

        for f in fs:

            path = os.path.join(root, f)
            rel = os.path.relpath(path, folder)

            files.append((path, rel))

    return files


def compress_data(data, method):

    if method == "none":
        return data

    if method == "zstd":

        import zstandard as zstd

        compressor = zstd.ZstdCompressor(level=3)

        return compressor.compress(data)

    raise ValueError("unsupported compression")


def pack(folder, output, compression="none"):

    if compression not in COMPRESSION_MAP:
        raise ValueError("invalid compression")

    files = scan_files(folder)

    total_size = sum(os.path.getsize(p) for p, _ in files)

    with open(output, "wb") as out:

        # HEADER

        out.write(MAGIC)

        out.write(struct.pack("<H", VERSION))

        compression_id = COMPRESSION_MAP[compression]

        out.write(struct.pack("<B", compression_id))

        out.write(struct.pack("<Q", len(files)))

        index_pos = out.tell()

        out.write(b"\x00" * 16)

        index = []

        progress = tqdm(total=total_size, unit="B", unit_scale=True)

        # DATA SECTION

        for path, rel in files:

            with open(path, "rb") as f:

                raw = f.read()

            progress.update(len(raw))

            original_size = len(raw)

            data = compress_data(raw, compression)

            offset = out.tell()

            out.write(data)

            compressed_size = len(data)

            file_type = detect_type(rel)

            index.append((
                rel,
                file_type,
                offset,
                compressed_size,
                original_size
            ))

        progress.close()

        # INDEX SECTION

        index_offset = out.tell()

        for rel, t, off, csize, osize in index:

            p = rel.encode()

            out.write(struct.pack("<H", len(p)))
            out.write(p)

            out.write(struct.pack("<B", t))

            out.write(struct.pack("<Q", off))
            out.write(struct.pack("<Q", csize))
            out.write(struct.pack("<Q", osize))

        end = out.tell()

        # PATCH HEADER

        out.seek(index_pos)

        out.write(struct.pack("<Q", index_offset))
        out.write(struct.pack("<Q", end))