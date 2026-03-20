import struct
import zlib
import os

MAGIC = b"AIPK"
VERSION = 1

CHECKSUM_CRC32 = 1
COMPRESSION_NONE = 0


class AIPKReader:
    def __init__(self, path):
        self.path = path

    def _read_exact(self, f, n):
        data = f.read(n)
        if len(data) != n:
            raise EOFError("Unexpected EOF")
        return data

    def _scan(self):
        with open(self.path, "rb") as f:
            magic = self._read_exact(f, 4)
            if magic != MAGIC:
                raise ValueError("Invalid AIPK file")

            version = struct.unpack("<H", self._read_exact(f, 2))[0]
            if version != VERSION:
                raise ValueError(f"Unsupported version: {version}")

            while True:
                header = f.read(4)
                if not header:
                    break

                if header != b"FILE":
                    raise ValueError("Invalid block")

                block_size = struct.unpack("<Q", self._read_exact(f, 8))[0]
                block_start = f.tell()

                path_len = struct.unpack("<H", self._read_exact(f, 2))[0]
                path = self._read_exact(f, path_len).decode("utf-8")

                file_type = struct.unpack("<B", self._read_exact(f, 1))[0]
                compression = struct.unpack("<B", self._read_exact(f, 1))[0]

                original_size = struct.unpack("<Q", self._read_exact(f, 8))[0]
                compressed_size = struct.unpack("<Q", self._read_exact(f, 8))[0]

                checksum_type = struct.unpack("<B", self._read_exact(f, 1))[0]
                checksum_size = struct.unpack("<B", self._read_exact(f, 1))[0]
                checksum = self._read_exact(f, checksum_size)

                data_offset = f.tell()
                data = self._read_exact(f, compressed_size)

                yield {
                    "path": path,
                    "type": file_type,
                    "compression": compression,
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "checksum_type": checksum_type,
                    "checksum": checksum,
                    "data": data,
                }

                f.seek(block_start + block_size)

    def list(self):
        return [entry["path"] for entry in self._scan()]

    def info(self):
        total_files = 0
        total_size = 0

        for entry in self._scan():
            total_files += 1
            total_size += entry["original_size"]

        return {
            "files": total_files,
            "total_size": total_size,
        }

    def tree(self):
        tree = {}
        for path in self.list():
            parts = path.split("/")
            cur = tree
            for p in parts:
                cur = cur.setdefault(p, {})
        return tree

    def cat(self, target):
        for entry in self._scan():
            if entry["path"] == target:
                return self._decode_and_verify(entry)
        raise FileNotFoundError(target)

    def extract_all(self, output_dir):
        for entry in self._scan():
            out_path = os.path.join(output_dir, entry["path"])
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            data = self._decode_and_verify(entry)

            with open(out_path, "wb") as f:
                f.write(data)

    def extract_one(self, target, output_path):
        for entry in self._scan():
            if entry["path"] == target:
                data = self._decode_and_verify(entry)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(data)
                return
        raise FileNotFoundError(target)

    def verify(self):
        for entry in self._scan():
            self._decode_and_verify(entry)
        return True

    def _decode_and_verify(self, entry):
        data = entry["data"]

        # (현재 압축 없음)
        if entry["compression"] == COMPRESSION_NONE:
            decoded = data
        else:
            raise NotImplementedError("Compression not supported yet")

        # 🔥 ORIGINAL 기준 checksum 검증
        if entry["checksum_type"] == CHECKSUM_CRC32:
            calc = zlib.crc32(decoded) & 0xffffffff
            stored = struct.unpack("<I", entry["checksum"])[0]
            if calc != stored:
                raise ValueError(f"Checksum mismatch: {entry['path']}")

        return decoded