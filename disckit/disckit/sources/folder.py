"""Any folder of files: documents, photo libraries, static websites, research data."""

import os
import re
from pathlib import Path

from . import Item, Source
from ..rules import guess_mime

TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)


def _html_title(p):
    try:
        with open(p, "rb") as f:
            m = TITLE_RE.search(f.read(65536))
        return m.group(1).decode("utf-8", "replace").strip() if m else None
    except OSError:
        return None


class FolderSource(Source):
    kind = "folder"

    def __init__(self, target, **_):
        self.root = Path(target).expanduser().resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"{self.root} is not a folder")
        self._files = None

    def _scan(self):
        if self._files is None:
            files = []
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                for name in sorted(filenames):
                    if not name.startswith("."):
                        files.append(Path(dirpath) / name)
            self._files = files
        return self._files

    def title(self):
        return self.root.name

    def main_path(self):
        for name in ("index.html", "index.htm"):
            if (self.root / name).exists():
                return name
        return ""

    def count_hint(self):
        return len(self._scan())

    def items(self):
        for p in self._scan():
            rel = p.relative_to(self.root).as_posix()
            mime = guess_mime(rel)
            title = (_html_title(p) or p.stem) if mime == "text/html" else p.name
            yield Item(path=rel, mime=mime, title=title, size=p.stat().st_size,
                       load=lambda p=p: p.read_bytes())
