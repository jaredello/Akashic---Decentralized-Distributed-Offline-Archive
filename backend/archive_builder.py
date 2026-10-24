"""Builds the archive: downloads articles and images from Wikipedia and saves them to the two "discs".

- `build_starter_archive` fetches the starter set of articles.
- `grow_archive` follows links (optionally within a theme) to add many related articles.
Both run in the background; progress is published in `progress` for the status endpoint.
"""

import asyncio
import uuid
from collections import Counter
from datetime import datetime, timezone

import media_storage
import wikipedia_api as wiki
from article_text import add_article_links, remove_links, split_into_sections, title_to_slug
from config import db, logger
from topics import STARTER_ARTICLES, THEMES, is_good_article_title

# Live progress of the current background job (read by /api/seed/status).
progress = {"state": "idle", "phase": "", "done": 0, "total": len(STARTER_ARTICLES), "current": "", "errors": []}


def _reset_progress(**values):
    progress.clear()
    progress.update(values)


def _now():
    return datetime.now(timezone.utc).isoformat()


async def save_image(article_slug, url, caption, is_lead):
    """Download one image and put it on the Media Disc. Returns a small reference, or None on failure."""
    try:
        data, content_type = await asyncio.to_thread(wiki.download_image, url)
    except Exception as e:
        logger.warning(f"media download failed {url}: {e}")
        return None
    media_id = str(uuid.uuid4())
    ext = (content_type.split("/")[-1] or "jpg").split(";")[0]
    backend, storage_path = "inline", None
    if media_storage.status["ready"]:
        try:
            path = f"{media_storage.APP_NAME}/media/{article_slug}/{media_id}.{ext}"
            result = await asyncio.to_thread(media_storage.save_file, path, data, content_type)
            backend, storage_path = "objstore", result["path"]
        except Exception as e:
            logger.warning(f"objstore put failed, inlining: {e}")
    await db.media_disk.insert_one({
        "id": media_id, "article_slug": article_slug, "caption": caption,
        "is_lead": is_lead, "content_type": content_type, "size_bytes": len(data),
        "storage_backend": backend, "storage_path": storage_path,
        "inline_bytes": data if backend == "inline" else None,
        "source_url": url, "is_deleted": False, "created_at": _now(),
    })
    return {"id": media_id, "caption": caption, "is_lead": is_lead, "size_bytes": len(data)}


async def fetch_article(title):
    """Download one article's text and up to three images."""
    summary = await asyncio.to_thread(wiki.fetch_summary, title)
    real_title = summary.get("title", title)
    slug = title_to_slug(real_title)
    plain_text = await asyncio.to_thread(wiki.fetch_plain_text, real_title)
    intro_html, sections = split_into_sections(plain_text)

    await db.media_disk.delete_many({"article_slug": slug})
    images = []
    lead_image = (summary.get("thumbnail") or {}).get("source") or (summary.get("originalimage") or {}).get("source")
    if lead_image:
        ref = await save_image(slug, lead_image, real_title, True)
        if ref:
            images.append(ref)
    for img in await asyncio.to_thread(wiki.fetch_image_list, real_title, 2):
        ref = await save_image(slug, img["url"], img["caption"], False)
        if ref:
            images.append(ref)

    return {"slug": slug, "title": real_title, "description": summary.get("description", ""),
            "lead_html_raw": intro_html, "sections_raw": sections, "media": images}


def _text_size(intro_html, sections):
    return len(intro_html) + sum(len(s["html"]) for s in sections)


async def relink_all_articles():
    """Re-add links between articles after the set of archived articles changed."""
    docs = await db.text_disk.find(
        {}, {"_id": 0, "slug": 1, "title": 1, "lead_html_raw": 1, "sections_raw": 1, "lead_html": 1, "sections": 1}
    ).to_list(None)
    titles_to_slugs = {d["title"]: d["slug"] for d in docs}
    for d in docs:
        raw_intro = d.get("lead_html_raw")
        if raw_intro is None:
            raw_intro = remove_links(d.get("lead_html", ""))
        raw_sections = d.get("sections_raw")
        if raw_sections is None:
            raw_sections = [{"title": s["title"], "anchor": s["anchor"], "html": remove_links(s["html"])}
                            for s in d.get("sections", [])]
        linked_intro = add_article_links(raw_intro, titles_to_slugs, d["slug"])
        linked_sections = [{"title": s["title"], "anchor": s["anchor"],
                            "html": add_article_links(s["html"], titles_to_slugs, d["slug"])} for s in raw_sections]
        await db.text_disk.update_one({"slug": d["slug"]}, {"$set": {
            "lead_html_raw": raw_intro, "sections_raw": raw_sections, "lead_html": linked_intro,
            "sections": linked_sections, "size_bytes": _text_size(raw_intro, raw_sections)}})


async def archive_titles(titles):
    """Fetch and save each title that isn't archived yet, politely spaced out for Wikipedia."""
    for title in titles:
        progress["current"] = title
        try:
            if await db.text_disk.find_one({"slug": title_to_slug(title)}, {"_id": 1}):
                progress["done"] += 1
                continue
            article = await fetch_article(title)
            await db.text_disk.replace_one({"slug": article["slug"]}, {
                "id": str(uuid.uuid4()), **article,
                "lead_html": article["lead_html_raw"], "sections": article["sections_raw"],
                "size_bytes": _text_size(article["lead_html_raw"], article["sections_raw"]),
                "created_at": _now(),
            }, upsert=True)
        except Exception as e:
            logger.error(f"seed failed {title}: {e}")
            progress["errors"].append(f"{title}: {str(e)[:120]}")
        progress["done"] += 1
        await asyncio.sleep(0.9)
    progress["current"] = "linking articles together"
    await relink_all_articles()


async def build_starter_archive():
    _reset_progress(state="running", phase="seeding", done=0, total=len(STARTER_ARTICLES), current="", errors=[])
    await archive_titles(STARTER_ARTICLES)
    progress.update(state="done", current="")
    logger.info("seed complete")


async def _most_linked_titles(roots, target, archived_slugs):
    """Count how often each title is linked from the root articles; the most-linked come first."""
    votes = Counter()
    for root in roots[:40]:
        progress["current"] = f"mapping links · {root}"
        for t in await asyncio.to_thread(wiki.fetch_linked_titles, root):
            if is_good_article_title(t) and title_to_slug(t) not in archived_slugs:
                votes[t] += 1
        await asyncio.sleep(0.35)
    needed = max(target - len(archived_slugs), 0)
    return [t for t, _ in votes.most_common()][:needed]


async def grow_archive(target, theme=None):
    """Grow the archive to about `target` articles, staying close to `theme` if one is given."""
    _reset_progress(state="running", phase="discovering", done=0, total=0, current="", errors=[], theme=theme or "")
    docs = await db.text_disk.find({}, {"_id": 0, "title": 1, "slug": 1}).to_list(None)
    archived = {d["slug"] for d in docs}

    theme_roots = THEMES.get(theme, {}).get("roots") if theme else None
    if theme_roots:
        roots = theme_roots
        titles = [t for t in theme_roots if title_to_slug(t) not in archived]
    else:
        roots = [d["title"] for d in docs] or STARTER_ARTICLES
        titles = []

    for t in await _most_linked_titles(roots, target, archived):
        if title_to_slug(t) not in archived and t not in titles:
            titles.append(t)
    titles = titles[:max(target - len(archived), 0)]

    progress.update(phase="seeding", total=len(titles))
    await archive_titles(titles)
    progress.update(state="done", current="")
    logger.info(f"expand complete (+{len(titles)} targeted, goal {target}, theme {theme})")


async def current_progress():
    """Progress for the UI; reports "done" once the archive exists even after a server restart."""
    if progress["state"] == "running":
        return progress
    count = await db.text_disk.count_documents({})
    if count >= len(STARTER_ARTICLES):
        st = dict(progress)
        st.update({"state": "done", "done": st.get("total", count), "current": ""})
        if st.get("total", 0) < count:
            st["total"] = count
        return st
    return progress
