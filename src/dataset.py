import mmap
from reader import AIPKReader


class AIPKDataset:
    def __init__(self, path, use_cache=True):
        self.path = path
        self.reader = AIPKReader(path)
        self.use_cache = use_cache

        # build index (path -> entry)
        self.index = {
            entry.path: entry
            for entry in self.reader.entries
            if getattr(entry, "file_type", 0) == 0  # skip directories if any
        }

        # optional cache
        self.cache = {} if use_cache else None

        # optional mmap (future optimization)
        try:
            with open(path, "rb") as f:
                self.mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception:
            self.mm = None

    def __len__(self):
        return len(self.index)

    def __contains__(self, key):
        return key in self.index

    def keys(self):
        return self.index.keys()

    def get(self, path):
        if path not in self.index:
            raise KeyError(path)

        if self.use_cache and path in self.cache:
            return self.cache[path]

        entry = self.index[path]

        if getattr(entry, "file_type", 0) == 1:
            raise IsADirectoryError(path)

        data = self.reader.read_file(path)

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
            return None