from reader import AIPKReader


class AIPKDataset:
    def __init__(self, path, use_cache=True, verify=False):
        self.path = path
        self.reader = AIPKReader(path, verify=verify)
        self.use_cache = use_cache

        # index (path -> entry)
        self.index = {e["path"]: e for e in self.reader.index}

        # cache
        self.cache = {} if use_cache else None

    # ---------------- basic ----------------

    def __len__(self):
        return len(self.index)

    def __contains__(self, key):
        return key in self.index

    def keys(self):
        return self.index.keys()

    # ---------------- API ----------------

    def get(self, path):
        if path not in self.index:
            raise KeyError(path)

        if self.use_cache and path in self.cache:
            return self.cache[path]

        data = self.reader.cat(path)

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

    # ---------------- utils ----------------

    def clear_cache(self):
        if self.cache is not None:
            self.cache.clear()

    def close(self):
        self.reader.close()

    def __del__(self):
        self.close()