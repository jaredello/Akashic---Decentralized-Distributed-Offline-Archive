"""Backend tests for Offline Wikipedia Dual M-Disc archive."""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://dual-disc-wiki.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---- Disks status ----
def test_disks_status(s):
    r = s.get(f"{API}/disks/status", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["hardware"]["drive_model"] == "ASUS ZenDrive U9M"
    assert data["text_disk"]["article_count"] > 0
    assert data["media_disk"]["image_count"] > 0
    assert data["seed"]["state"] == "done"


# ---- Articles list ----
def test_articles_list(s):
    r = s.get(f"{API}/articles", timeout=30)
    assert r.status_code == 200
    arts = r.json()
    assert isinstance(arts, list)
    assert 15 <= len(arts) <= 25
    for a in arts:
        assert a["slug"] and a["title"]
        assert "description" in a
        assert "size_bytes" in a
    # at least most should have lead_media_id
    with_lead = [a for a in arts if a.get("lead_media_id")]
    assert len(with_lead) >= len(arts) - 2


# ---- Article detail ----
@pytest.mark.parametrize("slug", ["Lion", "Black_hole"])
def test_article_detail(s, slug):
    r = s.get(f"{API}/articles/{slug}", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["title"]
    assert d["lead_html"]
    assert isinstance(d["sections"], list) and len(d["sections"]) > 0
    for sec in d["sections"]:
        assert sec["title"] and sec["anchor"] and sec["html"]
    assert isinstance(d["toc"], list)
    assert len(d["toc"]) == len(d["sections"])
    media = d.get("media", [])
    assert len(media) >= 1
    leads = [m for m in media if m.get("is_lead")]
    assert len(leads) == 1


# ---- Search ----
def test_search_lio(s):
    r = s.get(f"{API}/search", params={"q": "lio"}, timeout=30)
    assert r.status_code == 200
    results = r.json()
    assert any("Lion" in x["title"] for x in results)


def test_search_empty(s):
    r = s.get(f"{API}/search", params={"q": ""}, timeout=30)
    assert r.status_code == 200
    assert r.json() == []


# ---- Media (Media Disk read) ----
def test_media_image_bytes(s):
    r = s.get(f"{API}/articles/Lion", timeout=30)
    media_id = r.json()["media"][0]["id"]
    m = s.get(f"{API}/media/{media_id}", timeout=60)
    assert m.status_code == 200
    assert m.headers["content-type"].startswith("image/")
    assert len(m.content) > 100


def test_media_404(s):
    r = s.get(f"{API}/media/non-existent-id", timeout=30)
    assert r.status_code == 404


# ---- Cross article linking ----
def test_cross_article_linking(s):
    arts_r = s.get(f"{API}/articles", timeout=30).json()
    found_wikilink = False
    for a in arts_r[:8]:
        d = s.get(f"{API}/articles/{a['slug']}", timeout=30).json()
        html_all = d.get("lead_html", "") + "".join(sec.get("html", "") for sec in d.get("sections", []))
        if re.search(r'data-wikilink="[^"]+"', html_all):
            found_wikilink = True
            break
    assert found_wikilink, "No data-wikilink anchors found in sampled articles"
