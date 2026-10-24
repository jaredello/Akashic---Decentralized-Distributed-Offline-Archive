"""Talks to Wikipedia's public APIs: article summaries, plain text, images and links.

Wikipedia rate-limits busy clients, so every request goes through `_get`, which waits and retries
when Wikipedia answers "slow down" (HTTP 429/503). All functions are blocking; call them with
`asyncio.to_thread`.
"""

import time

import requests

REST_API = "https://en.wikipedia.org/api/rest_v1"
ACTION_API = "https://en.wikipedia.org/w/api.php"

_http = requests.Session()
_http.headers.update({"User-Agent": "OfflineWikiMDiscDemo/1.0 (offline archive demo)"})


def _get(url, params=None, retries=5):
    delay = 2.0
    last = None
    for _ in range(retries):
        r = _http.get(url, params=params, timeout=30)
        if r.status_code in (429, 503):
            last = r
            time.sleep(min(float(r.headers.get("Retry-After", delay)), 20))
            delay *= 2
            continue
        r.raise_for_status()
        return r
    if last is not None:
        last.raise_for_status()
    raise RuntimeError(f"failed to fetch {url}")


def fetch_summary(title):
    """Short description, canonical title and lead image of an article."""
    return _get(f"{REST_API}/page/summary/{requests.utils.quote(title)}").json()


def fetch_plain_text(title):
    """The whole article as plain text, with headings written like `== History ==`."""
    params = {"action": "query", "prop": "extracts", "titles": title, "format": "json",
              "explaintext": 1, "exsectionformat": "wiki", "redirects": 1}
    pages = _get(ACTION_API, params=params).json().get("query", {}).get("pages", {})
    for page in pages.values():
        return page.get("extract", "") or ""
    return ""


def _image_caption(item):
    caption = item.get("caption") or {}
    text = (caption.get("text") or "").strip() if isinstance(caption, dict) else ""
    if text:
        return text
    return (item.get("title") or "").replace("File:", "").rsplit(".", 1)[0].replace("_", " ")


def _largest_image_url(item):
    srcset = item.get("srcset") or []
    if not srcset:
        return None
    src = srcset[-1].get("src") or srcset[0].get("src")
    if src and src.startswith("//"):
        src = "https:" + src
    return src


def fetch_image_list(title, limit=4):
    """Up to `limit` images used in the article, as [{"url", "caption"}]."""
    try:
        items = _get(f"{REST_API}/page/media-list/{requests.utils.quote(title)}").json().get("items", [])
    except Exception:
        return []
    images = []
    for item in items:
        if item.get("type") != "image":
            continue
        url = _largest_image_url(item)
        if not url:
            continue
        images.append({"url": url, "caption": _image_caption(item)})
        if len(images) >= limit:
            break
    return images


def download_image(url):
    """Returns (bytes, content_type)."""
    r = _get(url)
    return r.content, r.headers.get("Content-Type", "image/jpeg")


def fetch_linked_titles(title):
    """Titles of every other article this article links to."""
    params = {"action": "query", "prop": "links", "titles": title, "plnamespace": 0,
              "pllimit": "max", "format": "json", "redirects": 1}
    titles = []
    try:
        data = _get(ACTION_API, params=params).json()
        for page in data.get("query", {}).get("pages", {}).values():
            titles.extend(link["title"] for link in page.get("links", []))
    except Exception:
        pass
    return titles
