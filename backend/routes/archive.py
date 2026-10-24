"""Building the archive: start the starter download, grow it by theme, and check progress."""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException

import archive_builder
from config import db
from topics import STARTER_ARTICLES, THEMES

router = APIRouter()


@router.post("/seed")
async def seed(force: bool = False):
    if archive_builder.progress["state"] == "running":
        return {"state": "running", "detail": "seed already in progress"}
    count = await db.text_disk.count_documents({})
    if count > 0 and not force:
        return {"state": "exists", "articles": count}
    if force:
        await db.text_disk.delete_many({})
        await db.media_disk.delete_many({})
    asyncio.create_task(archive_builder.build_starter_archive())
    return {"state": "started", "total": len(STARTER_ARTICLES)}


@router.get("/seed/themes")
async def seed_themes():
    return [{"key": k, "label": v["label"]} for k, v in THEMES.items()]


@router.post("/seed/expand")
async def seed_expand(target: int = 150, theme: Optional[str] = None):
    if archive_builder.progress["state"] == "running":
        return {"state": "running", "detail": "an archive operation is already in progress"}
    if theme and theme not in THEMES:
        raise HTTPException(status_code=400, detail="unknown theme")
    target = max(20, min(target, 600))
    asyncio.create_task(archive_builder.grow_archive(target, theme))
    return {"state": "started", "target": target, "theme": theme}


@router.get("/seed/status")
async def seed_status():
    return await archive_builder.current_progress()
