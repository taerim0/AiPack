import os
import struct

MAGIC = b"AIPK"
VERSION = 1

def detect_type(path):
    ext = path.split(".")[-1].lower()

    if ext in ["txt", "md"]:
        return 0
    if ext in ["png", "jpg", "jpeg"]:
        return 1
    if ext in ["mp4", "avi"]:
        return 2
    return 4


def pack(folder, output):

    files = []

    for root, dirs, fs in os.walk(folder):
        for f in fs:
            path = os.path.join(root, f)
            rel = os.path.relpath(path, folder)
            files.append((path, rel))

    with open(output, "wb") as out:

        out.write(MAGIC)
        out.write(struct.pack("H", VERSION))
        out.write(struct.pack("Q", len(files)))

        index_pos = out.tell()
        out.write(b"\x00"*16)

        index = []

        for path, rel in files:

            with open(path, "rb") as f:
                data = f.read()

            offset = out.tell()
            out.write(data)

            index.append((rel, detect_type(rel), offset, len(data)))

        index_offset = out.tell()

        for rel, t, off, size in index:

            p = rel.encode()

            out.write(struct.pack("H", len(p)))
            out.write(p)

            out.write(struct.pack("B", t))
            out.write(struct.pack("Q", off))
            out.write(struct.pack("Q", size))

        end = out.tell()

        out.seek(index_pos)
        out.write(struct.pack("Q", index_offset))
        out.write(struct.pack("Q", end))