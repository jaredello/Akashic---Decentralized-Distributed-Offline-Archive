"""Burn to Disc: packs the archive into two real ISO 9660 disc images (Text Disc + Media Disc).

`build_disc_images` runs in the background, records SHA-256 checksums, and stores the finished
images in object storage (or on local disk as a fallback). Progress is published in `progress`.
"""

import asyncio
import hashlib
import io
import json
import re
from datetime import datetime, timezone

import pycdlib

import media_storage
from config import LOCAL_EXPORT_DIR, db, logger
from disc_site import MEDIA_DISC_README, SITE_CSS, TEXT_DISC_README, article_page, file_extension, home_page

progress = {"state": "idle", "step": "", "progress": 0, "total": 0, "error": ""}


def _reset_progress(**values):
    progress.clear()
    progress.update(values)


def make_iso(volume_name, files):
    """Build an ISO image in memory from [{"path": "a/b.html", "data": bytes}].

    ISO 9660 only allows short upper-case names, so files get short internal names while the
    Joliet and Rock Ridge extensions keep the real names that computers actually show.
    """
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", vol_ident=volume_name[:16])
    iso_dirs = {"": ""}
    counts = {"dirs": 0, "files": 0}

    def iso_dir_for(real_dir):
        if real_dir in iso_dirs:
            return iso_dirs[real_dir]
        parent, _, name = real_dir.rpartition("/")
        parent_iso = iso_dir_for(parent)
        counts["dirs"] += 1
        iso_path = f"{parent_iso}/D{counts['dirs']:04d}"
        iso.add_directory(iso_path, rr_name=name, joliet_path="/" + real_dir)
        iso_dirs[real_dir] = iso_path
        return iso_path

    for f in files:
        path = f["path"].strip("/")
        real_dir, _, file_name = path.rpartition("/")
        parent_iso = iso_dir_for(real_dir) if real_dir else ""
        counts["files"] += 1
        ext = file_name.rsplit(".", 1)[-1] if "." in file_name else "dat"
        ext3 = re.sub(r"[^A-Z0-9]", "", ext.upper())[:3] or "DAT"
        data = f["data"]
        iso.add_fp(io.BytesIO(data), len(data), f"{parent_iso}/F{counts['files']:05d}.{ext3};1",
                   rr_name=file_name, joliet_path="/" + path)

    buf = io.BytesIO()
    iso.write_fp(buf)
    iso.close()
    return buf.getvalue()


async def read_image_bytes(media):
    """Read one image from the Media Disc (object storage, or inline in MongoDB)."""
    if media.get("storage_backend") == "objstore" and media.get("storage_path"):
        try:
            data, _ = await asyncio.to_thread(media_storage.load_file, media["storage_path"])
            return data
        except Exception as e:
            logger.warning(f"media read for burn failed: {e}")
            return None
    return media.get("inline_bytes")


async def _save_image_file(name, data):
    if media_storage.status["ready"]:
        try:
            result = await asyncio.to_thread(media_storage.save_file, f"{media_storage.APP_NAME}/exports/{name}",
                                             data, "application/x-iso9660-image")
            return {"backend": "objstore", "location": result["path"], "size": len(data)}
        except Exception as e:
            logger.warning(f"export objstore put failed, writing local: {e}")
    LOCAL_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    fp = LOCAL_EXPORT_DIR / name
    await asyncio.to_thread(fp.write_bytes, data)
    return {"backend": "local", "location": str(fp), "size": len(data)}


def _text_disc_files(docs, extensions):
    files = [
        {"path": "index.html", "data": home_page(docs, extensions).encode("utf-8")},
        {"path": "assets/style.css", "data": SITE_CSS.encode("utf-8")},
        {"path": "README.txt", "data": TEXT_DISC_README.encode("utf-8")},
    ]
    for d in docs:
        files.append({"path": f'articles/{d["slug"]}.html', "data": article_page(d, extensions).encode("utf-8")})
        raw = {k: d.get(k) for k in ("slug", "title", "description", "lead_html", "sections")}
        files.append({"path": f'data/{d["slug"]}.json', "data": json.dumps(raw, ensure_ascii=False).encode("utf-8")})
    return files


async def _media_disc_files(medias, extensions):
    files, manifest = [], []
    for i, m in enumerate(medias):
        data = await read_image_bytes(m)
        progress["progress"] = i + 1
        if data is None:
            continue
        name = f'media/{m["id"]}.{extensions[m["id"]]}'
        files.append({"path": name, "data": data})
        manifest.append({"id": m["id"], "article": m.get("article_slug"), "caption": m.get("caption"), "file": name})
    image_count = len(files)
    files.append({"path": "manifest.json", "data": json.dumps(manifest, ensure_ascii=False).encode("utf-8")})
    files.append({"path": "README.txt", "data": MEDIA_DISC_README.encode("utf-8")})
    return files, image_count


async def build_disc_images():
    _reset_progress(state="running", step="loading archive", progress=0, total=0, error="")
    try:
        docs = await db.text_disk.find({}, {"_id": 0}).to_list(None)
        medias = await db.media_disk.find({"is_deleted": False}, {"_id": 0}).to_list(None)
        if not docs:
            raise RuntimeError("archive is empty — seed articles first")
        extensions = {m["id"]: file_extension(m.get("content_type")) for m in medias}
        progress["total"] = len(medias)

        progress["step"] = "writing text pages"
        text_files = _text_disc_files(docs, extensions)
        progress["step"] = "building TEXT DISC image"
        text_iso = await asyncio.to_thread(make_iso, "OWIKI_TEXT", text_files)

        progress["step"] = "reading Media Disk"
        media_files, image_count = await _media_disc_files(medias, extensions)
        progress["step"] = "building MEDIA DISC image"
        media_iso = await asyncio.to_thread(make_iso, "OWIKI_MEDIA", media_files)

        progress["step"] = "finalizing"
        text_entry = await _save_image_file("offline-wiki-text.iso", text_iso)
        media_entry = await _save_image_file("offline-wiki-media.iso", media_iso)
        await db.exports.replace_one({"id": "latest"}, {
            "id": "latest", "created_at": datetime.now(timezone.utc).isoformat(),
            "text": {**text_entry, "article_count": len(docs), "sha256": hashlib.sha256(text_iso).hexdigest(),
                     "filename": "offline-wiki-text.iso"},
            "media": {**media_entry, "image_count": image_count, "sha256": hashlib.sha256(media_iso).hexdigest(),
                      "filename": "offline-wiki-media.iso"},
        }, upsert=True)
        _reset_progress(state="done", step="done", progress=len(medias), total=len(medias), error="",
                        text_size=len(text_iso), media_size=len(media_iso))
        logger.info("burn complete")
    except Exception as e:
        logger.exception("burn failed")
        _reset_progress(state="error", step="", progress=0, total=0, error=str(e)[:200])
