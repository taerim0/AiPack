import struct
import json
import zlib
import os
import hashlib

MAGIC = b"AIPK"
VERSION = 2


class AIPKReader:
    def __init__(self, path):
        self.path = path
        self._load_index()

    def _read_exact(self, f, n):
        data = f.read(n)
        if len(data) != n:
            raise EOFError("Unexpected EOF")
        return data

    def _load_index(self):
        with open(self.path, "rb") as f:
            magic = self._read_exact(f, 4)
            if magic != MAGIC:
                raise ValueError("Invalid AIPK file")

            version = struct.unpack("<H", self._read_exact(f, 2))[0]
            if version != VERSION:
                raise ValueError(f"Unsupported version: {version}")

            index_size = struct.unpack("<I", self._read_exact(f, 4))[0]
            index_json = self._read_exact(f, index_size)

            self.index = json.loads(index_json.decode("utf-8"))

            # data 영역 시작 위치
            self.data_offset = f.tell()

    # ---------------- basic ----------------

    def list(self):
        return [e["path"] for e in self.index]

    def info(self):
        return {
            "files": len(self.index),
            "total_size": sum(e["original_size"] for e in self.index),
        }

    def tree(self):
        tree = {}
        for path in self.list():
            parts = path.split("/")
            cur = tree
            for p in parts:
                cur = cur.setdefault(p, {})
        return tree

    # ---------------- core read ----------------

    def _read_entry(self, entry):
        with open(self.path, "rb") as f:
            f.seek(self.data_offset + entry["offset"])
            data = self._read_exact(f, entry["size"])
        return data

    def _decode(self, entry, data):
        if entry["compression"] == "zlib":
            return zlib.decompress(data)
        return data

    def _verify(self, entry, data):
        if "checksum" not in entry:
            return

        calc = hashlib.sha256(data).hexdigest()
        if calc != entry["checksum"]:
            raise ValueError(f"Checksum mismatch: {entry['path']}")

    def _get_entry(self, path):
        for e in self.index:
            if e["path"] == path:
                return e
        raise FileNotFoundError(path)

    # ---------------- API ----------------

    def cat(self, target):
        entry = self._get_entry(target)
        raw = self._read_entry(entry)
        decoded = self._decode(entry, raw)
        self._verify(entry, decoded)
        return decoded

    def extract_all(self, output_dir):
        for entry in self.index:
            out_path = os.path.join(output_dir, entry["path"])
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            raw = self._read_entry(entry)
            decoded = self._decode(entry, raw)
            self._verify(entry, decoded)

            with open(out_path, "wb") as f:
                f.write(decoded)

    def extract_one(self, target, output_path):
        entry = self._get_entry(target)

        raw = self._read_entry(entry)
        decoded = self._decode(entry, raw)
        self._verify(entry, decoded)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(decoded)

    def verify(self):
        for entry in self.index:
            raw = self._read_entry(entry)
            decoded = self._decode(entry, raw)
            self._verify(entry, decoded)
        return True

    def get_manifest(self):
        try:
            data = self.cat("__manifest__.json")
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None