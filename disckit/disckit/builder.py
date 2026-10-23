"""Routes every item from a source onto the Text Disc or the Media Disc."""

import threading
import time
import uuid

import sqlite3

from .rules import MEDIA, TEXT, Rules, base_mime
from .textindex import FTS_SCHEMA, html_to_text
from pathlib import Path

from .volume import CLUSTER_TARGET, GB, DiscFullError, VolumeWriter, _compress, check_empty

DISC_SIZES_GB = {"25 GB BD-R": 25, "50 GB BD-R DL": 50, "100 GB M-DISC BDXL": 100, "128 GB BDXL": 128}


class Progress:
    def __init__(self):
        self.lock = threading.Lock()
        self.phase, self.done, self.total = "idle", 0, 0
        self.text_bytes = self.media_bytes = 0
        self.text_items = self.media_items = self.skipped = 0
        self.current = ""
        self.started = time.time()

    def snapshot(self):
        with self.lock:
            el = max(time.time() - self.started, 0.001)
            return {
                "phase": self.phase, "done": self.done, "total": self.total,
                "text_bytes": self.text_bytes, "media_bytes": self.media_bytes,
                "text_items": self.text_items, "media_items": self.media_items,
                "skipped": self.skipped, "current": self.current, "elapsed": el,
                "rate": self.done / el,
            }


FT_MIMES = ("text/html", "text/plain")


def _ft_text(mime, data):
    m = base_mime(mime)
    if m == "text/html":
        return html_to_text(data)
    return bytes(data).decode("utf-8", "replace")


def _fts_ratio(samples):
    """Measure index bytes per raw HTML byte by indexing a real sample in memory."""
    if not samples:
        return 0.0
    db = sqlite3.connect(":memory:")
    db.executescript(FTS_SCHEMA)
    for i, (mime, d) in enumerate(samples):
        db.execute("INSERT INTO fts(rowid, title, body) VALUES (?,?,?)", (i + 1, "", _ft_text(mime, d)))
    db.execute("INSERT INTO fts(fts) VALUES('optimize')")
    db.commit()
    size = db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]
    return size / max(sum(len(d) for _, d in samples), 1)


def plan(source, rules, capacity_gb, sample_limit=400, cancel=None, fulltext=True):
    """Scan the source (without writing) and estimate how full each disc will be."""
    if not source.estimable:
        return {"estimable": False, "note": "Websites are sized as they are crawled; build to see the totals."}
    raw = {TEXT: 0, MEDIA: 0}
    count = {TEXT: 0, MEDIA: 0}
    redirects = skipped = 0
    sample, sample_raw = [], 0
    ft_sample, ft_raw, ft_sample_bytes = [], 0, 0
    for it in source.items():
        if cancel and cancel.is_set():
            break
        if it.redirect_to:
            redirects += 1
            continue
        role = rules.classify(it.mime)
        if role is None:
            skipped += 1
            continue
        raw[role] += it.size
        count[role] += 1
        if role == TEXT and fulltext and base_mime(it.mime) in FT_MIMES:
            ft_raw += it.size
            if len(ft_sample) < 1000 and ft_sample_bytes < 30_000_000 and it.load:
                ft_sample.append((it.mime, it.load()))
                ft_sample_bytes += len(ft_sample[-1][1])
        if role == TEXT and rules.compressible(it.mime) and len(sample) < sample_limit and it.load:
            data = it.load()
            sample.append(data)
            sample_raw += len(data)
    ratio = 1.0
    if sample:
        packed = 0
        chunk, size = [], 0
        for d in sample:
            chunk.append(d)
            size += len(d)
            if size >= CLUSTER_TARGET:
                packed += len(_compress(b"".join(chunk))[1])
                chunk, size = [], 0
        if chunk:
            packed += len(_compress(b"".join(chunk))[1])
        ratio = packed / max(sample_raw, 1)
    index_overhead = (count[TEXT] + count[MEDIA] + redirects) * 120
    fts_bytes = int(ft_raw * _fts_ratio(ft_sample)) if fulltext else 0
    est_text = raw[TEXT] * ratio + index_overhead * 0.7 + fts_bytes
    est_media = raw[MEDIA] + index_overhead * 0.3
    cap = capacity_gb * GB
    return {
        "estimable": True, "capacity_bytes": cap,
        "text": {"items": count[TEXT], "raw_bytes": raw[TEXT], "est_bytes": int(est_text),
                 "fill_pct": est_text / cap * 100, "fits": est_text <= cap * 0.985,
                 "compression_ratio": round(ratio, 3), "fulltext_bytes": fts_bytes},
        "media": {"items": count[MEDIA], "raw_bytes": raw[MEDIA], "est_bytes": int(est_media),
                  "fill_pct": est_media / cap * 100, "fits": est_media <= cap * 0.985},
        "redirects": redirects, "skipped": skipped,
    }


def build(source, text_dir, media_dir, capacity_gb=100, rules=None, label="DISCKIT",
          progress=None, log=print, cancel=None, fulltext=True):
    rules = rules or Rules()
    progress = progress or Progress()
    set_id = uuid.uuid4().hex
    cap = capacity_gb * GB
    title = source.title()
    t_path, m_path = Path(text_dir).expanduser().resolve(), Path(media_dir).expanduser().resolve()
    if t_path == m_path or t_path in m_path.parents or m_path in t_path.parents:
        raise ValueError("The Text Disc and Media Disc need two separate folders.")
    src_root = getattr(source, "root", None)
    if src_root and any(p == src_root or src_root in p.parents for p in (t_path, m_path)):
        raise ValueError("Disc folders can't be inside the source folder.")
    check_empty(t_path)
    check_empty(m_path)
    tw = VolumeWriter(text_dir, TEXT, set_id, f"{label}_TEXT", cap, compress=True, disc_index=1,
                      fulltext=fulltext)
    mw = VolumeWriter(media_dir, MEDIA, set_id, f"{label}_MEDIA", cap, compress=True, disc_index=2)
    with progress.lock:
        progress.phase, progress.total = "building", source.count_hint()
        progress.started = time.time()
    log(f"Building '{title}' -> Text: {text_dir} | Media: {media_dir} ({capacity_gb} GB discs)")
    cancelled = False
    try:
        for it in source.items():
            if cancel and cancel.is_set():
                cancelled = True
                log("Build cancelled.")
                break
            if it.redirect_to:
                tw.add_redirect(it.path, it.redirect_to, it.title)
                with progress.lock:
                    progress.done += 1
                continue
            role = rules.classify(it.mime)
            if role is None:
                with progress.lock:
                    progress.done += 1
                    progress.skipped += 1
                continue
            data = it.load()
            if role == TEXT:
                tw.add(it.path, it.mime, data, it.title, compressible=rules.compressible(it.mime))
                if fulltext and base_mime(it.mime) in FT_MIMES:
                    tw.add_fulltext(it.path, it.title or it.path, _ft_text(it.mime, data))
            else:
                mw.add(it.path, it.mime, data, compressible=rules.compressible(it.mime))
                if it.title:
                    tw.add_title(it.path, it.title)
            with progress.lock:
                progress.done += 1
                progress.current = it.path
                progress.text_bytes, progress.media_bytes = tw.used_bytes, mw.used_bytes
                progress.text_items, progress.media_items = tw.entries, mw.entries
                if progress.done > progress.total:
                    progress.total = progress.done
    except DiscFullError as e:
        log(f"STOPPED: {e}")
        with progress.lock:
            progress.phase = "error"
        raise
    finally:
        source.close()
    with progress.lock:
        progress.phase = "finalizing"
    log("Finalizing indexes and writing SHA256SUMS…")
    meta = {"title": title, "source_kind": source.kind, "main_path": source.main_path(),
            "partial": cancelled}
    tinfo = tw.close(meta)
    minfo = mw.close(meta)
    with progress.lock:
        progress.phase = "done"
        progress.text_bytes, progress.media_bytes = tinfo["disc_bytes"], minfo["disc_bytes"]
    log(f"Done. Text Disc {tinfo['disc_bytes'] / GB:.3f} GB ({tinfo['entries']} items, "
        f"{tinfo['redirects']} redirects) | Media Disc {minfo['disc_bytes'] / GB:.3f} GB "
        f"({minfo['entries']} items)")
    return {"set_id": set_id, "text": tinfo, "media": minfo}


__all__ = ["build", "plan", "Progress", "DISC_SIZES_GB", "base_mime"]
