"""DiscKit for Mac: version info and the downloadable source kit (the /disckit folder as a zip)."""

import io
import os
import re
import time
import zipfile

from fastapi import APIRouter
from fastapi.responses import Response

from config import PROJECT_DIR

router = APIRouter()

KIT_DIR = PROJECT_DIR / "disckit"
KIT_SUFFIXES = {".py", ".html", ".md", ".txt", ".command", ".sh", ".png", ".plist"}


def _kit_files():
    return sorted(
        p for p in KIT_DIR.rglob("*")
        if p.is_file() and p.suffix in KIT_SUFFIXES and not p.name.startswith(".")
        and "__pycache__" not in p.parts and ".venv" not in p.parts
    )


def zip_files(files, root, folder_name, executable_suffixes=(".command", ".sh")):
    """Zip `files` (paths under `root`) into `folder_name/…`, keeping scripts executable."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            info = zipfile.ZipInfo(f"{folder_name}/{p.relative_to(root).as_posix()}", time.localtime(p.stat().st_mtime)[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if p.suffix in executable_suffixes else 0o644
            info.external_attr = (0o100000 | mode) << 16
            zf.writestr(info, p.read_bytes())
    return buf.getvalue()


@router.get("/kit/info")
async def kit_info():
    version = re.search(r'__version__ = "([^"]+)"', (KIT_DIR / "disckit" / "__init__.py").read_text()).group(1)
    files = _kit_files()
    return {
        "version": version,
        "platform": "macOS",
        "file_count": len(files),
        "size_bytes": sum(p.stat().st_size for p in files),
        "sources": ["zim", "folder", "website"],
        "features": ["fulltext_search", "dual_drive_reader", "parallel_burn"],
        "app": {"arch": "arm64", "signed": False, "signing_ready": True,
                "signing_guide": "packaging/macos/SIGNING.md", "dmg_url": os.environ.get("DISCKIT_DMG_URL"),
                "workflow": ".github/workflows/disckit-macos.yml"},
    }


@router.get("/kit/download")
async def kit_download():
    return Response(zip_files(_kit_files(), KIT_DIR, "DiscKit"), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="DiscKit-macOS.zip"'})
