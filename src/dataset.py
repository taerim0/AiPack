import mmap
import os
import zlib
import hashlib
from reader import AIPKReader


class AIPKDataset:
    def __init__(self, path, use_cache=True):
        self.path = path
        self.reader = AIPKReader(path)
        self.use_cache = use_cache

        # index (path -> entry)
        self.index = {
            e["path"]: e
            for e in self.reader.index
        }

        # cache
        self.cache = {} if use_cache else None

        # mmap (핵심 최적화)
        try:
            f = open(path, "rb")
            self._file = f
            self.mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception:
            self.mm = None
            self._file = None

    # ---------------- basic ----------------

    def __len__(self):
        return len(self.index)

    def __contains__(self, key):
        return key in self.index

    def keys(self):
        return self.index.keys()

    # ---------------- core ----------------

    def _read_raw(self, entry):
        start = self.reader.data_offset + entry["offset"]
        end = start + entry["size"]

        if self.mm:
            return self.mm[start:end]
        else:
            with open(self.path, "rb") as f:
                f.seek(start)
                return f.read(entry["size"])

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

    # ---------------- API ----------------

    def get(self, path):
        if path not in self.index:
            raise KeyError(path)

        if self.use_cache and path in self.cache:
            return self.cache[path]

        entry = self.index[path]

        raw = self._read_raw(entry)
        data = self._decode(entry, raw)
        self._verify(entry, data)

        if self.use_cache:
            self.cache[path] = data

        return data

    def __getitem__(self, path):
        return self.get(path)

    def iter_items(self):
        for path in self.index:
            yield path, self.get(path)

    def get_text(self, path, encoding="utf-8"):
        data = self.get(path)
        try:
            return data.decode(encoding)
        except Exception:
            return None

    # ---------------- cleanup ----------------

    def close(self):
        if self.mm:
            self.mm.close()
        if self._file:
            self._file.close()

    def __del__(self):
        self.close()