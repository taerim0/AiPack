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

    return 4


def create_compressor(method):

    if method == "none":
        return None

    if method == "zstd":

        import zstandard as zstd

        return zstd.ZstdCompressor(level=3).compressobj()

    raise ValueError("unsupported compression")


def scan_files(folder):

    files = []

    for root, dirs, fs in os.walk(folder):

        for f in fs:

            path = os.path.join(root, f)
            rel = os.path.relpath(path, folder)

            files.append((path, rel))

    return files


def pack(folder, output, compression="none"):

    if compression not in COMPRESSION_MAP:
        raise ValueError("invalid compression")

    files = scan_files(folder)

    total_size = sum(os.path.getsize(p) for p, _ in files)

    compressor = create_compressor(compression)

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

                offset = out.tell()

                while True:

                    chunk = f.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    progress.update(len(chunk))

                    if compressor:
                        chunk = compressor.compress(chunk)

                    out.write(chunk)

                size = out.tell() - offset

            file_type = detect_type(rel)

            index.append((rel, file_type, offset, size))

        if compressor:
            out.write(compressor.flush())

        progress.close()

        # INDEX SECTION

        index_offset = out.tell()

        for rel, t, off, size in index:

            p = rel.encode()

            out.write(struct.pack("<H", len(p)))
            out.write(p)

            out.write(struct.pack("<B", t))

            out.write(struct.pack("<Q", off))
            out.write(struct.pack("<Q", size))

        end = out.tell()

        # PATCH HEADER

        out.seek(index_pos)

        out.write(struct.pack("<Q", index_offset))
        out.write(struct.pack("<Q", end))

if __name__ == "__main__":

    pack(
        "../testfiles",
        "../result/pack/pack_result.aip",
        compression="none"
    )