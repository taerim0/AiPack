import struct
import mmap
import zlib

MAGIC = b"AIPK"

class AIPDataset:

    def __init__(self, path):

        self.path = path
        self.f = open(path, "rb")

        # memory map
        self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)

        self.header = self._read_header()
        self.entries = self._read_index()

        self.map = {e["path"]: e for e in self.entries}

    def _read_header(self):

        mm = self.mm

        magic = mm.read(4)

        if magic != MAGIC:
            raise ValueError("invalid AIP file")

        version = struct.unpack("H", mm.read(2))[0]
        compression = struct.unpack("B", mm.read(1))[0]
        file_count = struct.unpack("Q", mm.read(8))[0]

        index_offset = struct.unpack("Q", mm.read(8))[0]
        index_end = struct.unpack("Q", mm.read(8))[0]

        return {
            "version": version,
            "compression": compression,
            "file_count": file_count,
            "index_offset": index_offset,
            "index_end": index_end,
        }

    def _read_index(self):

        mm = self.mm
        mm.seek(self.header["index_offset"])

        entries = []

        for _ in range(self.header["file_count"]):

            path_len = struct.unpack("H", mm.read(2))[0]
            path = mm.read(path_len).decode()

            ftype = struct.unpack("B", mm.read(1))[0]

            offset = struct.unpack("Q", mm.read(8))[0]
            size = struct.unpack("Q", mm.read(8))[0]

            entries.append({
                "path": path,
                "type": ftype,
                "offset": offset,
                "size": size
            })

        return entries

    def __getitem__(self, key):

        entry = self.map[key]

        start = entry["offset"]
        end = start + entry["size"]

        data = self.mm[start:end]

        # compression
        if self.header["compression"] == 1:
            data = zlib.decompress(data)

        return data

    def __iter__(self):

        for e in self.entries:
            yield e["path"], self[e["path"]]

    def list(self):

        return list(self.map.keys())

    def close(self):

        self.mm.close()
        self.f.close()