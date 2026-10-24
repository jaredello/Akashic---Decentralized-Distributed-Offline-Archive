"""Writes the offline website that goes on the discs: one HTML page per article plus a home page.

Pages on the Text Disc load images from `../media/<id>.<ext>` on the Media Disc, so the two
discs work together when their folders sit side by side (or in the Combined Preview).
"""

import html
import re

SITE_CSS = """
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

TEXT_DISC_README = (
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
MEDIA_DISC_README = (
    "OFFLINE WIKIPEDIA — MEDIA DISC (Drive 1)\n"
    "========================================\n\n"
    "This M-Disc holds the IMAGES for the offline Wikipedia archive. Each file in\n"
    "the 'media' folder is referenced by the article pages on the TEXT DISC.\n"
    "See manifest.json for the id -> article mapping.\n\n"
    "Hardware: written to Verbatim M-DISC 100GB via ASUS ZenDrive U9M.\n"
)

_EXTENSIONS = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
               "image/gif": "gif", "image/webp": "webp", "image/svg+xml": "svg"}


def file_extension(content_type):
    """"image/png; charset=x" -> "png"."""
    ct = (content_type or "").split(";")[0].strip().lower()
    return _EXTENSIONS.get(ct, (ct.split("/")[-1] or "img"))


def _links_to_files(article_html):
    """In-app links (data-wikilink="Slug") become normal links to Slug.html."""
    return re.sub(r'data-wikilink="([^"]+)"', r'href="\1.html"', article_html or "")


def _figure(css_class, media, extensions, prefix):
    ext = extensions.get(media["id"], "jpg")
    return (f'<figure class="{css_class}"><img src="{prefix}media/{media["id"]}.{ext}" alt="">'
            f'<figcaption>{html.escape(media.get("caption", ""))}</figcaption></figure>')


def article_page(doc, extensions):
    """Full HTML page for one article. `extensions` maps media id -> file extension."""
    media = doc.get("media", [])
    lead = next((m for m in media if m.get("is_lead")), None)
    inline = [m for m in media if not m.get("is_lead")]
    title = html.escape(doc["title"])
    p = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f'<title>{title} — Offline Wikipedia</title>',
         '<link rel="stylesheet" href="../assets/style.css"></head><body><div class="wrap">',
         '<p class="back"><a href="../index.html">&larr; Offline Wikipedia</a></p>',
         f'<h1>{title}</h1>']
    if doc.get("description"):
        p.append(f'<p class="desc">{html.escape(doc["description"])}</p>')
    if lead:
        p.append(_figure("infobox", lead, extensions, "../"))
    if doc.get("sections"):
        p.append('<nav class="toc"><b>Contents</b><ol>')
        p.extend(f'<li><a href="#{s["anchor"]}">{html.escape(s["title"])}</a></li>' for s in doc["sections"])
        p.append('</ol></nav>')
    p.append('<div class="body">')
    p.append(_links_to_files(doc.get("lead_html", "")))
    for i, s in enumerate(doc.get("sections", [])):
        p.append(f'<h2 id="{s["anchor"]}">{html.escape(s["title"])}</h2>')
        if i < len(inline):
            p.append(_figure("thumb", inline[i], extensions, "../"))
        p.append(_links_to_files(s.get("html", "")))
    p.append('</div><footer>Retrieved offline from the Text Disc (Drive 0) and Media Disc '
             '(Drive 1). Content from Wikipedia, the free encyclopedia.</footer></div></body></html>')
    return "".join(p)


def home_page(docs, extensions):
    """The disc's index.html: a grid of every archived article."""
    cards = []
    for d in sorted(docs, key=lambda x: x["title"].lower()):
        lead = next((m for m in d.get("media", []) if m.get("is_lead")), None)
        img = f'<img src="media/{lead["id"]}.{extensions.get(lead["id"], "jpg")}" alt="">' if lead else ""
        cards.append(f'<a class="card" href="articles/{d["slug"]}.html">{img}'
                     f'<span>{html.escape(d["title"])}</span></a>')
    return "".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Offline Wikipedia</title>',
        '<link rel="stylesheet" href="assets/style.css"></head><body><div class="wrap">',
        '<span class="badge">OFFLINE · SERVED FROM M-DISC</span>',
        '<h1>Offline Wikipedia</h1>',
        f'<p class="desc">The free encyclopedia, archived to disc — {len(docs)} articles. '
        'No internet required.</p>',
        '<div class="grid">', "".join(cards), '</div></div></body></html>',
    ])
