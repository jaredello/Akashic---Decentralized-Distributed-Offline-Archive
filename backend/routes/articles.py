"""Reading the archive: article list, search, single article, images and the disc-status panel."""

import asyncio
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

import archive_builder
import media_storage
from config import DISC_CAPACITY_BYTES, DISC_MEDIUM, DRIVE_MODEL, db, logger

router = APIRouter()


@router.get("/")
async def root():
    return {"message": "Offline Wikipedia dual M-Disc archive", "drive": DRIVE_MODEL}


@router.get("/articles")
async def list_articles():
    docs = await db.text_disk.find(
        {}, {"_id": 0, "slug": 1, "title": 1, "description": 1, "media": 1, "size_bytes": 1}
    ).sort("title", 1).to_list(500)
    articles = []
    for d in docs:
        lead = next((m for m in d.get("media", []) if m.get("is_lead")), None)
        articles.append({"slug": d["slug"], "title": d["title"], "description": d.get("description", ""),
                         "lead_media_id": lead["id"] if lead else None, "size_bytes": d.get("size_bytes", 0)})
    return articles


@router.get("/search")
async def search(q: str = ""):
    q = q.strip()
    if not q:
        return []
    return await db.text_disk.find(
        {"title": {"$regex": re.escape(q), "$options": "i"}},
        {"_id": 0, "slug": 1, "title": 1, "description": 1},
    ).limit(8).to_list(8)


@router.get("/articles/{slug}")
async def get_article(slug: str):
    doc = await db.text_disk.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Article not found on Text Disk")
    doc["toc"] = [{"anchor": s["anchor"], "title": s["title"]} for s in doc.get("sections", [])]
    return doc


@router.get("/media/{media_id}")
async def get_media(media_id: str):
    doc = await db.media_disk.find_one({"id": media_id, "is_deleted": False})
    if not doc:
        raise HTTPException(status_code=404, detail="Media not found on Media Disk")
    content_type = doc.get("content_type", "image/jpeg")
    if doc.get("storage_backend") == "objstore" and doc.get("storage_path"):
        try:
            data, stored_type = await asyncio.to_thread(media_storage.load_file, doc["storage_path"])
            content_type = doc.get("content_type") or stored_type
        except Exception as e:
            logger.error(f"objstore get failed: {e}")
            raise HTTPException(status_code=502, detail="Media Disk read error")
    else:
        data = doc.get("inline_bytes")
        if not data:
            raise HTTPException(status_code=404, detail="Media payload missing")
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})


def _capacity_plan(used, count, total):
    """How full a disc is, and roughly how many more items of the same average size would fit."""
    avg = (used / count) if count else 0
    fits = int(total / avg) if avg else 0
    return {"avg_item_bytes": int(avg), "est_items_per_disc": fits, "headroom_items": max(fits - count, 0),
            "fill_pct": round((used / total) * 100, 4), "over_capacity": used > total}


@router.get("/disks/status")
async def disks_status():
    text_count = await db.text_disk.count_documents({})
    media_count = await db.media_disk.count_documents({"is_deleted": False})
    text_used = 0
    async for d in db.text_disk.find({}, {"_id": 0, "size_bytes": 1}):
        text_used += d.get("size_bytes", 0)
    media_used = largest_media = 0
    async for d in db.media_disk.find({"is_deleted": False}, {"_id": 0, "size_bytes": 1}):
        size = d.get("size_bytes", 0)
        media_used += size
        largest_media = max(largest_media, size)

    disc = {"drive": DRIVE_MODEL, "medium": DISC_MEDIUM, "total_bytes": DISC_CAPACITY_BYTES}
    return {
        "hardware": {"drive_model": DRIVE_MODEL, "medium": DISC_MEDIUM, "drive_count": 2},
        "text_disk": {"label": "TEXT DISK", "slot": "DRIVE 0", **disc, "used_bytes": text_used,
                      "article_count": text_count, "status": "READY" if text_count else "EMPTY"},
        "media_disk": {"label": "MEDIA DISK", "slot": "DRIVE 1", **disc, "used_bytes": media_used,
                       "image_count": media_count, "status": "READY" if media_count else "EMPTY"},
        "capacity": {
            "disc_bytes": DISC_CAPACITY_BYTES,
            "text": _capacity_plan(text_used, text_count, DISC_CAPACITY_BYTES),
            "media": _capacity_plan(media_used, media_count, DISC_CAPACITY_BYTES),
            "largest_media_bytes": largest_media,
            "largest_media_over_disc": largest_media > DISC_CAPACITY_BYTES,
        },
        "seed": await archive_builder.current_progress(),
    }
