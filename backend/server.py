import os
import re
import io
import time
import json
import uuid
import html
import hashlib
import zipfile
import asyncio
import logging
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

import requests
import pycdlib
from bs4 import BeautifulSoup, NavigableString
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import Response, HTMLResponse, PlainTextResponse, RedirectResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Offline Wikipedia — Dual M-Disc Archive")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("offline-wiki")

# ----------------------------------------------------------------------------
# Object storage ("Media Disk" backend)
# ----------------------------------------------------------------------------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "offline-wiki"
storage_key: Optional[str] = None
STORAGE_OK = False


def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ----------------------------------------------------------------------------
# Hardware metadata (the real-world build this demo represents)
# ----------------------------------------------------------------------------
DISK_TOTAL_BYTES = 100 * 1000 * 1000 * 1000  # Verbatim 100GB M-DISC
DRIVE_MODEL = "ASUS ZenDrive U9M"
MEDIUM = "Verbatim M-DISC BD-R 100GB"

WIKI_HEADERS = {"User-Agent": "OfflineWikiMDiscDemo/1.0 (offline archive demo)"}
REST = "https://en.wikipedia.org/api/rest_v1"
ACTION = "https://en.wikipedia.org/w/api.php"

SKIP_SECTIONS = {
    "references", "external links", "see also", "notes", "bibliography",
    "further reading", "citations", "sources", "footnotes", "gallery",
}

CURATED_TITLES = [
    "Ancient Rome", "Black hole", "Leonardo da Vinci", "Great Wall of China",
    "Photosynthesis", "Albert Einstein", "Mount Everest", "Apollo 11",
    "Octopus", "Volcano", "Solar System", "William Shakespeare",
    "Great Pyramid of Giza", "Coffee", "Jupiter", "DNA", "Lion", "Internet",
]

seed_state = {"state": "idle", "phase": "", "done": 0, "total": len(CURATED_TITLES), "current": "", "errors": []}
burn_state = {"state": "idle", "step": "", "progress": 0, "total": 0, "error": ""}
EXPORT_DIR = Path("/tmp/offline_wiki_exports")

# "Pick Topics" — theme presets seed a tightly interlinked web around a subject.
THEMES = {
    "space": {"label": "Space & Astronomy", "roots": [
        "Solar System", "Jupiter", "Saturn", "Mars", "Sun", "Moon", "Black hole",
        "Galaxy", "Milky Way", "NASA", "Apollo 11", "Astronomy", "Star", "Planet",
        "Telescope", "Big Bang"]},
    "history": {"label": "History", "roots": [
        "Ancient Rome", "Ancient Greece", "Ancient Egypt", "Roman Empire", "Middle Ages",
        "Renaissance", "World War II", "World War I", "French Revolution", "Napoleon",
        "Byzantine Empire", "Industrial Revolution"]},
    "science": {"label": "Science", "roots": [
        "Physics", "Chemistry", "Biology", "DNA", "Photosynthesis", "Evolution", "Atom",
        "Energy", "Gravity", "Cell (biology)", "Periodic table", "Electricity"]},
    "nature": {"label": "Nature & Animals", "roots": [
        "Lion", "Octopus", "Elephant", "Volcano", "Ocean", "Tiger", "Whale", "Bird",
        "Tree", "Coral reef", "Rainforest", "Insect"]},
    "art_culture": {"label": "Art & Culture", "roots": [
        "Leonardo da Vinci", "William Shakespeare", "Painting", "Music", "Film",
        "Literature", "Vincent van Gogh", "Classical music", "Sculpture", "Theatre"]},
    "technology": {"label": "Technology", "roots": [
        "Internet", "Computer", "Artificial intelligence", "Electricity", "Telephone",
        "Software", "Robotics", "Smartphone", "World Wide Web", "Semiconductor"]},
    "geography": {"label": "Geography", "roots": [
        "Mount Everest", "Great Wall of China", "Great Pyramid of Giza", "Mountain",
        "River", "Continent", "Desert", "Ocean", "Volcano", "Island", "Lake"]},
}


def slugify_title(title: str) -> str:
    return title.strip().replace(" ", "_")


def anchorize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ----------------------------------------------------------------------------
# Wikipedia fetch (blocking — always called via asyncio.to_thread)
# ----------------------------------------------------------------------------
_session = requests.Session()
_session.headers.update(WIKI_HEADERS)


def _wiki_get(url: str, params: dict = None, retries: int = 5):
    delay = 2.0
    last = None
    for attempt in range(retries):
        r = _session.get(url, params=params, timeout=30)
        if r.status_code in (429, 503):
            last = r
            wait = float(r.headers.get("Retry-After", delay))
            time.sleep(min(wait, 20))
            delay *= 2
            continue
        r.raise_for_status()
        return r
    if last is not None:
        last.raise_for_status()
    raise RuntimeError(f"failed to fetch {url}")


def _fetch_summary(title: str) -> dict:
    r = _wiki_get(f"{REST}/page/summary/{requests.utils.quote(title)}")
    return r.json()


def _fetch_extract_html(title: str) -> str:
    params = {
        "action": "query", "prop": "extracts", "titles": title,
        "format": "json", "explaintext": 1, "exsectionformat": "wiki",
        "redirects": 1,
    }
    r = _wiki_get(ACTION, params=params)
    pages = r.json().get("query", {}).get("pages", {})
    for _, page in pages.items():
        return page.get("extract", "") or ""
    return ""


def _fetch_media_urls(title: str, limit: int = 4) -> list:
    try:
        r = _wiki_get(f"{REST}/page/media-list/{requests.utils.quote(title)}")
        items = r.json().get("items", [])
    except Exception:
        return []
    out = []
    for it in items:
        if it.get("type") != "image":
            continue
        srcset = it.get("srcset") or []
        if not srcset:
            continue
        src = srcset[-1].get("src") or srcset[0].get("src")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        cap = ""
        caption = it.get("caption") or {}
        if isinstance(caption, dict):
            cap = (caption.get("text") or "").strip()
        if not cap:
            cap = (it.get("title") or "").replace("File:", "").rsplit(".", 1)[0].replace("_", " ")
        out.append({"url": src, "caption": cap})
        if len(out) >= limit:
            break
    return out


def _download_image(url: str) -> tuple:
    r = _wiki_get(url)
    return r.content, r.headers.get("Content-Type", "image/jpeg")


HEADING_RE = re.compile(r"^(={2,6})\s*(.+?)\s*=+\s*$")


def parse_sections(extract_text: str) -> tuple:
    """Turn plain-text extract (with == wiki headings ==) into lead HTML + sections."""
    lead_parts, sections, current = [], [], None
    para = []

    def container():
        return current["parts"] if current else lead_parts

    def flush_para():
        if para:
            txt = " ".join(para).strip()
            if txt:
                container().append("<p>" + html.escape(txt, quote=False) + "</p>")
            para.clear()

    for raw in extract_text.split("\n"):
        line = raw.strip()
        m = HEADING_RE.match(line)
        if m:
            flush_para()
            level = len(m.group(1))
            title = m.group(2).strip()
            if level == 2:
                skip = title.lower() in SKIP_SECTIONS
                current = {"title": title, "anchor": anchorize(title), "parts": [], "skip": skip}
                sections.append(current)
            else:
                tag = "h3" if level == 3 else "h4"
                container().append(f"<{tag}>{html.escape(title, quote=False)}</{tag}>")
            continue
        if line == "":
            flush_para()
        else:
            para.append(line)
    flush_para()

    good = []
    for s in sections:
        body = "".join(s["parts"]).strip()
        if s["skip"] or "<p>" not in body:
            continue
        good.append({"title": s["title"], "anchor": s["anchor"], "html": body})
    return "".join(lead_parts), good


# ----------------------------------------------------------------------------
# Cross-article linking ("web browsing experience")
# ----------------------------------------------------------------------------
def _linkify(html: str, mapping: dict, self_slug: str) -> str:
    if not html:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for title, slug in mapping.items():
        if slug == self_slug:
            continue
        pattern = re.compile(r"\b" + re.escape(title) + r"\b")
        replaced = False
        for node in list(soup.find_all(string=True)):
            if replaced:
                break
            if node.parent.name == "a":
                continue
            m = pattern.search(str(node))
            if not m:
                continue
            before, after = str(node)[:m.start()], str(node)[m.end():]
            a = soup.new_tag("a", **{"data-wikilink": slug, "class": "wikilink"})
            a.string = title
            node.replace_with(NavigableString(before), a, NavigableString(after))
            replaced = True
    return str(soup)


# ----------------------------------------------------------------------------
# Seeding
# ----------------------------------------------------------------------------
async def _store_media(article_slug: str, url: str, caption: str, is_lead: bool) -> Optional[dict]:
    try:
        data, content_type = await asyncio.to_thread(_download_image, url)
    except Exception as e:
        logger.warning(f"media download failed {url}: {e}")
        return None
    media_id = str(uuid.uuid4())
    ext = (content_type.split("/")[-1] or "jpg").split(";")[0]
    backend, storage_path = "inline", None
    if STORAGE_OK:
        try:
            path = f"{APP_NAME}/media/{article_slug}/{media_id}.{ext}"
            result = await asyncio.to_thread(put_object, path, data, content_type)
            backend, storage_path = "objstore", result["path"]
        except Exception as e:
            logger.warning(f"objstore put failed, inlining: {e}")
    doc = {
        "id": media_id, "article_slug": article_slug, "caption": caption,
        "is_lead": is_lead, "content_type": content_type, "size_bytes": len(data),
        "storage_backend": backend, "storage_path": storage_path,
        "inline_bytes": data if backend == "inline" else None,
        "source_url": url, "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.media_disk.insert_one(doc)
    return {"id": media_id, "caption": caption, "is_lead": is_lead, "size_bytes": len(data)}


async def _seed_one(title: str) -> dict:
    slug = slugify_title(title)
    summary = await asyncio.to_thread(_fetch_summary, title)
    real_title = summary.get("title", title)
    slug = slugify_title(real_title)
    extract_html = await asyncio.to_thread(_fetch_extract_html, real_title)
    lead_html, sections = parse_sections(extract_html)

    await db.media_disk.delete_many({"article_slug": slug})
    media_refs = []
    thumb = (summary.get("thumbnail") or {}).get("source") or (summary.get("originalimage") or {}).get("source")
    lead_desc = summary.get("description", "")
    if thumb:
        ref = await _store_media(slug, thumb, real_title, True)
        if ref:
            media_refs.append(ref)
    for m in await asyncio.to_thread(_fetch_media_urls, real_title, 2):
        ref = await _store_media(slug, m["url"], m["caption"], False)
        if ref:
            media_refs.append(ref)

    return {
        "slug": slug, "title": real_title, "description": lead_desc,
        "lead_html_raw": lead_html, "sections_raw": sections, "media": media_refs,
    }


def _strip_links(h: str) -> str:
    return re.sub(r"<a[^>]*>(.*?)</a>", r"\1", h or "", flags=re.S)


async def _relinkify_all():
    """Rebuild cross-article links across the whole corpus from raw text."""
    docs = await db.text_disk.find(
        {}, {"_id": 0, "slug": 1, "title": 1, "lead_html_raw": 1, "sections_raw": 1,
             "lead_html": 1, "sections": 1}
    ).to_list(None)
    mapping = {d["title"]: d["slug"] for d in docs}
    for d in docs:
        raw_lead = d.get("lead_html_raw")
        if raw_lead is None:
            raw_lead = _strip_links(d.get("lead_html", ""))
        raw_secs = d.get("sections_raw")
        if raw_secs is None:
            raw_secs = [{"title": s["title"], "anchor": s["anchor"],
                         "html": _strip_links(s["html"])} for s in d.get("sections", [])]
        lead = _linkify(raw_lead, mapping, d["slug"])
        secs = [{"title": s["title"], "anchor": s["anchor"],
                 "html": _linkify(s["html"], mapping, d["slug"])} for s in raw_secs]
        size = len(raw_lead) + sum(len(s["html"]) for s in raw_secs)
        await db.text_disk.update_one(
            {"slug": d["slug"]},
            {"$set": {"lead_html_raw": raw_lead, "sections_raw": raw_secs,
                      "lead_html": lead, "sections": secs, "size_bytes": size}},
        )


async def _seed_titles(titles: list):
    for title in titles:
        seed_state["current"] = title
        try:
            if await db.text_disk.find_one({"slug": slugify_title(title)}, {"_id": 1}):
                seed_state["done"] += 1
                continue
            payload = await _seed_one(title)
            doc = {"id": str(uuid.uuid4()), **payload,
                   "lead_html": payload["lead_html_raw"],
                   "sections": payload["sections_raw"],
                   "size_bytes": len(payload["lead_html_raw"]) + sum(len(s["html"]) for s in payload["sections_raw"]),
                   "created_at": datetime.now(timezone.utc).isoformat()}
            await db.text_disk.replace_one({"slug": payload["slug"]}, doc, upsert=True)
        except Exception as e:
            logger.error(f"seed failed {title}: {e}")
            seed_state["errors"].append(f"{title}: {str(e)[:120]}")
        seed_state["done"] += 1
        await asyncio.sleep(0.9)
    seed_state["current"] = "linking articles together"
    await _relinkify_all()


async def _run_seed():
    global seed_state
    seed_state = {"state": "running", "phase": "seeding", "done": 0,
                  "total": len(CURATED_TITLES), "current": "", "errors": []}
    await _seed_titles(CURATED_TITLES)
    seed_state["state"] = "done"
    seed_state["current"] = ""
    logger.info("seed complete")


# ----------------------------------------------------------------------------
# Archive expansion — crawl the Wikipedia link graph for an interlinked corpus
# ----------------------------------------------------------------------------
def _fetch_links(title: str) -> list:
    out = []
    params = {"action": "query", "prop": "links", "titles": title,
              "plnamespace": 0, "pllimit": "max", "format": "json", "redirects": 1}
    try:
        data = _wiki_get(ACTION, params=params).json()
        for p in data.get("query", {}).get("pages", {}).values():
            for lk in p.get("links", []):
                out.append(lk["title"])
    except Exception:
        pass
    return out


def _valid_candidate(title: str) -> bool:
    low = title.lower()
    if ":" in title or "(identifier)" in low or "(disambiguation)" in low:
        return False
    if low.startswith(("list of", "index of", "outline of", "timeline of", "history of")):
        return False
    return 1 < len(title) <= 80


async def _discover_titles(roots: list, target: int, existing_slugs: set) -> list:
    counter = Counter()
    for root in roots[:40]:
        seed_state["current"] = f"mapping links · {root}"
        for t in await asyncio.to_thread(_fetch_links, root):
            if _valid_candidate(t) and slugify_title(t) not in existing_slugs:
                counter[t] += 1
        await asyncio.sleep(0.35)
    needed = max(target - len(existing_slugs), 0)
    return [t for t, _ in counter.most_common()][:needed]


async def _run_expand(target: int, theme: Optional[str] = None):
    global seed_state
    seed_state = {"state": "running", "phase": "discovering", "done": 0,
                  "total": 0, "current": "", "errors": [], "theme": theme or ""}
    docs = await db.text_disk.find({}, {"_id": 0, "title": 1, "slug": 1}).to_list(None)
    existing = {d["slug"] for d in docs}

    theme_roots = THEMES.get(theme, {}).get("roots") if theme else None
    if theme_roots:
        roots = theme_roots
        base = [t for t in theme_roots if slugify_title(t) not in existing]
    else:
        roots = [d["title"] for d in docs] or CURATED_TITLES
        base = []

    candidates = await _discover_titles(roots, target, existing)
    titles = list(base)
    for t in candidates:
        if slugify_title(t) not in existing and t not in titles:
            titles.append(t)
    needed = max(target - len(existing), 0)
    titles = titles[:needed]

    seed_state["phase"] = "seeding"
    seed_state["total"] = len(titles)
    await _seed_titles(titles)
    seed_state["state"] = "done"
    seed_state["current"] = ""
    logger.info(f"expand complete (+{len(titles)} targeted, goal {target}, theme {theme})")


# ----------------------------------------------------------------------------
# Burn to Disc — build real ISO 9660 disc images for the two M-Discs
# ----------------------------------------------------------------------------
DISC_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#202122;
background:#fff;margin:0;line-height:1.7}
.wrap{max-width:900px;margin:0 auto;padding:24px}
h1{font-family:Georgia,'Times New Roman',serif;font-size:2.2rem;border-bottom:1px solid #a2a9b1;padding-bottom:6px}
h2{font-family:Georgia,serif;font-size:1.5rem;border-bottom:1px solid #eaecf0;padding-bottom:4px;margin-top:1.6em}
h3{font-family:Georgia,serif}
a{color:#3366cc;text-decoration:none}a:hover{text-decoration:underline}
.desc{color:#54595d;font-style:italic;margin-top:-4px}
.back{font-size:.9rem}
.infobox{float:right;width:300px;background:#f8f9fa;border:1px solid #a2a9b1;padding:6px;margin:0 0 16px 20px}
.infobox img{width:100%;height:auto}
.thumb{float:right;width:240px;background:#f8f9fa;border:1px solid #c8ccd1;padding:4px;margin:0 0 12px 18px}
.thumb img{width:100%;height:auto}
figcaption{font-size:.8rem;color:#54595d;padding:4px}
.toc{display:inline-block;background:#f8f9fa;border:1px solid #c8ccd1;padding:10px 16px;margin:12px 0}
.toc ol{margin:6px 0 0 18px}
footer{margin-top:40px;padding-top:12px;border-top:1px solid #eaecf0;color:#72777d;font-size:.85rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin-top:16px}
.card{display:flex;gap:10px;align-items:center;border:1px solid #eaecf0;padding:8px}
.card:hover{background:#f8f9fa;border-color:#a2a9b1}
.card img{width:52px;height:52px;object-fit:cover;border:1px solid #c8ccd1}
.card span{font-family:Georgia,serif}
.badge{display:inline-block;background:#eaecf0;border:1px solid #a2a9b1;padding:2px 8px;font-size:.8rem;margin-bottom:12px}
""".strip()

TEXT_README = (
    "OFFLINE WIKIPEDIA — TEXT DISC (Drive 0)\n"
    "=======================================\n\n"
    "This M-Disc holds the article TEXT of an offline Wikipedia archive.\n"
    "Open index.html in any web browser to start browsing. Articles link to\n"
    "each other, recreating the Wikipedia web experience with no internet.\n\n"
    "Images live on the companion MEDIA DISC (Drive 1). Pages reference images\n"
    "at ../media/<id>. To view images, mount the Media Disc and copy or link its\n"
    "'media' folder next to this disc's content, or browse both from a single\n"
    "combined copy.\n\n"
    "Hardware: written to Verbatim M-DISC 100GB via ASUS ZenDrive U9M.\n"
)
MEDIA_README = (
    "OFFLINE WIKIPEDIA — MEDIA DISC (Drive 1)\n"
    "========================================\n\n"
    "This M-Disc holds the IMAGES for the offline Wikipedia archive. Each file in\n"
    "the 'media' folder is referenced by the article pages on the TEXT DISC.\n"
    "See manifest.json for the id -> article mapping.\n\n"
    "Hardware: written to Verbatim M-DISC 100GB via ASUS ZenDrive U9M.\n"
)

MEDIA_EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
             "image/gif": "gif", "image/webp": "webp", "image/svg+xml": "svg"}


def _media_ext(ct: str) -> str:
    ct = (ct or "").split(";")[0].strip().lower()
    return MEDIA_EXT.get(ct, (ct.split("/")[-1] or "img"))


def _fix_links(h: str) -> str:
    return re.sub(r'data-wikilink="([^"]+)"', r'href="\1.html"', h or "")


def _article_html(doc: dict, ext_map: dict) -> str:
    media = doc.get("media", [])
    lead = next((m for m in media if m.get("is_lead")), None)
    inline = [m for m in media if not m.get("is_lead")]
    p = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f'<title>{html.escape(doc["title"])} — Offline Wikipedia</title>',
         '<link rel="stylesheet" href="../assets/style.css"></head><body><div class="wrap">',
         '<p class="back"><a href="../index.html">&larr; Offline Wikipedia</a></p>',
         f'<h1>{html.escape(doc["title"])}</h1>']
    if doc.get("description"):
        p.append(f'<p class="desc">{html.escape(doc["description"])}</p>')
    if lead:
        ext = ext_map.get(lead["id"], "jpg")
        p.append(f'<figure class="infobox"><img src="../media/{lead["id"]}.{ext}" alt="">'
                 f'<figcaption>{html.escape(lead.get("caption",""))}</figcaption></figure>')
    if doc.get("sections"):
        p.append('<nav class="toc"><b>Contents</b><ol>')
        for s in doc["sections"]:
            p.append(f'<li><a href="#{s["anchor"]}">{html.escape(s["title"])}</a></li>')
        p.append('</ol></nav>')
    p.append('<div class="body">')
    p.append(_fix_links(doc.get("lead_html", "")))
    for i, s in enumerate(doc.get("sections", [])):
        p.append(f'<h2 id="{s["anchor"]}">{html.escape(s["title"])}</h2>')
        if i < len(inline):
            m = inline[i]
            ext = ext_map.get(m["id"], "jpg")
            p.append(f'<figure class="thumb"><img src="../media/{m["id"]}.{ext}" alt="">'
                     f'<figcaption>{html.escape(m.get("caption",""))}</figcaption></figure>')
        p.append(_fix_links(s.get("html", "")))
    p.append('</div><footer>Retrieved offline from the Text Disc (Drive 0) and Media Disc '
             '(Drive 1). Content from Wikipedia, the free encyclopedia.</footer></div></body></html>')
    return "".join(p)


def _index_html(docs: list, ext_map: dict) -> str:
    cards = []
    for d in sorted(docs, key=lambda x: x["title"].lower()):
        lead = next((m for m in d.get("media", []) if m.get("is_lead")), None)
        img = (f'<img src="media/{lead["id"]}.{ext_map.get(lead["id"],"jpg")}" alt="">'
               if lead else "")
        cards.append(f'<a class="card" href="articles/{d["slug"]}.html">{img}'
                     f'<span>{html.escape(d["title"])}</span></a>')
    return ("".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Offline Wikipedia</title>',
        '<link rel="stylesheet" href="assets/style.css"></head><body><div class="wrap">',
        '<span class="badge">OFFLINE · SERVED FROM M-DISC</span>',
        '<h1>Offline Wikipedia</h1>',
        f'<p class="desc">The free encyclopedia, archived to disc — {len(docs)} articles. '
        'No internet required.</p>',
        '<div class="grid">', "".join(cards), '</div></div></body></html>',
    ]))


def make_iso(vol_ident: str, files: list) -> bytes:
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", vol_ident=vol_ident[:16])
    dir_map = {"": ""}
    dcount = [0]
    fcount = [0]

    def ensure_dir(real_dir: str) -> str:
        if real_dir in dir_map:
            return dir_map[real_dir]
        parent, _, name = real_dir.rpartition("/")
        parent_iso = ensure_dir(parent)
        dcount[0] += 1
        iso_path = f"{parent_iso}/D{dcount[0]:04d}"
        iso.add_directory(iso_path, rr_name=name, joliet_path="/" + real_dir)
        dir_map[real_dir] = iso_path
        return iso_path

    for f in files:
        path = f["path"].strip("/")
        rdir, _, fname = path.rpartition("/")
        parent_iso = ensure_dir(rdir) if rdir else ""
        fcount[0] += 1
        ext = fname.rsplit(".", 1)[-1] if "." in fname else "dat"
        ext3 = re.sub(r"[^A-Z0-9]", "", ext.upper())[:3] or "DAT"
        iso_file = f"{parent_iso}/F{fcount[0]:05d}.{ext3};1"
        data = f["data"]
        iso.add_fp(io.BytesIO(data), len(data), iso_file, rr_name=fname, joliet_path="/" + path)

    buf = io.BytesIO()
    iso.write_fp(buf)
    iso.close()
    return buf.getvalue()


async def _read_media_bytes(m: dict) -> Optional[bytes]:
    if m.get("storage_backend") == "objstore" and m.get("storage_path"):
        try:
            data, _ = await asyncio.to_thread(get_object, m["storage_path"])
            return data
        except Exception as e:
            logger.warning(f"media read for burn failed: {e}")
            return None
    return m.get("inline_bytes")


async def _store_export(name: str, data: bytes) -> dict:
    if STORAGE_OK:
        try:
            path = f"{APP_NAME}/exports/{name}"
            result = await asyncio.to_thread(put_object, path, data, "application/x-iso9660-image")
            return {"backend": "objstore", "location": result["path"], "size": len(data)}
        except Exception as e:
            logger.warning(f"export objstore put failed, writing local: {e}")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    fp = EXPORT_DIR / name
    await asyncio.to_thread(fp.write_bytes, data)
    return {"backend": "local", "location": str(fp), "size": len(data)}


async def _run_burn():
    global burn_state
    burn_state = {"state": "running", "step": "loading archive", "progress": 0, "total": 0, "error": ""}
    try:
        docs = await db.text_disk.find({}, {"_id": 0}).to_list(None)
        medias = await db.media_disk.find({"is_deleted": False}, {"_id": 0}).to_list(None)
        if not docs:
            raise RuntimeError("archive is empty — seed articles first")
        ext_map = {m["id"]: _media_ext(m.get("content_type")) for m in medias}
        burn_state["total"] = len(medias)

        burn_state["step"] = "writing text pages"
        text_files = [
            {"path": "index.html", "data": _index_html(docs, ext_map).encode("utf-8")},
            {"path": "assets/style.css", "data": DISC_CSS.encode("utf-8")},
            {"path": "README.txt", "data": TEXT_README.encode("utf-8")},
        ]
        for d in docs:
            text_files.append({"path": f'articles/{d["slug"]}.html',
                               "data": _article_html(d, ext_map).encode("utf-8")})
            jd = {k: d.get(k) for k in ("slug", "title", "description", "lead_html", "sections")}
            text_files.append({"path": f'data/{d["slug"]}.json',
                               "data": json.dumps(jd, ensure_ascii=False).encode("utf-8")})

        burn_state["step"] = "building TEXT DISC image"
        text_iso = await asyncio.to_thread(make_iso, "OWIKI_TEXT", text_files)

        burn_state["step"] = "reading Media Disk"
        media_files = []
        manifest = []
        for i, m in enumerate(medias):
            data = await _read_media_bytes(m)
            burn_state["progress"] = i + 1
            if data is None:
                continue
            fn = f'media/{m["id"]}.{ext_map[m["id"]]}'
            media_files.append({"path": fn, "data": data})
            manifest.append({"id": m["id"], "article": m.get("article_slug"),
                             "caption": m.get("caption"), "file": fn})
        img_count = len(media_files)
        media_files.append({"path": "manifest.json",
                            "data": json.dumps(manifest, ensure_ascii=False).encode("utf-8")})
        media_files.append({"path": "README.txt", "data": MEDIA_README.encode("utf-8")})

        burn_state["step"] = "building MEDIA DISC image"
        media_iso = await asyncio.to_thread(make_iso, "OWIKI_MEDIA", media_files)

        burn_state["step"] = "finalizing"
        text_sha = hashlib.sha256(text_iso).hexdigest()
        media_sha = hashlib.sha256(media_iso).hexdigest()
        text_entry = await _store_export("offline-wiki-text.iso", text_iso)
        media_entry = await _store_export("offline-wiki-media.iso", media_iso)
        rec = {
            "id": "latest", "created_at": datetime.now(timezone.utc).isoformat(),
            "text": {**text_entry, "article_count": len(docs), "sha256": text_sha,
                     "filename": "offline-wiki-text.iso"},
            "media": {**media_entry, "image_count": img_count, "sha256": media_sha,
                      "filename": "offline-wiki-media.iso"},
        }
        await db.exports.replace_one({"id": "latest"}, rec, upsert=True)
        burn_state = {"state": "done", "step": "done", "progress": len(medias),
                      "total": len(medias), "error": "",
                      "text_size": len(text_iso), "media_size": len(media_iso)}
        logger.info("burn complete")
    except Exception as e:
        logger.exception("burn failed")
        burn_state = {"state": "error", "step": "", "progress": 0, "total": 0, "error": str(e)[:200]}


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@api_router.get("/")
async def root():
    return {"message": "Offline Wikipedia dual M-Disc archive", "drive": DRIVE_MODEL}


@api_router.post("/seed")
async def seed(force: bool = False):
    if seed_state["state"] == "running":
        return {"state": "running", "detail": "seed already in progress"}
    count = await db.text_disk.count_documents({})
    if count > 0 and not force:
        return {"state": "exists", "articles": count}
    if force:
        await db.text_disk.delete_many({})
        await db.media_disk.delete_many({})
    asyncio.create_task(_run_seed())
    return {"state": "started", "total": len(CURATED_TITLES)}


@api_router.get("/seed/themes")
async def seed_themes():
    return [{"key": k, "label": v["label"]} for k, v in THEMES.items()]


@api_router.post("/seed/expand")
async def seed_expand(target: int = 150, theme: Optional[str] = None):
    if seed_state["state"] == "running":
        return {"state": "running", "detail": "an archive operation is already in progress"}
    if theme and theme not in THEMES:
        raise HTTPException(status_code=400, detail="unknown theme")
    target = max(20, min(target, 600))
    asyncio.create_task(_run_expand(target, theme))
    return {"state": "started", "target": target, "theme": theme}


async def _effective_seed_state() -> dict:
    if seed_state["state"] == "running":
        return seed_state
    count = await db.text_disk.count_documents({})
    if count >= len(CURATED_TITLES):
        st = dict(seed_state)
        st.update({"state": "done", "done": st.get("total", count), "current": ""})
        if st.get("total", 0) < count:
            st["total"] = count
        return st
    return seed_state


@api_router.get("/seed/status")
async def seed_status():
    return await _effective_seed_state()


@api_router.post("/burn")
async def burn_start():
    if burn_state["state"] == "running":
        return {"state": "running", "detail": "disc images are already being built"}
    asyncio.create_task(_run_burn())
    return {"state": "started"}


@api_router.get("/burn/status")
async def burn_status():
    rec = await db.exports.find_one({"id": "latest"}, {"_id": 0})
    return {"burn": burn_state, "export": rec}


@api_router.get("/burn/download/{which}")
async def burn_download(which: str):
    if which not in ("text", "media"):
        raise HTTPException(status_code=404, detail="unknown disc")
    rec = await db.exports.find_one({"id": "latest"}, {"_id": 0})
    if not rec or which not in rec:
        raise HTTPException(status_code=404, detail="no disc image built yet")
    entry = rec[which]
    if entry.get("backend") == "objstore":
        data, _ = await asyncio.to_thread(get_object, entry["location"])
    else:
        fp = Path(entry["location"])
        if not fp.exists():
            raise HTTPException(status_code=404, detail="disc image missing; rebuild it")
        data = await asyncio.to_thread(fp.read_bytes)
    return Response(
        content=data, media_type="application/x-iso9660-image",
        headers={"Content-Disposition": f'attachment; filename="offline-wiki-{which}.iso"'},
    )


@api_router.get("/burn/checksums")
async def burn_checksums():
    rec = await db.exports.find_one({"id": "latest"}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="no disc images built yet")
    lines = [
        "# Offline Wikipedia — disc image checksums (SHA-256)",
        f"# built {rec.get('created_at', '')}",
        "#",
        "# Verify after writing with:  sha256sum -c SHA256SUMS",
        "",
        f"{rec['text'].get('sha256', '')}  {rec['text'].get('filename', 'offline-wiki-text.iso')}",
        f"{rec['media'].get('sha256', '')}  {rec['media'].get('filename', 'offline-wiki-media.iso')}",
        "",
    ]
    return PlainTextResponse(
        "\n".join(lines),
        headers={"Content-Disposition": 'attachment; filename="SHA256SUMS"'},
    )


KIT_DIR = ROOT_DIR.parent / "disckit"
KIT_SUFFIXES = {".py", ".html", ".md", ".txt", ".command", ".sh", ".png"}


def _kit_files():
    return sorted(
        p for p in KIT_DIR.rglob("*")
        if p.is_file() and p.suffix in KIT_SUFFIXES and not p.name.startswith(".")
        and "__pycache__" not in p.parts and ".venv" not in p.parts
    )


@api_router.get("/kit/info")
async def kit_info():
    version = re.search(r'__version__ = "([^"]+)"', (KIT_DIR / "disckit" / "__init__.py").read_text()).group(1)
    files = _kit_files()
    return {
        "version": version,
        "platform": "macOS",
        "file_count": len(files),
        "size_bytes": sum(p.stat().st_size for p in files),
        "sources": ["zim", "folder", "website"],
        "features": ["fulltext_search", "dual_drive_reader", "parallel_burn"],
        "app": {"arch": "arm64", "signed": False, "dmg_url": os.environ.get("DISCKIT_DMG_URL"),
                "workflow": ".github/workflows/disckit-macos.yml"},
    }


@api_router.get("/kit/download")
async def kit_download():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in _kit_files():
            info = zipfile.ZipInfo(f"DiscKit/{p.relative_to(KIT_DIR).as_posix()}", time.localtime(p.stat().st_mtime)[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if p.suffix in (".command", ".sh") else 0o644
            info.external_attr = (0o100000 | mode) << 16
            zf.writestr(info, p.read_bytes())
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="DiscKit-macOS.zip"'},
    )



@api_router.get("/articles")
async def list_articles():
    docs = await db.text_disk.find(
        {}, {"_id": 0, "slug": 1, "title": 1, "description": 1, "media": 1, "size_bytes": 1}
    ).sort("title", 1).to_list(500)
    out = []
    for d in docs:
        lead = next((m for m in d.get("media", []) if m.get("is_lead")), None)
        out.append({
            "slug": d["slug"], "title": d["title"],
            "description": d.get("description", ""),
            "lead_media_id": lead["id"] if lead else None,
            "size_bytes": d.get("size_bytes", 0),
        })
    return out


@api_router.get("/search")
async def search(q: str = ""):
    q = q.strip()
    if not q:
        return []
    docs = await db.text_disk.find(
        {"title": {"$regex": re.escape(q), "$options": "i"}},
        {"_id": 0, "slug": 1, "title": 1, "description": 1},
    ).limit(8).to_list(8)
    return docs


@api_router.get("/articles/{slug}")
async def get_article(slug: str):
    doc = await db.text_disk.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Article not found on Text Disk")
    toc = [{"anchor": s["anchor"], "title": s["title"]} for s in doc.get("sections", [])]
    doc["toc"] = toc
    return doc


@api_router.get("/media/{media_id}")
async def get_media(media_id: str):
    doc = await db.media_disk.find_one({"id": media_id, "is_deleted": False})
    if not doc:
        raise HTTPException(status_code=404, detail="Media not found on Media Disk")
    content_type = doc.get("content_type", "image/jpeg")
    if doc.get("storage_backend") == "objstore" and doc.get("storage_path"):
        try:
            data, ct = await asyncio.to_thread(get_object, doc["storage_path"])
            content_type = doc.get("content_type") or ct
        except Exception as e:
            logger.error(f"objstore get failed: {e}")
            raise HTTPException(status_code=502, detail="Media Disk read error")
    else:
        data = doc.get("inline_bytes")
        if not data:
            raise HTTPException(status_code=404, detail="Media payload missing")
    return Response(content=data, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"})


async def _load_corpus():
    docs = await db.text_disk.find({}, {"_id": 0}).to_list(None)
    medias = await db.media_disk.find(
        {"is_deleted": False}, {"_id": 0, "id": 1, "content_type": 1}
    ).to_list(None)
    ext_map = {m["id"]: _media_ext(m.get("content_type")) for m in medias}
    return docs, ext_map


# Combined Preview — serves the generated Text Disc + Media Disc together so the
# offline site can be test-browsed before burning. Relative links resolve under /api/preview.
@api_router.get("/preview", include_in_schema=False)
async def preview_root_noslash():
    return RedirectResponse(url="preview/index.html")


@api_router.get("/preview/", include_in_schema=False)
async def preview_root():
    return RedirectResponse(url="index.html")


@api_router.get("/preview/index.html", response_class=HTMLResponse)
async def preview_index():
    docs, ext_map = await _load_corpus()
    return HTMLResponse(_index_html(docs, ext_map))


@api_router.get("/preview/assets/style.css")
async def preview_css():
    return Response(DISC_CSS, media_type="text/css")


@api_router.get("/preview/articles/{slug}", response_class=HTMLResponse)
async def preview_article(slug: str):
    if slug.endswith(".html"):
        slug = slug[:-5]
    doc = await db.text_disk.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="article not on disc")
    _, ext_map = await _load_corpus()
    return HTMLResponse(_article_html(doc, ext_map))


@api_router.get("/preview/media/{fname}")
async def preview_media(fname: str):
    media_id = fname.rsplit(".", 1)[0]
    return await get_media(media_id)


@api_router.get("/disks/status")
async def disks_status():
    text_count = await db.text_disk.count_documents({})
    media_count = await db.media_disk.count_documents({"is_deleted": False})
    text_used = 0
    async for d in db.text_disk.find({}, {"_id": 0, "size_bytes": 1}):
        text_used += d.get("size_bytes", 0)
    media_used = 0
    largest_media = 0
    async for d in db.media_disk.find({"is_deleted": False}, {"_id": 0, "size_bytes": 1}):
        sz = d.get("size_bytes", 0)
        media_used += sz
        largest_media = max(largest_media, sz)

    def _plan(used, count, total):
        avg = (used / count) if count else 0
        est_capacity = int(total / avg) if avg else 0
        return {
            "avg_item_bytes": int(avg),
            "est_items_per_disc": est_capacity,
            "headroom_items": max(est_capacity - count, 0),
            "fill_pct": round((used / total) * 100, 4),
            "over_capacity": used > total,
        }

    capacity = {
        "disc_bytes": DISK_TOTAL_BYTES,
        "text": _plan(text_used, text_count, DISK_TOTAL_BYTES),
        "media": _plan(media_used, media_count, DISK_TOTAL_BYTES),
        "largest_media_bytes": largest_media,
        "largest_media_over_disc": largest_media > DISK_TOTAL_BYTES,
    }
    return {
        "hardware": {"drive_model": DRIVE_MODEL, "medium": MEDIUM, "drive_count": 2},
        "text_disk": {
            "label": "TEXT DISK", "slot": "DRIVE 0", "drive": DRIVE_MODEL, "medium": MEDIUM,
            "total_bytes": DISK_TOTAL_BYTES, "used_bytes": text_used,
            "article_count": text_count, "status": "READY" if text_count else "EMPTY",
        },
        "media_disk": {
            "label": "MEDIA DISK", "slot": "DRIVE 1", "drive": DRIVE_MODEL, "medium": MEDIUM,
            "total_bytes": DISK_TOTAL_BYTES, "used_bytes": media_used,
            "image_count": media_count, "status": "READY" if media_count else "EMPTY",
        },
        "capacity": capacity,
        "seed": await _effective_seed_state(),
    }


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    global STORAGE_OK
    try:
        init_storage()
        STORAGE_OK = True
        logger.info("Media Disk (object storage) initialized")
    except Exception as e:
        STORAGE_OK = False
        logger.error(f"Object storage init failed, images will inline to Mongo: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
