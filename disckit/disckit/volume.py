"""On-disc volume format (disckit/1).

<disc root>/
  DISCKIT.json      volume metadata (set id, role, disc index, title, main page)
  index.db          SQLite: entries, redirects, titles
  packs/pack-NNNNN.bin  data packs (<= 1 GiB each, safe for UDF/ISO)
  SHA256SUMS        checksums of every file above

Text is grouped into ~1 MB clusters and compressed (zstd if available, else zlib),
media is stored raw (it is already compressed).
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
import zlib
from collections import OrderedDict, deque
from pathlib import Path

from .textindex import FTS_SCHEMA, fts_query

try:
    import zstandard as _zstd
except ImportError:
    _zstd = None

FORMAT = "disckit/1"
PACK_LIMIT = 1 << 30
CLUSTER_TARGET = 1 << 20
FS_MARGIN = 0.985
GB = 1000 ** 3


class DiscFullError(Exception):
    pass


def _compress(data):
    if _zstd:
        return "zstd", _zstd.ZstdCompressor(level=12).compress(data)
    return "zlib", zlib.compress(data, 9)


def _decompress(codec, blob):
    if codec == "raw":
        return blob
    if codec == "zlib":
        return zlib.decompress(blob)
    if codec == "zstd":
        if not _zstd:
            raise RuntimeError("This disc uses zstd compression: pip install zstandard")
        return _zstd.ZstdDecompressor().decompress(blob)
    raise ValueError(f"Unknown codec {codec}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  path TEXT PRIMARY KEY, mime TEXT, pack INTEGER, off INTEGER, clen INTEGER,
  codec TEXT, ioff INTEGER, ilen INTEGER);
CREATE TABLE IF NOT EXISTS redirects (path TEXT PRIMARY KEY, target TEXT);
CREATE TABLE IF NOT EXISTS titles (path TEXT, title TEXT, key TEXT);
"""


def sha256_file(path, chunk=4 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def check_empty(root):
    root = Path(root)
    if root.exists() and not root.is_dir():
        raise NotADirectoryError(f"{root} is not a folder")
    if root.exists() and any(not p.name.startswith(".") for p in root.iterdir()):
        raise FileExistsError(f"{root} is not empty. Choose an empty folder for each disc.")


class VolumeWriter:
    def __init__(self, root, role, set_id, label, capacity_bytes, compress=True,
                 disc_index=1, disc_count=2, fulltext=False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        check_empty(self.root)
        (self.root / "packs").mkdir(exist_ok=True)
        self.role, self.set_id, self.label = role, set_id, label
        self.capacity = int(capacity_bytes * FS_MARGIN)
        self.compress = compress
        self.disc_index, self.disc_count = disc_index, disc_count
        self.db = sqlite3.connect(str(self.root / "index.db"))
        self.db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
        self.fulltext = fulltext
        self.fts_docs = 0
        if fulltext:
            self.db.executescript(FTS_SCHEMA)
        self.pack_no, self.pack_f, self.pack_pos = -1, None, 0
        self.packs_bytes = 0
        self.cluster, self.cluster_bytes = [], 0
        self.entries = self.redirects = 0
        self.raw_bytes = 0
        self._pending = 0
        self._db_size = 0
        self._next_pack()

    @property
    def used_bytes(self):
        return self.packs_bytes + self._db_size

    def _next_pack(self):
        if self.pack_f:
            self.pack_f.close()
        self.pack_no += 1
        self.pack_f = open(self.root / "packs" / f"pack-{self.pack_no:05d}.bin", "wb")
        self.pack_pos = 0

    def _write_blob(self, blob):
        if self.packs_bytes + self._db_size + len(blob) > self.capacity:
            raise DiscFullError(
                f"{self.role.title()} Disc is full ({self.capacity / GB:.1f} GB usable). "
                "Use a larger disc size or a smaller source.")
        if self.pack_pos and self.pack_pos + len(blob) > PACK_LIMIT:
            self._next_pack()
        off = self.pack_pos
        self.pack_f.write(blob)
        self.pack_pos += len(blob)
        self.packs_bytes += len(blob)
        return self.pack_no, off

    def _tick(self):
        self._pending += 1
        if self._pending >= 2000:
            self.db.commit()
            self._pending = 0
            self._db_size = os.path.getsize(self.root / "index.db")

    def add(self, path, mime, data, title=None, compressible=False):
        data = bytes(data)
        self.raw_bytes += len(data)
        self.entries += 1
        if title:
            self.add_title(path, title)
        if self.compress and compressible and len(data) < CLUSTER_TARGET:
            self.cluster.append((path, mime, data))
            self.cluster_bytes += len(data)
            if self.cluster_bytes >= CLUSTER_TARGET:
                self._flush_cluster()
        else:
            pack, off = self._write_blob(data)
            self.db.execute("INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?)",
                            (path, mime, pack, off, len(data), "raw", 0, len(data)))
        self._tick()

    def _flush_cluster(self):
        if not self.cluster:
            return
        joined = b"".join(d for _, _, d in self.cluster)
        codec, blob = _compress(joined)
        pack, off = self._write_blob(blob)
        ioff = 0
        rows = []
        for path, mime, d in self.cluster:
            rows.append((path, mime, pack, off, len(blob), codec, ioff, len(d)))
            ioff += len(d)
        self.db.executemany("INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?)", rows)
        self.cluster, self.cluster_bytes = [], 0

    def add_redirect(self, path, target, title=None):
        self.redirects += 1
        self.db.execute("INSERT OR REPLACE INTO redirects VALUES (?,?)", (path, target))
        if title:
            self.add_title(path, title)
        self._tick()

    def add_fulltext(self, path, title, text):
        cur = self.db.execute("INSERT INTO docs(path, title) VALUES (?,?)", (path, title))
        self.db.execute("INSERT INTO fts(rowid, title, body) VALUES (?,?,?)", (cur.lastrowid, title, text))
        self.fts_docs += 1

    def add_title(self, path, title):
        self.db.execute("INSERT INTO titles VALUES (?,?,?)", (path, title, title.casefold()))

    def close(self, meta):
        self._flush_cluster()
        self.pack_f.close()
        self.db.execute("CREATE INDEX IF NOT EXISTS titles_key ON titles(key)")
        if self.fulltext:
            self.db.execute("INSERT INTO fts(fts) VALUES('optimize')")
        self.db.commit()
        self.entries = self.db.execute("SELECT count(*) FROM entries").fetchone()[0]
        self.redirects = self.db.execute("SELECT count(*) FROM redirects").fetchone()[0]
        self.db.close()
        info = {
            "format": FORMAT, "set_id": self.set_id, "role": self.role, "label": self.label,
            "disc_index": self.disc_index, "disc_count": self.disc_count,
            "entries": self.entries, "redirects": self.redirects, "raw_bytes": self.raw_bytes,
            "packs": self.pack_no + 1, "fulltext": self.fulltext, "fulltext_docs": self.fts_docs, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **meta,
        }
        (self.root / "DISCKIT.json").write_text(json.dumps(info, indent=2))
        lines = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS":
                lines.append(f"{sha256_file(p)}  {p.relative_to(self.root).as_posix()}")
        (self.root / "SHA256SUMS").write_text("\n".join(lines) + "\n")
        info["disc_bytes"] = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        return info


class Volume:
    """Read-only view of one burned (or staged) disc, with live I/O statistics."""

    def __init__(self, root):
        self.root = Path(root)
        meta_path = self.root / "DISCKIT.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No DiscKit disc found at {self.root}")
        self.meta = json.loads(meta_path.read_text())
        self.role = self.meta["role"]
        self.meta["disc_bytes"] = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        self._local = threading.local()
        self._fds = {}
        self._fd_lock = threading.Lock()
        self._cache = OrderedDict()
        self._cache_lock = threading.Lock()
        self._stat_lock = threading.Lock()
        self.reads = self.cache_hits = self.bytes_read = 0
        self.events = deque(maxlen=4000)
        self.last_path, self.last_t = "", 0.0

    def _db(self):
        db = getattr(self._local, "db", None)
        if db is None:
            uri = (self.root / "index.db").resolve().as_uri() + "?mode=ro&immutable=1"
            db = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self._local.db = db
        return db

    def _fd(self, pack):
        with self._fd_lock:
            if pack not in self._fds:
                self._fds[pack] = os.open(self.root / "packs" / f"pack-{pack:05d}.bin", os.O_RDONLY)
            return self._fds[pack]

    def lookup(self, path):
        return self._db().execute(
            "SELECT mime, pack, off, clen, codec, ioff, ilen FROM entries WHERE path=?", (path,)
        ).fetchone()

    def redirect(self, path):
        r = self._db().execute("SELECT target FROM redirects WHERE path=?", (path,)).fetchone()
        return r[0] if r else None

    def search(self, q, limit=20):
        key = q.casefold()
        return self._db().execute(
            "SELECT path, title FROM titles WHERE key >= ? AND key < ? ORDER BY length(key) LIMIT ?",
            (key, key + "\uffff", limit)).fetchall()

    @property
    def has_fulltext(self):
        return bool(self.meta.get("fulltext"))

    def fulltext(self, terms, limit=20, offset=0):
        """Best-ranked articles containing every term: (total_capped, [(path, title)])."""
        q = fts_query(terms)
        if not q or not self.has_fulltext:
            return 0, []
        db = self._db()
        phrase = " ".join(terms)
        rows = db.execute(
            "SELECT d.path, d.title FROM (SELECT rowid, bm25(fts, 8.0, 1.0) AS r FROM fts WHERE fts MATCH ?) f "
            "JOIN docs d ON d.id = f.rowid "
            "ORDER BY lower(d.title) = ? DESC, f.rowid IN (SELECT rowid FROM fts WHERE fts MATCH ?) DESC, "
            "f.r LIMIT ? OFFSET ?",
            (q, phrase, "title : (" + q + ")", limit, offset)).fetchall()
        total = db.execute("SELECT count(*) FROM (SELECT rowid FROM fts WHERE fts MATCH ? LIMIT 1000)",
                           (q,)).fetchone()[0]
        return total, rows

    def random_path(self):
        r = self._db().execute(
            "SELECT path FROM titles WHERE rowid >= (abs(random()) % (SELECT max(rowid) FROM titles)) LIMIT 1"
        ).fetchone()
        return r[0] if r else None

    def list_prefix(self, prefix, limit=500):
        return [r[0] for r in self._db().execute(
            "SELECT path FROM entries WHERE path >= ? AND path < ? LIMIT ?",
            (prefix, prefix + "\uffff", limit))]

    def read(self, path, row):
        mime, pack, off, clen, codec, ioff, ilen = row
        key = (pack, off)
        with self._cache_lock:
            blob = self._cache.get(key)
            if blob is not None:
                self._cache.move_to_end(key)
        hit = blob is not None
        if not hit:
            raw = os.pread(self._fd(pack), clen, off)
            blob = _decompress(codec, raw)
            if codec != "raw":
                with self._cache_lock:
                    self._cache[key] = blob
                    while len(self._cache) > 48:
                        self._cache.popitem(last=False)
        now = time.time()
        with self._stat_lock:
            self.reads += 1
            self.last_path, self.last_t = path, now
            if hit:
                self.cache_hits += 1
            else:
                self.bytes_read += clen
                self.events.append((now, clen))
        return mime, blob[ioff:ioff + ilen]

    def stats(self):
        now = time.time()
        with self._stat_lock:
            recent = sum(n for t, n in self.events if now - t <= 1.0)
            return {
                "role": self.role, "label": self.meta.get("label"), "mount": str(self.root),
                "disc_index": self.meta.get("disc_index"), "reads": self.reads,
                "cache_hits": self.cache_hits, "bytes_read": self.bytes_read,
                "throughput_bps": recent, "active": now - self.last_t < 0.35,
                "last_path": self.last_path, "entries": self.meta.get("entries"),
                "disc_bytes": self.meta.get("disc_bytes"),
            }
