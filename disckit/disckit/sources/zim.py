"""Kiwix .zim files (Wikipedia, Wiktionary, Stack Exchange, Gutenberg, ...)."""

from pathlib import Path

from . import Item, Source


class ZimSource(Source):
    kind = "zim"

    def __init__(self, target, cache_mb=512, **_):
        try:
            import libzim
            from libzim.reader import Archive
        except ImportError as e:
            raise RuntimeError("Reading .zim files needs libzim: pip install libzim") from e
        libzim.reader.set_cluster_cache_max_size(int(cache_mb) * 1024 * 1024)
        self.path = Path(target)
        self.zim = Archive(self.path)

    def title(self):
        try:
            return bytes(self.zim.get_metadata("Title")).decode() or self.path.stem
        except Exception:
            return self.path.stem

    def main_path(self):
        return self.zim.main_entry.path if self.zim.has_main_entry else ""

    def count_hint(self):
        return self.zim.all_entry_count

    def items(self):
        z = self.zim
        for i in range(z.all_entry_count):
            e = z._get_entry_by_id(i)
            if e.is_redirect:
                try:
                    target = e.get_redirect_entry().path
                except Exception:
                    continue
                yield Item(path=e.path, redirect_to=target, title=e.title)
                continue
            it = e.get_item()
            mime = it.mimetype
            title = e.title if mime.startswith("text/html") and e.title else None
            yield Item(path=e.path, mime=mime, title=title, size=it.size,
                       load=lambda it=it: bytes(it.content))
