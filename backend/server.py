import os
import re
import time
import uuid
import html
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup, NavigableString
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import Response
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

seed_state = {"state": "idle", "done": 0, "total": len(CURATED_TITLES), "current": "", "errors": []}


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
    for m in await asyncio.to_thread(_fetch_media_urls, real_title, 4):
        ref = await _store_media(slug, m["url"], m["caption"], False)
        if ref:
            media_refs.append(ref)

    text_payload = {
        "slug": slug, "title": real_title,
        "description": lead_desc,
        "lead_html": lead_html,
        "sections": sections,
        "media": media_refs,
    }
    size_bytes = len(lead_html) + sum(len(s["html"]) for s in sections)
    return {"payload": text_payload, "size_bytes": size_bytes, "slug": slug, "title": real_title}


async def _run_seed():
    global seed_state
    seed_state = {"state": "running", "done": 0, "total": len(CURATED_TITLES), "current": "", "errors": []}
    raw = []
    for title in CURATED_TITLES:
        seed_state["current"] = title
        try:
            raw.append(await _seed_one(title))
        except Exception as e:
            logger.error(f"seed failed {title}: {e}")
            seed_state["errors"].append(f"{title}: {e}")
        seed_state["done"] += 1
        await asyncio.sleep(1.2)

    mapping = {r["title"]: r["slug"] for r in raw}
    for r in raw:
        p = r["payload"]
        p["lead_html"] = _linkify(p["lead_html"], mapping, p["slug"])
        for s in p["sections"]:
            s["html"] = _linkify(s["html"], mapping, p["slug"])
        size = len(p["lead_html"]) + sum(len(s["html"]) for s in p["sections"])
        doc = {
            "id": str(uuid.uuid4()), **p, "size_bytes": size,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.text_disk.replace_one({"slug": p["slug"]}, doc, upsert=True)

    seed_state["state"] = "done"
    seed_state["current"] = ""
    logger.info("seed complete")


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


@api_router.get("/seed/status")
async def seed_status():
    return seed_state


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


@api_router.get("/disks/status")
async def disks_status():
    text_count = await db.text_disk.count_documents({})
    media_count = await db.media_disk.count_documents({"is_deleted": False})
    text_used = 0
    async for d in db.text_disk.find({}, {"_id": 0, "size_bytes": 1}):
        text_used += d.get("size_bytes", 0)
    media_used = 0
    async for d in db.media_disk.find({"is_deleted": False}, {"_id": 0, "size_bytes": 1}):
        media_used += d.get("size_bytes", 0)
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
        "seed": seed_state,
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
