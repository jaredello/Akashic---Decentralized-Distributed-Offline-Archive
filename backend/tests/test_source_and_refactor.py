# Iteration 7: Source API + behaviour-preserving refactor flows (burn, seed expand, seed exists)
import hashlib
import io
import os
import time
import zipfile

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _flatten(nodes, out=None):
    out = [] if out is None else out
    for n in nodes:
        out.append(n)
        if n["type"] == "dir":
            _flatten(n["children"], out)
    return out


# --- Source tree ---
class TestSourceTree:
    def test_tree_top_level_and_hidden(self):
        r = requests.get(f"{API}/source/tree", timeout=60)
        assert r.status_code == 200
        d = r.json()
        names = [n["name"] for n in d["tree"]]
        for want in ["README.md", "LICENSE", "CONTRIBUTING.md", "docs", "backend", "frontend", "disckit", ".github"]:
            assert want in names, want
        assert d["file_count"] > 10 and d["total_bytes"] > 0
        allp = [n["path"] for n in _flatten(d["tree"])]
        for p in allp:
            parts = p.split("/")
            assert not any(x.startswith(".env") for x in parts), p
            assert "node_modules" not in parts and "__pycache__" not in parts, p
            assert "yarn.lock" not in parts, p
            assert parts[0] not in ("memory", "test_reports"), p
        dirs = {n["path"]: n for n in _flatten(d["tree"]) if n["type"] == "dir"}
        assert dirs["backend"]["summary"]
        assert dirs["docs"]["summary"]


# --- Source file / raw / traversal ---
class TestSourceFile:
    def test_python_file(self):
        r = requests.get(f"{API}/source/file", params={"path": "backend/archive_builder.py"})
        assert r.status_code == 200
        d = r.json()
        assert d["kind"] == "text" and d["language"] == "python"
        assert d["summary"] and "def " in d["content"]

    def test_image_file(self):
        r = requests.get(f"{API}/source/file", params={"path": "disckit/packaging/macos/icon.png"})
        assert r.status_code == 200
        assert r.json()["kind"] == "image"

    @pytest.mark.parametrize("p", ["../etc/passwd", "backend/.env", "frontend/.env", "backend/../backend/.env",
                                   "/etc/passwd", "/app/backend/.env", "%2e%2e/etc/passwd",
                                   "backend/%2e%2e/backend/.env", "frontend/node_modules/react/package.json",
                                   "memory/test_credentials.md", "test_reports/iteration_6.json",
                                   "backend\\..\\backend\\.env", "backend/./.env", ".github/../backend/.env"])
    def test_traversal_404(self, p):
        r = requests.get(f"{API}/source/file", params={"path": p})
        assert r.status_code == 404, (p, r.status_code, r.text[:200])
        r2 = requests.get(f"{API}/source/raw", params={"path": p})
        assert r2.status_code == 404, (p, r2.status_code)

    def test_raw_encoded_in_url(self):
        r = requests.get(f"{API}/source/raw?path=backend%2F..%2F..%2Fetc%2Fpasswd")
        assert r.status_code == 404
        r = requests.get(f"{API}/source/raw?path=backend%2F.env")
        assert r.status_code == 404

    def test_raw_headers(self):
        r = requests.get(f"{API}/source/raw", params={"path": "backend/server.py"})
        assert r.status_code == 200
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert "sandbox" in r.headers.get("content-security-policy", "")
        assert b"FastAPI" in r.content

    def test_folder_400(self):
        r = requests.get(f"{API}/source/file", params={"path": "backend"})
        assert r.status_code == 400


# --- Source zip download ---
class TestSourceDownload:
    def test_zip(self):
        r = requests.get(f"{API}/source/download", timeout=120)
        assert r.status_code == 200
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = z.namelist()
        assert not any(n.split("/")[-1].startswith(".env") for n in names)
        assert not any("node_modules" in n or "__pycache__" in n for n in names)
        stripped = ["/".join(n.split("/")[1:]) for n in names]
        for want in ["LICENSE", "README.md", "docs/ARCHITECTURE.md"]:
            assert want in stripped, want


# --- Seed endpoints ---
class TestSeed:
    def test_seed_exists(self):
        r = requests.post(f"{API}/seed")
        assert r.status_code == 200
        assert r.json()["state"] in ("exists", "running")

    def test_invalid_theme(self):
        r = requests.post(f"{API}/seed/expand", params={"target": 50, "theme": "nope_theme"})
        assert r.status_code == 400

    def test_expand_flow(self):
        before = len(requests.get(f"{API}/articles").json())
        r = requests.post(f"{API}/seed/expand", params={"target": before + 2, "theme": "space"})
        assert r.status_code == 200 and r.json()["state"] == "started", r.text
        seen_running = False
        st = {}
        for _ in range(60):
            time.sleep(3)
            st = requests.get(f"{API}/seed/status").json()
            if st["state"] == "running":
                seen_running = True
            if st["state"] in ("done", "error"):
                break
        assert st["state"] == "done", st
        after = len(requests.get(f"{API}/articles").json())
        print("articles before/after", before, after, "seen_running", seen_running, st)
        assert after > before


# --- Burn flow ---
class TestBurn:
    def test_burn_and_download(self):
        r = requests.post(f"{API}/burn")
        assert r.status_code == 200 and r.json()["state"] in ("started", "running")
        st = {}
        for _ in range(150):  # media reads from object storage are slow (~1-2 images/s)
            time.sleep(5)
            st = requests.get(f"{API}/burn/status").json()
            if st["burn"]["state"] in ("done", "error"):
                break
        assert st["burn"]["state"] == "done", st
        sums = requests.get(f"{API}/burn/checksums").text
        lines = {l.split("  ")[1]: l.split("  ")[0] for l in sums.splitlines() if l and not l.startswith("#")}
        print(st["export"]["text"].get("article_count"), st["export"]["media"].get("image_count"))
        for which in ("text", "media"):
            d = requests.get(f"{API}/burn/download/{which}", timeout=180)
            assert d.status_code == 200
            assert d.content[32769:32774] == b"CD001", "not an ISO 9660 image"
            assert hashlib.sha256(d.content).hexdigest() == lines[f"offline-wiki-{which}.iso"]
