"""Burn to Disc: build the two ISO images, download them and their checksums, and preview the
offline site exactly as it will appear on the discs (served under /api/preview/)."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

import disc_images
import media_storage
from config import db
from disc_site import SITE_CSS, article_page, file_extension, home_page
from routes.articles import get_media

router = APIRouter()


@router.post("/burn")
async def burn_start():
    if disc_images.progress["state"] == "running":
        return {"state": "running", "detail": "disc images are already being built"}
    asyncio.create_task(disc_images.build_disc_images())
    return {"state": "started"}


@router.get("/burn/status")
async def burn_status():
    return {"burn": disc_images.progress, "export": await db.exports.find_one({"id": "latest"}, {"_id": 0})}


@router.get("/burn/download/{which}")
async def burn_download(which: str):
    if which not in ("text", "media"):
        raise HTTPException(status_code=404, detail="unknown disc")
    rec = await db.exports.find_one({"id": "latest"}, {"_id": 0})
    if not rec or which not in rec:
        raise HTTPException(status_code=404, detail="no disc image built yet")
    entry = rec[which]
    if entry.get("backend") == "objstore":
        data, _ = await asyncio.to_thread(media_storage.load_file, entry["location"])
    else:
        fp = Path(entry["location"])
        if not fp.exists():
            raise HTTPException(status_code=404, detail="disc image missing; rebuild it")
        data = await asyncio.to_thread(fp.read_bytes)
    return Response(content=data, media_type="application/x-iso9660-image",
                    headers={"Content-Disposition": f'attachment; filename="offline-wiki-{which}.iso"'})


@router.get("/burn/checksums")
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
    return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": 'attachment; filename="SHA256SUMS"'})


async def _image_extensions():
    medias = await db.media_disk.find({"is_deleted": False}, {"_id": 0, "id": 1, "content_type": 1}).to_list(None)
    return {m["id"]: file_extension(m.get("content_type")) for m in medias}


@router.get("/preview", include_in_schema=False)
async def preview_root_noslash():
    return RedirectResponse(url="preview/index.html")


@router.get("/preview/", include_in_schema=False)
async def preview_root():
    return RedirectResponse(url="index.html")


@router.get("/preview/index.html", response_class=HTMLResponse)
async def preview_index():
    docs = await db.text_disk.find({}, {"_id": 0}).to_list(None)
    return HTMLResponse(home_page(docs, await _image_extensions()))


@router.get("/preview/assets/style.css")
async def preview_css():
    return Response(SITE_CSS, media_type="text/css")


@router.get("/preview/articles/{slug}", response_class=HTMLResponse)
async def preview_article(slug: str):
    slug = slug[:-5] if slug.endswith(".html") else slug
    doc = await db.text_disk.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="article not on disc")
    return HTMLResponse(article_page(doc, await _image_extensions()))


@router.get("/preview/media/{fname}")
async def preview_media(fname: str):
    return await get_media(fname.rsplit(".", 1)[0])
