"""Copy a whole website (same host) plus the images/CSS/JS it uses, ready for offline reading."""

import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import deque
from html import unescape
from urllib.parse import unquote, urldefrag, urljoin, urlparse

from . import Item, Source
from ..rules import base_mime, guess_mime

UA = "DiscKit/1.0 (offline archiver; +https://kiwix.org)"
TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>", re.S)
ATTR_RE = re.compile(
    r"""(\s)(href|src|poster|data-src|srcset)(\s*=\s*)("([^"]*)"|'([^']*)'|([^\s>"']+))""", re.I)
CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)|@import\s+(['"])([^'"]+)\3""", re.I)
PAGE_TAGS = {"a", "area", "iframe", "frame"}
ASSET_REL = ("stylesheet", "icon", "preload", "apple-touch-icon", "manifest")
MAX_BYTES = 500 * 1024 * 1024


class WebsiteSource(Source):
    kind = "website"
    estimable = False

    def __init__(self, target, max_pages=500, max_depth=5, delay=0.5,
                 external_assets=True, log=print, **_):
        url = target.strip()
        if "://" not in url:
            url = "https://" + url
        self.start = urldefrag(url)[0]
        self.host = urlparse(self.start).netloc.lower()
        self.max_pages, self.max_depth = int(max_pages), int(max_depth)
        self.delay, self.external = float(delay), bool(external_assets)
        self.log = log
        self.robots = urllib.robotparser.RobotFileParser()
        try:
            self.robots.set_url(f"{urlparse(self.start).scheme}://{self.host}/robots.txt")
            self.robots.read()
        except Exception:
            self.robots = None

    def title(self):
        return self.host

    def main_path(self):
        return self.key_link(self.start)[0]

    def count_hint(self):
        return self.max_pages

    def key_link(self, absurl):
        """Map an absolute URL to (disc path, rewritten link) or None if not archivable."""
        u = urlparse(absurl)
        if u.scheme not in ("http", "https"):
            return None
        host = u.netloc.lower()
        if host == self.host:
            prefix = ""
        elif self.external:
            prefix = f"_ext_/{host}/"
        else:
            return None
        raw_path = u.path or "/"
        key = prefix + unquote(raw_path).lstrip("/")
        if key == "" or key.endswith("/"):
            key += "index.html"
        link = "/" + prefix + raw_path.lstrip("/")
        key = key.rstrip("?")
        if u.query:
            key += "?" + u.query
            link += "?" + u.query
        return key, link

    def _allowed(self, url):
        return self.robots is None or self.robots.can_fetch(UA, url)

    def _fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.geturl(), r.headers.get("Content-Type", ""), r.read(MAX_BYTES)

    def items(self):
        queue = deque([(self.start, 0, True)])
        seen = {self.start}
        self._keys = {self.key_link(self.start)[0]}
        stored = set()
        pages = 0
        while queue:
            url, depth, is_page = queue.popleft()
            if is_page and pages >= self.max_pages:
                continue
            if is_page and urlparse(url).netloc.lower() == self.host and not self._allowed(url):
                continue
            try:
                final, ctype, body = self._fetch(url)
            except (urllib.error.URLError, OSError, ValueError) as e:
                self.log(f"skip {url}: {e}")
                continue
            finally:
                time.sleep(self.delay)
            final = urldefrag(final)[0]
            src_kl, dst_kl = self.key_link(url), self.key_link(final)
            if not dst_kl:
                continue
            if dst_kl[0] in stored:
                continue
            if src_kl and src_kl[0] != dst_kl[0]:
                yield Item(path=src_kl[0], redirect_to=dst_kl[0])
                seen.add(final)
            stored.add(dst_kl[0])
            mime = base_mime(ctype) if ctype else guess_mime(final)
            title = None
            if mime == "text/html":
                pages += 1
                text = body.decode(_charset(ctype), "replace")
                found = []
                text = self._rewrite_html(text, final, found)
                m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
                title = unescape(m.group(1)).strip() if m else dst_kl[0]
                body = text.encode("utf-8")
                ctype_out = "text/html; charset=utf-8"
                for link_url, page in found:
                    self._enqueue(queue, seen, link_url, depth + 1 if page else depth, page)
            elif mime == "text/css":
                found = []
                body = self._rewrite_css(body.decode(_charset(ctype), "replace"), final, found).encode("utf-8")
                ctype_out = "text/css; charset=utf-8"
                for link_url, page in found:
                    self._enqueue(queue, seen, link_url, depth, False)
            else:
                ctype_out = mime
            yield Item(path=dst_kl[0], mime=ctype_out, title=title, size=len(body),
                       load=lambda b=body: b)

    def _enqueue(self, queue, seen, url, depth, page):
        kl = self.key_link(url)
        if url in seen or not kl or kl[0] in self._keys:
            return
        same = urlparse(url).netloc.lower() == self.host
        if page and (not same or depth > self.max_depth):
            return
        if not page and not same and not self.external:
            return
        seen.add(url)
        self._keys.add(kl[0])
        queue.append((url, depth, page))

    def _resolve(self, base, raw, found, page):
        raw = unescape(raw.strip())
        if not raw or raw.startswith(("#", "data:", "javascript:", "mailto:", "tel:", "about:")):
            return None
        absurl, frag = urldefrag(urljoin(base, raw))
        kl = self.key_link(absurl)
        if not kl:
            return None
        if page and urlparse(absurl).netloc.lower() != self.host:
            return None
        found.append((absurl, page))
        return kl[1] + (f"#{frag}" if frag else "")

    def _rewrite_html(self, html, base, found):
        def tag_sub(m):
            tag = m.group(1).lower()
            attrs = m.group(2)
            rel = re.search(r"""rel\s*=\s*["']?([^"'>]+)""", attrs, re.I)
            rel = rel.group(1).lower() if rel else ""

            def attr_sub(a):
                name = a.group(2).lower()
                val = a.group(5) if a.group(5) is not None else (a.group(6) if a.group(6) is not None else a.group(7))
                if name == "srcset":
                    parts = []
                    for cand in val.split(","):
                        bits = cand.strip().split(None, 1)
                        if not bits:
                            continue
                        new = self._resolve(base, bits[0], found, False) or bits[0]
                        parts.append(" ".join([new] + bits[1:]))
                    new_val = ", ".join(parts)
                elif name == "href" and tag == "link":
                    if not any(r in rel for r in ASSET_REL):
                        return a.group(0)
                    new_val = self._resolve(base, val, found, False)
                elif name == "href" or (name == "src" and tag in PAGE_TAGS):
                    new_val = self._resolve(base, val, found, True)
                    if new_val is None:
                        kl = self.key_link(urljoin(base, unescape(val)))
                        if kl and urlparse(urljoin(base, val)).netloc.lower() == self.host:
                            new_val = kl[1]
                else:
                    new_val = self._resolve(base, val, found, False)
                if new_val is None:
                    return a.group(0)
                return f'{a.group(1)}{a.group(2)}{a.group(3)}"{new_val.replace(chr(34), "%22")}"'

            new_attrs = ATTR_RE.sub(attr_sub, attrs)
            if "style" in new_attrs.lower() and "url(" in new_attrs:
                new_attrs = self._rewrite_css(new_attrs, base, found)
            return f"<{m.group(1)}{new_attrs}>"

        html = TAG_RE.sub(tag_sub, html)
        html = re.sub(r"<base\b[^>]*>", "", html, flags=re.I)
        return re.sub(r"(<style\b[^>]*>)(.*?)(</style>)",
                      lambda m: m.group(1) + self._rewrite_css(m.group(2), base, found) + m.group(3),
                      html, flags=re.I | re.S)

    def _rewrite_css(self, css, base, found):
        def sub(m):
            raw = m.group(2) or m.group(4)
            new = self._resolve(base, raw, found, False)
            if new is None:
                return m.group(0)
            return f'url("{new}")' if m.group(2) else f'@import "{new}"'
        return CSS_URL_RE.sub(sub, css)


def _charset(ctype):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    return m.group(1) if m else "utf-8"
