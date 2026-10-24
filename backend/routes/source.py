"""The public Source page: lets anyone browse, read and download the app's complete source code.

Only project files are shown. Settings files (.env), installed packages, build output and
caches are never listed or served, and every requested path is checked against that list.
"""

import ast
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from config import PROJECT_DIR
from routes.kit import zip_files

router = APIRouter()

TOP_LEVEL = ["README.md", "LICENSE", "CONTRIBUTING.md", "docs", "backend", "frontend", "disckit", ".github"]
FRONTEND_ONLY = {"src", "public", "package.json", "craco.config.js", "tailwind.config.js",
                 "postcss.config.js", "jsconfig.json", "components.json"}
HIDDEN_NAMES = {"node_modules", "build", "dist", "__pycache__", ".venv", ".pytest_cache", ".git",
                "yarn.lock", "package-lock.json", ".DS_Store"}
MAX_VIEW_BYTES = 600_000

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".css": "css", ".html": "xml", ".json": "json", ".md": "markdown", ".yml": "yaml", ".yaml": "yaml",
    ".sh": "bash", ".command": "bash", ".txt": "plaintext", ".plist": "xml", ".toml": "ini", ".cfg": "ini",
    ".ini": "ini", "": "plaintext",
}
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
          ".ico": "image/x-icon", ".gif": "image/gif", ".webp": "image/webp"}

FOLDER_NOTES = {
    "docs": "Plain-English guides: how the whole system works.",
    "backend": "The server (Python + FastAPI). Downloads Wikipedia, stores the two discs, builds disc images.",
    "backend/routes": "The web addresses (API endpoints) the website calls, grouped by topic.",
    "backend/tests": "Automated checks that the server behaves correctly.",
    "frontend": "The website you see (React). Talks to the backend through /api.",
    "frontend/src": "Website source code.",
    "frontend/src/pages": "One file per screen: home, article reader, Burn to Disc, Source.",
    "frontend/src/components": "Reusable pieces of the screens (header, disc monitor, search box…).",
    "frontend/src/components/ui": "Ready-made UI building blocks from the shadcn/ui library (buttons, dialogs…). Not app-specific.",
    "frontend/src/components/burn": "The sections of the Burn to Disc screen.",
    "frontend/src/components/source": "The pieces of this Source page.",
    "frontend/src/context": "Shared live state: the simulated disc activity shown in the monitor.",
    "frontend/src/lib": "Small helpers: talking to the backend, formatting sizes.",
    "frontend/src/hooks": "Reusable React hooks.",
    "frontend/public": "Static files served as-is (page shell, icons).",
    "disckit": "DiscKit: the Mac desktop app that archives ALL of Wikipedia onto two real discs.",
    "disckit/disckit": "DiscKit's Python code.",
    "disckit/disckit/sources": "Where archives come from: Kiwix .zim files, folders, websites.",
    "disckit/disckit/reader": "The Two-Drive Reader: reads both discs at once in your browser.",
    "disckit/packaging": "Turning DiscKit into a double-clickable Mac app.",
    "disckit/packaging/macos": "Mac app build, icon, signing and notarization scripts.",
    ".github": "GitHub settings: automatic builds and issue templates.",
    ".github/workflows": "Automatic jobs GitHub runs, e.g. building DiscKit.app on a Mac.",
}


def _hidden(name):
    return name in HIDDEN_NAMES or name.startswith(".env") or name.endswith((".pyc", ".log"))


def _allowed(rel):
    """True if this project-relative path is part of the public source."""
    parts = rel.split("/")
    if not parts or parts[0] not in TOP_LEVEL or any(_hidden(p) or p in ("", ".", "..") for p in parts):
        return False
    return not (parts[0] == "frontend" and len(parts) > 1 and parts[1] not in FRONTEND_ONLY)


def _resolve(rel):
    rel = (rel or "").strip().strip("/")
    if not _allowed(rel):
        raise HTTPException(status_code=404, detail="not part of the public source")
    path = (PROJECT_DIR / rel).resolve()
    if PROJECT_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return path


def _first_comment_block(text, prefix):
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#!") and not lines:
            continue
        if s.startswith(prefix):
            lines.append(s[len(prefix):].strip())
        elif lines or s:
            break
    return " ".join(lines)


def file_summary(path, text):
    """A one-paragraph description pulled from the file's own header comment."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".py":
            return (ast.get_docstring(ast.parse(text)) or "").split("\n\n")[0].replace("\n", " ")
        if suffix in (".js", ".jsx", ".ts", ".tsx", ".css"):
            m = re.match(r"\s*/\*\*?(.*?)\*/", text, re.S)
            if m:
                return " ".join(l.strip(" *") for l in m.group(1).splitlines()).strip()
            return _first_comment_block(text, "//")
        if suffix in (".sh", ".command", ".yml", ".yaml", ".txt") or path.name in ("LICENSE",):
            return _first_comment_block(text, "#") if suffix != ".txt" else ""
        if suffix == ".md":
            for block in re.split(r"\n\s*\n", text):
                b = block.strip()
                if b and not b.startswith(("#", "|", "```", "<", "![", "---")):
                    plain = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", b)
                    return re.sub(r"\s+", " ", re.sub(r"[*_`]", "", plain))[:400]
        if suffix == ".html":
            m = re.search(r"<!--(.*?)-->", text, re.S)
            return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    except (SyntaxError, ValueError):
        return ""
    return ""


def _public_files():
    """Every public file, walking only allowed folders (so huge ones like node_modules are never scanned)."""
    out = []
    for top in TOP_LEVEL:
        p = PROJECT_DIR / top
        if p.is_file():
            out.append(p)
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            here = Path(dirpath)
            dirnames[:] = sorted(d for d in dirnames if _allowed((here / d).relative_to(PROJECT_DIR).as_posix()))
            for name in sorted(filenames):
                f = here / name
                if not f.is_symlink() and _allowed(f.relative_to(PROJECT_DIR).as_posix()):
                    out.append(f)
    return out


def _tree():
    root = {"name": "", "path": "", "type": "dir", "children": {}}
    for f in _public_files():
        rel = f.relative_to(PROJECT_DIR).as_posix()
        node = root
        parts = rel.split("/")
        for i, part in enumerate(parts[:-1]):
            sub = "/".join(parts[:i + 1])
            node = node["children"].setdefault(part, {"name": part, "path": sub, "type": "dir", "children": {},
                                                      "summary": FOLDER_NOTES.get(sub, "")})
        node["children"][parts[-1]] = {"name": parts[-1], "path": rel, "type": "file", "size": f.stat().st_size}

    def finish(node):
        if node["type"] == "file":
            return node
        kids = sorted(node["children"].values(), key=lambda n: (n["type"] != "dir", n["name"].lower()))
        node["children"] = [finish(k) for k in kids]
        return node

    order = {name: i for i, name in enumerate(TOP_LEVEL)}
    tree = finish(root)["children"]
    return sorted(tree, key=lambda n: order.get(n["name"], 99))


@router.get("/source/tree")
async def source_tree():
    files = _public_files()
    return {"tree": _tree(), "file_count": len(files), "total_bytes": sum(f.stat().st_size for f in files)}


@router.get("/source/file")
async def source_file(path: str):
    fp = _resolve(path)
    if fp.is_dir():
        raise HTTPException(status_code=400, detail="that is a folder")
    rel = fp.relative_to(PROJECT_DIR.resolve()).as_posix()
    suffix = fp.suffix.lower()
    size = fp.stat().st_size
    if suffix in IMAGES:
        return {"path": rel, "kind": "image", "size": size, "summary": ""}
    if size > MAX_VIEW_BYTES:
        return {"path": rel, "kind": "too_large", "size": size, "summary": ""}
    try:
        text = fp.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"path": rel, "kind": "binary", "size": size, "summary": ""}
    return {"path": rel, "kind": "text", "size": size, "lines": text.count("\n") + 1,
            "language": LANGUAGES.get(suffix, "plaintext"), "summary": file_summary(fp, text), "content": text}


@router.get("/source/raw")
async def source_raw(path: str):
    fp = _resolve(path)
    if fp.is_dir():
        raise HTTPException(status_code=400, detail="that is a folder")
    media_type = IMAGES.get(fp.suffix.lower(), "text/plain; charset=utf-8")
    return Response(fp.read_bytes(), media_type=media_type,
                    headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.get("/source/download")
async def source_download():
    return Response(zip_files(_public_files(), PROJECT_DIR, "offline-wikipedia-mdisc"), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="offline-wikipedia-mdisc-source.zip"'})
