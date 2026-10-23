# DiscKit full-text search: build (with/without index), reader /_disckit/api/fulltext, kit info/download
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
import requests

KIT = "/app/disckit"
ZIM = "/root/zim/knots.zim"
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _build(tmp, extra=()):
    t, m = tmp / "T", tmp / "M"
    r = subprocess.run([sys.executable, "-m", "disckit", "build", "zim", ZIM, "--text-out", str(t),
                        "--media-out", str(m), *extra], cwd=KIT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr + r.stdout
    return t, m


def _serve(t, m):
    port = _free_port()
    p = subprocess.Popen([sys.executable, "-m", "disckit", "read", str(t), str(m), "--no-browser",
                          "--port", str(port)], cwd=KIT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            requests.get(url + "/_disckit/api/info", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    return p, url


@pytest.fixture(scope="module")
def ft_reader():
    if not Path(ZIM).exists():
        pytest.skip("knots.zim missing")
    tmp = Path(tempfile.mkdtemp())
    t, m = _build(tmp)
    p, url = _serve(t, m)
    yield t, url
    p.terminate()


@pytest.fixture(scope="module")
def noft_reader():
    tmp = Path(tempfile.mkdtemp())
    t, m = _build(tmp, ["--no-fulltext"])
    p, url = _serve(t, m)
    yield t, url
    p.terminate()


# --- build output
def test_build_meta_fulltext(ft_reader):
    t, _ = ft_reader
    meta = json.loads((t / "DISCKIT.json").read_text())
    assert meta["fulltext"] is True and meta["fulltext_docs"] > 0
    names = {r[0] for r in sqlite3.connect(str(t / "index.db")).execute("select name from sqlite_master")}
    assert {"docs", "fts"} <= names


def test_build_no_fulltext(noft_reader):
    t, url = noft_reader
    meta = json.loads((t / "DISCKIT.json").read_text())
    assert meta["fulltext"] is False
    assert requests.get(url + "/_disckit/api/info").json()["fulltext"] is False
    r = requests.get(url + "/_disckit/api/fulltext", params={"q": "bowline"}).json()
    assert r["available"] is False and r["results"] == []


# --- reader API
def test_info(ft_reader):
    assert requests.get(ft_reader[1] + "/_disckit/api/info").json()["fulltext"] is True


def _ft(url, q, page=0):
    r = requests.get(url + "/_disckit/api/fulltext", params={"q": q, "page": page})
    assert r.status_code == 200, r.text
    return r.json()


def test_bowline_first(ft_reader):
    r = _ft(ft_reader[1], "bowline")
    assert r["available"] and r["total"] > 1
    assert r["results"][0]["title"] == "Bowline"
    for h in r["results"]:
        assert h["path"] and h["title"]
        assert isinstance(h["snippet"], list)
        for seg, is_m in h["snippet"]:
            if is_m:
                assert seg.lower().startswith("bowline")
    assert any(m for h in r["results"] for _, m in h["snippet"])


def test_multiword_requires_all(ft_reader):
    url = ft_reader[1]
    both = _ft(url, "sailor rope")
    a, b = _ft(url, "sailor"), _ft(url, "rope")
    assert both["total"] <= min(a["total"], b["total"])
    assert both["total"] > 0


def test_prefix_last_word(ft_reader):
    r = _ft(ft_reader[1], "trefo")
    assert any("Trefoil" in h["title"] for h in r["results"]), [h["title"] for h in r["results"]]


def test_paging(ft_reader):
    url = ft_reader[1]
    p0, p1 = _ft(url, "knot"), _ft(url, "knot", 1)
    assert p0["more"] is True and len(p0["results"]) == 15
    assert p1["results"]
    assert not ({h["path"] for h in p0["results"]} & {h["path"] for h in p1["results"]})


def test_empty_query(ft_reader):
    r = _ft(ft_reader[1], "")
    assert r["results"] == [] and r["total"] == 0
    r = _ft(ft_reader[1], "   ")
    assert r["results"] == []


@pytest.mark.parametrize("q", ['"\'*()-', "NOT", "a OR b", "title:x", "^", "AND OR NOT", "'", "\"", "*", "a\"b", "NEAR(a b)", "日本"])
def test_special_chars_no_500(ft_reader, q):
    _ft(ft_reader[1], q)


def test_bad_page_param(ft_reader):
    r = requests.get(ft_reader[1] + "/_disckit/api/fulltext", params={"q": "knot", "page": "abc"})
    assert r.status_code == 200 and r.json()["page"] == 0


# --- ranking (iteration_5: bm25 fixed with content='' + detail=full)
def test_bm25_nonzero(ft_reader):
    db = sqlite3.connect(str(ft_reader[0] / "index.db"))
    sql = db.execute("select sql from sqlite_master where name='fts'").fetchone()[0]
    assert "detail=full" in sql
    scores = [r[0] for r in db.execute("SELECT bm25(fts,10,1) FROM fts WHERE fts MATCH '\"paracord\"*'")]
    assert scores and all(s != 0 for s in scores)


def test_body_only_ranked_not_alphabetical(ft_reader):
    titles = [h["title"] for h in _ft(ft_reader[1], "sailor rope")["results"]]
    assert titles[0] == "Sailor's hitch" and titles != sorted(titles)
    titles = [h["title"] for h in _ft(ft_reader[1], "paracord")["results"]]
    assert titles[0] == "Lanyard" and titles != sorted(titles)


def test_no_excerpt_placeholder(ft_reader):
    hit = [h for h in _ft(ft_reader[1], "braid length")["results"] if h["title"] == "Braid length"]
    assert hit and hit[0]["snippet"] == [["(no excerpt)", False]]


def test_accent_insensitive_highlight(ft_reader):
    r = _ft(ft_reader[1], "mobius")
    assert any(seg == "Möbius" for h in r["results"] for seg, m in h["snippet"] if m)


def test_paging_no_gap_with_pinned_title(ft_reader):
    # 'Knot' is pinned first but is not in bm25 top-15; every bm25 hit must still appear on some page
    url = ft_reader[1]
    got = [h["path"] for pg in range(3) for h in _ft(url, "knot", pg)["results"]]
    assert len(got) == len(set(got))
    assert "Diamond_knot" in got, "15th bm25 hit dropped by exact-title pin"


def test_plan_cli_mb():
    out = subprocess.run([sys.executable, "-m", "disckit", "plan", "zim", ZIM], cwd=KIT, capture_output=True, text=True).stdout
    out2 = subprocess.run([sys.executable, "-m", "disckit", "plan", "zim", ZIM, "--no-fulltext"], cwd=KIT, capture_output=True, text=True).stdout
    assert "MB" in out and "search index: ~0.0 MB" not in out
    assert "search index: ~0.0 MB" in out2


def test_negative_page(ft_reader):
    r = _ft(ft_reader[1], "knot", -5)
    assert r["page"] == 0


def test_shell_served(ft_reader):
    r = requests.get(ft_reader[1] + "/_disckit/")
    assert r.status_code == 200 and 'data-testid="reader-search-all"' in r.text or "reader-results" in r.text


# --- web backend
def test_kit_info():
    d = requests.get(BASE_URL + "/api/kit/info").json()
    assert d["version"] == "1.1.0"
    assert "fulltext_search" in json.dumps(d["features"])
    assert d["app"]["arch"] == "arm64" and d["app"]["signed"] is False and d["app"]["dmg_url"] is None


def test_kit_download_zip():
    r = requests.get(BASE_URL + "/api/kit/download")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    for f in ["build_app.sh", "launcher.py", "icon.png", "FIRST_LAUNCH.txt"]:
        assert f"DiscKit/packaging/macos/{f}" in names, f
    assert "DiscKit/disckit/textindex.py" in names
    mode = (z.getinfo("DiscKit/packaging/macos/build_app.sh").external_attr >> 16) & 0o777
    assert mode == 0o755, oct(mode)
