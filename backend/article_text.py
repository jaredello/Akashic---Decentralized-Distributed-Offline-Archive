"""Turns Wikipedia's plain text into tidy HTML sections and links articles to each other."""

import html
import re

from bs4 import BeautifulSoup, NavigableString

# End-of-article sections that are mostly lists of links; we leave them out.
SKIPPED_SECTIONS = {
    "references", "external links", "see also", "notes", "bibliography",
    "further reading", "citations", "sources", "footnotes", "gallery",
}
HEADING_RE = re.compile(r"^(={2,6})\s*(.+?)\s*=+\s*$")


def title_to_slug(title):
    """"Black hole" -> "Black_hole" (the same style Wikipedia uses in its URLs)."""
    return title.strip().replace(" ", "_")


def heading_to_anchor(text):
    """"Early life" -> "early-life", used for #links to a section."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_into_sections(plain_text):
    """Turn plain text with `== Heading ==` lines into (intro_html, [{"title", "anchor", "html"}])."""
    intro_parts, sections, current = [], [], None
    paragraph = []

    def target():
        return current["parts"] if current else intro_parts

    def end_paragraph():
        if paragraph:
            text = " ".join(paragraph).strip()
            if text:
                target().append("<p>" + html.escape(text, quote=False) + "</p>")
            paragraph.clear()

    for raw_line in plain_text.split("\n"):
        line = raw_line.strip()
        heading = HEADING_RE.match(line)
        if heading:
            end_paragraph()
            level, title = len(heading.group(1)), heading.group(2).strip()
            if level == 2:
                current = {"title": title, "anchor": heading_to_anchor(title), "parts": [],
                           "skip": title.lower() in SKIPPED_SECTIONS}
                sections.append(current)
            else:
                tag = "h3" if level == 3 else "h4"
                target().append(f"<{tag}>{html.escape(title, quote=False)}</{tag}>")
        elif line == "":
            end_paragraph()
        else:
            paragraph.append(line)
    end_paragraph()

    kept = []
    for s in sections:
        body = "".join(s["parts"]).strip()
        if not s["skip"] and "<p>" in body:
            kept.append({"title": s["title"], "anchor": s["anchor"], "html": body})
    return "".join(intro_parts), kept


def add_article_links(article_html, titles_to_slugs, own_slug):
    """Turn the first mention of every other archived article's title into a link to it."""
    if not article_html:
        return article_html
    soup = BeautifulSoup(article_html, "html.parser")
    for title, slug in titles_to_slugs.items():
        if slug == own_slug:
            continue
        pattern = re.compile(r"\b" + re.escape(title) + r"\b")
        for node in list(soup.find_all(string=True)):
            if node.parent.name == "a":
                continue
            match = pattern.search(str(node))
            if not match:
                continue
            before, after = str(node)[:match.start()], str(node)[match.end():]
            link = soup.new_tag("a", **{"data-wikilink": slug, "class": "wikilink"})
            link.string = title
            node.replace_with(NavigableString(before), link, NavigableString(after))
            break
    return str(soup)


def remove_links(article_html):
    return re.sub(r"<a[^>]*>(.*?)</a>", r"\1", article_html or "", flags=re.S)
