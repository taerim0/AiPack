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


def list_files(aip_path):

    with open(aip_path, "rb") as f:

        header = read_header(f)

        print("\nHEADER")
        print(header)

        entries = read_index(f, header)

        print("\nFILES")

        for e in entries:

            print(
                f'{e["path"]} | type={e["type"]} | '
                f'compressed={e["compressed_size"]} | '
                f'original={e["original_size"]} | '
                f'offset={e["offset"]}'
            )

def dataset_info(aip_path):

    with open(aip_path, "rb") as f:

        header = read_header(f)
        entries = read_index(f, header)

    print("\nDATASET INFO")
    print("files:", len(entries))
    print("compression:", header["compression"])

    total = sum(e["original_size"] for e in entries)

    print("total_size:", total)

def cat_file(aip_path, target):

    with open(aip_path, "rb") as f:

        header = read_header(f)
        entries = read_index(f, header)

        for e in entries:

            if e["path"] == target:

                f.seek(e["offset"])

                data = f.read(e["compressed_size"])

                if header["compression"] == 1:

                    import zstandard as zstd
                    data = zstd.ZstdDecompressor().decompress(data)

                try:
                    print(data.decode())
                except:
                    print("binary file")

                return

    print("file not found")

def tree(aip_path):

    with open(aip_path, "rb") as f:

        header = read_header(f)
        entries = read_index(f, header)

    for e in entries:

        print(e["path"])