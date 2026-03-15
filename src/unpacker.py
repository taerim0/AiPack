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

        compressed_size = struct.unpack("<Q", f.read(8))[0]

        original_size = struct.unpack("<Q", f.read(8))[0]

        entries.append({
            "path": path,
            "type": file_type,
            "offset": offset,
            "compressed_size": compressed_size,
            "original_size": original_size
        })

    return entries


def decompress_data(data, compression):

    if compression == 0:
        return data

    if compression == 1:

        import zstandard as zstd

        d = zstd.ZstdDecompressor()

        return d.decompress(data)

    raise ValueError("unsupported compression")


def extract_file(aip, entry, output_folder, compression):

    target_path = os.path.join(output_folder, entry["path"])

    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    aip.seek(entry["offset"])

    compressed_size = entry["compressed_size"]

    data = aip.read(compressed_size)

    data = decompress_data(data, compression)

    with open(target_path, "wb") as out:

        out.write(data)


def unpack(aip_path, output_folder):

    with open(aip_path, "rb") as f:

        header = read_header(f)

        print("HEADER:", header)

        entries = read_index(f, header)

        print("FILES:", len(entries))

        for entry in entries:

            print("extracting:", entry["path"])

            extract_file(
                f,
                entry,
                output_folder,
                header["compression"]
            )