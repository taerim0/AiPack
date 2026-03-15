import struct

MAGIC = b"AIPK"


def read_header(f):

    magic = f.read(4)

    if magic != MAGIC:
        raise ValueError("Not an AIP file")

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
        "index_end": index_end
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


def list_files(aip_path):

    with open(aip_path, "rb") as f:

        header = read_header(f)

        print("\nHEADER")
        print(header)

        entries = read_index(f, header)

        print("\nFILES")

        for e in entries:

            print(
                f'{e["path"]} | type={e["type"]} | size={e["size"]} | offset={e["offset"]}'
            )


if __name__ == "__main__":

    aip_file = "../result/pack/pack_result.aip"

    list_files(aip_file)