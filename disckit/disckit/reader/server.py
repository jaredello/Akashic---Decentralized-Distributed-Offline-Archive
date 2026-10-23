"""Two-Drive Reader: serves the Text Disc and Media Disc together as one website."""

import json
import mimetypes
import threading
import webbrowser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from ..rules import MEDIA, TEXT, Rules, base_mime, guess_mime
from ..textindex import html_to_text, query_terms, snippet
from ..volume import Volume

SHELL = (Path(__file__).parent / "shell.html").read_text(encoding="utf-8")
_rules = Rules()


class Library:
    def __init__(self, roots):
        self.volumes = [Volume(r) for r in roots]
        if not self.volumes:
            raise ValueError("Give at least one disc (Text Disc and Media Disc).")
        sets = {v.meta["set_id"] for v in self.volumes}
        self.mismatch = len(sets) > 1
        self.text = [v for v in self.volumes if v.role == TEXT]
        self.media = [v for v in self.volumes if v.role == MEDIA]
        meta = (self.text or self.volumes)[0].meta
        self.title = meta.get("title", "Archive")
        self.main_path = meta.get("main_path", "")

    def info(self):
        return {"title": self.title, "main_path": self.main_path, "set_mismatch": self.mismatch,
                "fulltext": self.has_fulltext,
                "volumes": [v.meta for v in self.volumes]}

    def _order(self, path):
        media_first = _rules.classify(guess_mime(path)) == MEDIA
        return (self.media + self.text) if media_first else (self.text + self.media)

    def find(self, path):
        for v in self._order(path):
            row = v.lookup(path)
            if row:
                return v, row
        return None

    def redirect(self, path):
        for v in self.text:
            t = v.redirect(path)
            if t is not None:
                return t
        return None

    def search(self, q, limit=20):
        out, seen = [], set()
        if not q.strip():
            return out
        for v in self.text:
            for path, title in v.search(q, limit):
                if path not in seen:
                    seen.add(path)
                    out.append({"path": path, "title": title})
        return out[:limit]

    @property
    def has_fulltext(self):
        return any(v.has_fulltext for v in self.text)

    def fulltext(self, q, page=0, per_page=15):
        terms = query_terms(q)
        out = {"query": q, "terms": terms, "available": self.has_fulltext, "page": page,
               "total": 0, "results": []}
        if not terms or not self.has_fulltext:
            return out
        for v in self.text:
            total, rows = v.fulltext(terms, per_page, page * per_page)
            out["total"] += total
            for path, title in rows:
                hit = self.find(path)
                text = ""
                if hit:
                    mime, data = hit[0].read(path, hit[1])
                    text = html_to_text(data) if base_mime(mime) == "text/html" else bytes(data).decode("utf-8", "replace")
                    if title and text.startswith(title):
                        text = text[len(title):].lstrip()
                out["results"].append({"path": path, "title": title, "snippet": snippet(text, terms)})
        out["more"] = len(out["results"]) == per_page
        return out

    def random_path(self):
        for v in self.text:
            p = v.random_path()
            if p:
                return p
        return self.main_path

    def listing(self, prefix):
        names = set()
        for v in self.volumes:
            for p in v.list_prefix(prefix):
                rest = p[len(prefix):]
                names.add(rest.split("/", 1)[0] + ("/" if "/" in rest else ""))
        return sorted(names)


def make_handler(lib):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DiscKitReader/1.0"

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj):
            self._send(200, json.dumps(obj).encode(), "application/json")

        def _go(self, path):
            self._send(302, b"", "text/plain", {"Location": "/" + quote(path, safe="/?=&%:@!$'()*+,;-._~")})

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            u = urlsplit(self.path)
            if u.path in ("/_disckit", "/_disckit/"):
                return self._send(200, SHELL.encode("utf-8"), "text/html; charset=utf-8")
            if u.path.startswith("/_disckit/api/"):
                return self._api(u.path[len("/_disckit/api/"):], parse_qs(u.query))
            in_frame = self.headers.get("Sec-Fetch-Dest") == "iframe"
            if u.path == "/" and not in_frame:
                return self._go("_disckit/")
            if u.path == "/" and lib.main_path:
                return self._go(lib.main_path)
            self._content(unquote(u.path[1:]), u.query)

        def _api(self, name, q):
            if name == "info":
                return self._json(lib.info())
            if name == "io":
                return self._json({"volumes": [v.stats() for v in lib.volumes]})
            if name == "search":
                return self._json(lib.search((q.get("q") or [""])[0]))
            if name == "fulltext":
                page = int((q.get("page") or ["0"])[0] or 0)
                return self._json(lib.fulltext((q.get("q") or [""])[0], max(page, 0)))
            if name == "random":
                return self._json({"path": lib.random_path()})
            self._send(404, b"{}", "application/json")

        def _content(self, key, query):
            candidates = []
            if query:
                candidates.append(f"{key}?{query}")
            candidates.append(key)
            if key == "" or key.endswith("/"):
                candidates = [c + "index.html" for c in candidates] + candidates
            for c in candidates:
                hit = lib.find(c)
                if hit:
                    vol, row = hit
                    mime, data = vol.read(c, row)
                    return self._send(200, data, mime or mimetypes.guess_type(c)[0] or "application/octet-stream")
            for c in candidates:
                target = lib.redirect(c)
                if target is not None:
                    return self._go(target)
            entries = lib.listing(key if key.endswith("/") or key == "" else key + "/")
            if entries:
                if key and not key.endswith("/"):
                    return self._go(key + "/")
                return self._send(200, _listing_html(key, entries), "text/html; charset=utf-8")
            body = (f"<html><body style='font-family:Georgia,serif;padding:40px'>"
                    f"<h1 style='font-weight:normal'>Not on these discs</h1>"
                    f"<p><code>{escape(key)}</code> was not archived.</p></body></html>").encode()
            self._send(404, body, "text/html; charset=utf-8")

    return Handler


def _listing_html(prefix, names):
    rows = "".join(f"<li><a href='{quote(n)}'>{escape(n)}</a></li>" for n in names)
    return (f"<html><head><meta charset='utf-8'><title>/{escape(prefix)}</title></head>"
            f"<body style='font-family:Georgia,serif;padding:32px;max-width:900px'>"
            f"<h1 style='font-weight:normal;border-bottom:1px solid #a2a9b1'>Index of /{escape(prefix)}</h1>"
            f"<ul style='line-height:1.8;font-family:sans-serif'>{rows}</ul></body></html>").encode()


class ReaderServer:
    def __init__(self, roots, host="127.0.0.1", port=8800):
        self.lib = Library(roots)
        self.httpd = ThreadingHTTPServer((host, port), make_handler(self.lib))
        self.httpd.daemon_threads = True
        self.url = f"http://{host}:{self.httpd.server_port}/_disckit/"
        self.thread = None

    def start(self, open_browser=True):
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        if open_browser:
            webbrowser.open(self.url)
        return self.url

    def serve_forever(self, open_browser=True):
        if open_browser:
            threading.Timer(0.6, webbrowser.open, (self.url,)).start()
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
