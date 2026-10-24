"""The "Media Disc": stores image files in Emergent Object Storage.

All functions here are blocking (they use `requests`), so async code calls them through
`asyncio.to_thread`. If storage can't be reached at startup, images are kept inside MongoDB instead.
"""

import os

import requests

import config  # noqa: F401  (loads backend/.env before the settings below are read)

_base = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = _base.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "offline-wiki"  # every stored file lives under this folder name

# Filled in at startup by `connect()`; read by anything that wants to store a file.
status = {"ready": False}
_session_key = None


def _get_session_key(refresh=False):
    """Exchange our Emergent key for a storage session key (cached until it expires)."""
    global _session_key
    if _session_key and not refresh:
        return _session_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")},
                         timeout=30)
    resp.raise_for_status()
    _session_key = resp.json()["storage_key"]
    return _session_key


def connect():
    _get_session_key()
    status["ready"] = True


def save_file(path, data, content_type):
    """Upload bytes to `path`. Retries once with a fresh session key if the old one expired."""
    def upload(key):
        return requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type},
                            data=data, timeout=120)

    resp = upload(_get_session_key())
    if resp.status_code == 404:
        resp = upload(_get_session_key(refresh=True))
    resp.raise_for_status()
    return resp.json()


def load_file(path):
    """Download a stored file. Returns (bytes, content_type)."""
    def download(key):
        return requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)

    resp = download(_get_session_key())
    if resp.status_code == 404:
        resp = download(_get_session_key(refresh=True))
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
