"""Full-text search helpers: HTML -> plain text, safe FTS5 queries, highlighted snippets."""

import re
from html import unescape

DROP_RE = re.compile(r"<(head|script|style|noscript|template|svg|math)\b.*?</\1\s*>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"\w+", re.U)

FTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, path TEXT, title TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  title, body, content='', detail=column, tokenize='unicode61 remove_diacritics 2');
"""


def html_to_text(html):
    if isinstance(html, (bytes, bytearray, memoryview)):
        html = bytes(html).decode("utf-8", "replace")
    html = DROP_RE.sub(" ", html)
    html = TAG_RE.sub(" ", html)
    return WS_RE.sub(" ", unescape(html)).strip()


def query_terms(q):
    return WORD_RE.findall(q.casefold())[:12]


def fts_query(terms):
    """Every term must appear; the last one also matches as a prefix (search-as-you-type)."""
    if not terms:
        return None
    parts = [f'"{t}"' for t in terms[:-1]] + [f'"{terms[-1]}"*']
    return " ".join(parts)


def snippet(text, terms, width=240):
    """Return [[segment, is_match], ...] around the first hit."""
    if not text:
        return []
    if not terms:
        return [[text[:width], False]]
    hit = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\w*", re.I | re.U)
    m = hit.search(text)
    start = 0
    if m and m.start() > 80:
        start = text.rfind(" ", 0, m.start() - 70) + 1
    window = text[start:start + width]
    if start + width < len(text):
        cut = window.rfind(" ")
        window = window[:cut if cut > width // 2 else width] + " …"
    if start:
        window = "… " + window
    out, pos = [], 0
    for mm in hit.finditer(window):
        if mm.start() > pos:
            out.append([window[pos:mm.start()], False])
        out.append([mm.group(0), True])
        pos = mm.end()
    if pos < len(window):
        out.append([window[pos:], False])
    return out
