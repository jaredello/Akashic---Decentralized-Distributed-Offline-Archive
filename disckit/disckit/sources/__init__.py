"""Source adapters. Each yields Item objects; the builder routes them to discs.

To add a new source, subclass Source and register it in SOURCES.
"""

from dataclasses import dataclass
from typing import Callable, Iterator, Optional


@dataclass
class Item:
    path: str
    mime: str = ""
    load: Optional[Callable[[], bytes]] = None
    title: Optional[str] = None
    redirect_to: Optional[str] = None
    size: int = 0


class Source:
    kind = "base"
    estimable = True

    def title(self) -> str:
        return "Archive"

    def main_path(self) -> str:
        return ""

    def count_hint(self) -> int:
        return 0

    def items(self) -> Iterator[Item]:
        raise NotImplementedError

    def close(self):
        pass


def open_source(kind, target, **opts):
    from .zim import ZimSource
    from .folder import FolderSource
    from .website import WebsiteSource
    sources = {"zim": ZimSource, "folder": FolderSource, "website": WebsiteSource}
    if kind not in sources:
        raise ValueError(f"Unknown source type {kind!r}; choose one of {', '.join(sources)}")
    return sources[kind](target, **opts)
