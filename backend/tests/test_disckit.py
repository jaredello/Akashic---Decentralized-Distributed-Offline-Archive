# DiscKit (macOS desktop kit) regression tests: kit API, CLI build (zim/folder/website), verify, Two-Drive Reader
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import zipfile

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
ZIM = "/root/zim/knots.zim"
WORK = "/tmp/disckit_pytest"


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _cli(kit, *args, check=True):
    r = subprocess.run([sys.executable, "-m", "disckit", *args], cwd=kit, capture_output=True, text=True, timeout=280)
    if check:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def _entries(d):
    db = sqlite3.connect(os.path.join(d, "index.db"))
    try:
        return db.execute("select path, mime from entries").fetchall()
    finally:
        db.close()


@pytest.fixture(scope="session")
def kit():
    subprocess.run(["rm", "-rf", WORK]); os.makedirs(WORK)
    r = requests.get(f"{BASE_URL}/api/kit/download", timeout=60)
    assert r.status_code == 200
    zipfile.ZipFile(io.BytesIO(r.content)).extractall(WORK)
    return os.path.join(WORK, "DiscKit")


class Reader:
    def __init__(self, kit, *discs):
        self.port = _free_port()
        self.p = subprocess.Popen([sys.executable, "-m", "disckit", "read", *discs, "--no-browser", "--port", str(self.port)],
                                  cwd=kit, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.url = f"http://127.0.0.1:{self.port}"
        for _ in range(50):
            try:
                requests.get(self.url + "/_disckit/api/info", timeout=1); break
            except requests.RequestException:
                time.sleep(0.1)

    def get(self, path, **kw):
        kw.setdefault("allow_redirects", False)
        return requests.get(self.url + path, timeout=10, **kw)

    def stop(self):
        self.p.terminate(); self.p.wait()


# ---------- Kit API ----------
class TestKitApi:
    def test_info(self):
        d = requests.get(f"{BASE_URL}/api/kit/info").json()
        assert d["version"] == "1.1.0" and d["file_count"] > 0
        assert d["sources"] == ["zim", "folder", "website"]

    def test_download_zip(self):
        r = requests.get(f"{BASE_URL}/api/kit/download")
        assert r.headers["content-type"] == "application/zip"
        assert "DiscKit-macOS.zip" in r.headers["content-disposition"]
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = z.namelist()
        for n in ["DiscKit/README.md", "DiscKit/install.command", "DiscKit/DiscKit.command",
                  "DiscKit/Read Discs.command", "DiscKit/requirements.txt", "DiscKit/disckit/__main__.py",
                  "DiscKit/disckit/reader/shell.html"]:
            assert n in names
        assert not any("__pycache__" in n for n in names)
        for i in z.infolist():
            if i.filename.endswith(".command"):
                assert (i.external_attr >> 16) & 0o777 == 0o755


# ---------- ZIM build + reader ----------
@pytest.fixture(scope="session")
def zim_discs(kit):
    if not os.path.exists(ZIM):
        pytest.skip("knots.zim missing")
    t, m = f"{WORK}/zim/T", f"{WORK}/zim/M"
    _cli(kit, "build", "zim", ZIM, "--text-out", t, "--media-out", m)
    return t, m


class TestZim:
    def test_plan(self, kit):
        out = _cli(kit, "plan", "zim", ZIM).stdout
        assert "Text  Disc" in out and "Media Disc" in out and "Redirects" in out

    def test_split(self, zim_discs):
        t, m = zim_discs
        assert all(not mm.startswith(("image/", "audio/", "video/")) for _, mm in _entries(t))
        assert all(mm.startswith("image/") for _, mm in _entries(m))
        db = sqlite3.connect(os.path.join(t, "index.db"))
        assert db.execute("select count(*) from redirects").fetchone()[0] > 0
        assert db.execute("select count(*) from titles").fetchone()[0] > 0
        jt, jm = (json.load(open(os.path.join(d, "DISCKIT.json"))) for d in (t, m))
        assert jt["set_id"] == jm["set_id"] and jt["role"] == "text" and jm["role"] == "media"

    def test_verify(self, kit, zim_discs):
        for d in zim_discs:
            assert "0 bad" in _cli(kit, "verify", d).stdout

    def test_existing_disc_folder_rejected(self, kit, zim_discs):
        r = _cli(kit, "build", "zim", ZIM, "--text-out", zim_discs[0], "--media-out", f"{WORK}/zim/M_new", check=False)
        assert r.returncode != 0 and "is not empty" in r.stderr

    def test_nonempty_folder_rejected(self, kit):
        junk = f"{WORK}/junk"; os.makedirs(junk, exist_ok=True)
        open(f"{junk}/x.txt", "w").write("x")
        r = _cli(kit, "build", "zim", ZIM, "--text-out", junk, "--media-out", f"{WORK}/junk_m", check=False)
        assert r.returncode != 0, "build into a non-empty (non-disc) folder should be refused"

    def test_error_is_clean_no_traceback(self, kit, zim_discs):
        r = _cli(kit, "build", "zim", ZIM, "--text-out", zim_discs[0], "--media-out", f"{WORK}/zim/M_x", check=False)
        assert "Traceback" not in r.stderr, "CLI should print a friendly error, not a traceback"

    def test_media_conflict_leaves_no_orphan_text_disc(self, kit, zim_discs):
        t2 = f"{WORK}/zim/T_orphan"
        _cli(kit, "build", "zim", ZIM, "--text-out", t2, "--media-out", zim_discs[1], check=False)
        assert not os.path.exists(os.path.join(t2, "index.db")), "failed build left a half-made Text Disc"


@pytest.fixture(scope="session")
def zim_reader(kit, zim_discs):
    r = Reader(kit, *zim_discs)
    yield r
    r.stop()


class TestZimReader:
    def test_root_redirects(self, zim_reader):
        assert zim_reader.get("/").headers["Location"].endswith("/_disckit/")
        r = zim_reader.get("/", headers={"Sec-Fetch-Dest": "iframe"})
        assert r.status_code == 302 and r.headers["Location"].endswith("/mainPage")

    def test_article_and_images_and_io(self, zim_reader):
        r = zim_reader.get("/Trefoil_knot")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        img = zim_reader.get("/_assets_/d1f33b1cb42dc60ec0e42c6954875701/Blue_Trefoil_Knot.png")
        assert img.status_code == 200 and img.headers["content-type"].startswith("image/")
        vols = {v["role"]: v for v in zim_reader.get("/_disckit/api/io").json()["volumes"]}
        assert vols["text"]["reads"] > 0 and vols["text"]["bytes_read"] > 0
        assert vols["media"]["reads"] > 0 and vols["media"]["bytes_read"] > 0

    def test_redirect_entry(self, zim_reader):
        r = zim_reader.get("/(2,3)-torus_knot")
        assert r.status_code == 302 and r.headers["Location"].endswith("/Trefoil_knot")

    def test_search_random_404(self, zim_reader):
        res = zim_reader.get("/_disckit/api/search?q=tre").json()
        assert any(x["path"] == "Trefoil_knot" for x in res)
        assert isinstance(zim_reader.get("/_disckit/api/random").json()["path"], str)
        assert zim_reader.get("/No_such_article_xyz").status_code == 404


# ---------- Folder source ----------
class TestFolder:
    def test_folder_build_and_read(self, kit):
        src = f"{WORK}/fsrc"; os.makedirs(f"{src}/sub", exist_ok=True)
        open(f"{src}/index.html", "w").write("<html><title>Home</title><img src='a.png'></html>")
        open(f"{src}/a.png", "wb").write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        open(f"{src}/notes.txt", "w").write("notes")
        open(f"{src}/sub/b.txt", "w").write("b")
        t, m = f"{WORK}/f/T", f"{WORK}/f/M"
        _cli(kit, "build", "folder", src, "--text-out", t, "--media-out", m)
        assert {p for p, _ in _entries(m)} == {"a.png"}
        assert {p for p, _ in _entries(t)} == {"index.html", "notes.txt", "sub/b.txt"}
        r = Reader(kit, t, m)
        try:
            assert r.get("/", headers={"Sec-Fetch-Dest": "iframe"}).headers["Location"].endswith("/index.html")
            assert r.get("/a.png").status_code == 200
            lst = r.get("/sub/")
            assert lst.status_code == 200 and "b.txt" in lst.text
            assert r.get("/sub").status_code == 302
        finally:
            r.stop()


# ---------- Website source ----------
class TestWebsite:
    def test_website_build_and_read(self, kit):
        t, m = f"{WORK}/w/T", f"{WORK}/w/M"
        _cli(kit, "build", "website", "https://books.toscrape.com/", "--max-pages", "3", "--max-depth", "1",
             "--delay", "0.1", "--text-out", t, "--media-out", m)
        assert any(mm == "image/jpeg" for _, mm in _entries(m))
        tm = [mm for _, mm in _entries(t)]
        assert any(x.startswith("text/html") for x in tm) and any(x.startswith("text/css") for x in tm)
        r = Reader(kit, t, m)
        try:
            html = r.get("/index.html").text
            assert 'href="/catalogue/' in html and 'src="/media/cache/' in html
            assert r.get("/static/oscar/css/styles.css").status_code == 200
        finally:
            r.stop()

    def test_website_pages_dedup_by_key(self, kit):
        """'/' and '/index.html' map to the same disc key; max-pages=3 should still yield 3 distinct html pages."""
        t = f"{WORK}/w/T"
        if not os.path.exists(t):
            pytest.skip("website not built")
        html = [p for p, mm in _entries(t) if mm.startswith("text/html")]
        meta = json.load(open(os.path.join(t, "DISCKIT.json")))
        assert meta["entries"] == len(_entries(t)), f"DISCKIT.json entries={meta['entries']} but index has {len(_entries(t))}"
        assert len(html) == 3, f"only {len(html)} distinct pages archived: {html}"
