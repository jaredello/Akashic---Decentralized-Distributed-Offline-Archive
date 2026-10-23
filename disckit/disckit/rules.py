"""Decides which disc each file belongs on, based on its MIME type."""

import mimetypes

TEXT, MEDIA = "text", "media"

SKIP_TYPES = {
    "application/octet-stream+xapian",
    "application/octet-stream+zimlisting",
}
MEDIA_PREFIXES = ("image/", "audio/", "video/", "font/")
MEDIA_TYPES = {
    "application/pdf", "application/zip", "application/x-7z-compressed",
    "application/x-tar", "application/gzip", "application/octet-stream",
    "application/vnd.ms-fontobject", "application/x-font-ttf", "application/font-woff",
    "application/ogg", "application/x-shockwave-flash",
}
COMPRESSIBLE_PREFIXES = ("text/",)
COMPRESSIBLE_TYPES = {
    "application/javascript", "application/json", "application/xml",
    "application/xhtml+xml", "image/svg+xml", "application/rss+xml",
    "application/atom+xml", "application/ld+json",
}

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("font/woff2", ".woff2")


def base_mime(mime):
    return (mime or "application/octet-stream").split(";")[0].strip().lower()


def guess_mime(path):
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


class Rules:
    def __init__(self, svg_on_text=False):
        self.svg_on_text = svg_on_text

    def classify(self, mime):
        """Return TEXT, MEDIA or None (skip)."""
        m = base_mime(mime)
        if m in SKIP_TYPES:
            return None
        if m == "image/svg+xml" and self.svg_on_text:
            return TEXT
        if m.startswith(MEDIA_PREFIXES) or m in MEDIA_TYPES:
            return MEDIA
        return TEXT

    @staticmethod
    def compressible(mime):
        m = base_mime(mime)
        return m.startswith(COMPRESSIBLE_PREFIXES) or m in COMPRESSIBLE_TYPES
