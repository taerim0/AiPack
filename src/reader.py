import struct
import json
import zlib
import os
import hashlib
import mmap
import zstandard as zstd


MAGIC = b"AIPK"
VERSION = 2


class AIPKReader:
    def __init__(self, path, verify=True, use_mmap=True):
        self.path = path
        self.verify_enabled = verify
        self.use_mmap = use_mmap

        self._manifest = None

        self._load_index()
        self._build_map()
        self._init_mmap()

        # 🔥 zstd decoder 재사용
        self._zstd_dctx = zstd.ZstdDecompressor()

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
            self.data_offset = f.tell()

    def _build_map(self):
        self._map = {e["path"]: e for e in self.index}

    def _init_mmap(self):
        self.mm = None
        self._file = None

        if not self.use_mmap:
            return

        try:
            f = open(self.path, "rb")
            self._file = f
            self.mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception:
            self.mm = None
            self._file = None

    def list(self):
        return list(self._map.keys())

    def info(self):
        return {
            "files": len(self.index),
            "total_size": sum(e["original_size"] for e in self.index),
        }

    def _read_raw(self, entry):
        start = self.data_offset + entry["offset"]
        end = start + entry["size"]

        if self.mm:
            return self.mm[start:end]
        else:
            with open(self.path, "rb") as f:
                f.seek(start)
                return f.read(entry["size"])

    def _decode(self, entry, data):
        comp = entry["compression"]

        if comp == "zlib":
            return zlib.decompress(data)

        if comp == "zstd":
            return self._zstd_dctx.decompress(data)

        return data

    def _verify(self, entry, data):
        if not self.verify_enabled:
            return

        calc = hashlib.sha256(data).hexdigest()
        if calc != entry["checksum"]:
            raise ValueError(f"[AIPK] Checksum mismatch: {entry['path']}")

    def _get_entry(self, path):
        if path not in self._map:
            raise FileNotFoundError(path)
        return self._map[path]

    def _load_entry(self, entry):
        raw = self._read_raw(entry)
        data = self._decode(entry, raw)
        self._verify(entry, data)
        return data

    def cat(self, path):
        return self._load_entry(self._get_entry(path))

    def extract_all(self, output_dir):
        for entry in self.index:
            out_path = os.path.join(output_dir, entry["path"])
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            data = self._load_entry(entry)

            with open(out_path, "wb") as f:
                f.write(data)

    def extract_one(self, path, output_path):
        entry = self._get_entry(path)
        data = self._load_entry(entry)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(data)

    def verify(self):
        for entry in self.index:
            self._load_entry(entry)
        return True

    def get_manifest(self):
        if self._manifest:
            return self._manifest
        try:
            data = self.cat("__manifest__.json")
            self._manifest = json.loads(data.decode("utf-8"))
            return self._manifest
        except Exception:
            return None