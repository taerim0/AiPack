import os
from reader import AIPKReader


class AIPKUnpacker:
    def __init__(self, path, skip_meta=False):
        self.reader = AIPKReader(path)
        self.skip_meta = skip_meta

    def _safe_path(self, base, target):
        full = os.path.normpath(os.path.join(base, target))
        base = os.path.abspath(base)
        full_abs = os.path.abspath(full)

        if not full_abs.startswith(base):
            raise ValueError(f"Path traversal detected: {target}")

        return full_abs

    def extract_all(self, out_dir):
        for entry in self.reader.entries:
            path = entry.path

            # skip meta files if requested
            if self.skip_meta and path.startswith("__"):
                continue

            self._extract_entry(entry, out_dir)

    def extract_one(self, target_path, out_dir):
        entry = None
        for e in self.reader.entries:
            if e.path == target_path:
                entry = e
                break

        if not entry:
            raise FileNotFoundError(target_path)

        self._extract_entry(entry, out_dir)

    def _extract_entry(self, entry, out_dir):
        safe_out = self._safe_path(out_dir, entry.path)

        # directory support (future-proof)
        if getattr(entry, "file_type", 0) == 1:
            os.makedirs(safe_out, exist_ok=True)
            return

        data = self.reader.read_file(entry.path)

        os.makedirs(os.path.dirname(safe_out), exist_ok=True)

        with open(safe_out, "wb") as f:
            f.write(data)