import os
import struct

MAGIC = b"AIPK"
CHUNK_SIZE = 1024 * 1024


def read_header(f):

    magic = f.read(4)

    if magic != MAGIC:
        raise ValueError("Not a valid AIP file")

    version = struct.unpack("<H", f.read(2))[0]
    compression = struct.unpack("<B", f.read(1))[0]
    file_count = struct.unpack("<Q", f.read(8))[0]

    index_offset = struct.unpack("<Q", f.read(8))[0]
    index_end = struct.unpack("<Q", f.read(8))[0]

    return {
        "version": version,
        "compression": compression,
        "file_count": file_count,
        "index_offset": index_offset,
        "index_end": index_end,
    }


def read_index(f, header):

    entries = []

    f.seek(header["index_offset"])

    while f.tell() < header["index_end"]:

        path_len = struct.unpack("<H", f.read(2))[0]

        path = f.read(path_len).decode()

        file_type = struct.unpack("<B", f.read(1))[0]

        offset = struct.unpack("<Q", f.read(8))[0]
        size = struct.unpack("<Q", f.read(8))[0]

        entries.append({
            "path": path,
            "type": file_type,
            "offset": offset,
            "size": size
        })

    return entries


def extract_file(aip, entry, output_folder):

    target_path = os.path.join(output_folder, entry["path"])

    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    aip.seek(entry["offset"])

    remaining = entry["size"]

    with open(target_path, "wb") as out:

        while remaining > 0:

            chunk = aip.read(min(CHUNK_SIZE, remaining))

            if not chunk:
                break

            out.write(chunk)

            remaining -= len(chunk)


def unpack(aip_path, output_folder):

    with open(aip_path, "rb") as f:

        header = read_header(f)

        print("HEADER:", header)

        entries = read_index(f, header)

        print("FILES:", len(entries))

        for entry in entries:

            print("extracting:", entry["path"])

            extract_file(f, entry, output_folder)