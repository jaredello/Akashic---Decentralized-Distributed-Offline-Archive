"""Offline Wikipedia on two M-DISCs: the web server.

This file only wires things together. The real work lives in clearly named modules:
  config.py           database connection and hardware constants
  wikipedia_api.py    downloading from Wikipedia
  article_text.py     turning Wikipedia text into HTML sections and links
  topics.py           starter articles and topic themes
  archive_builder.py  filling the Text Disc and Media Disc
  media_storage.py    the Media Disc's file storage
  disc_site.py        the offline website written onto the discs
  disc_images.py      building the ISO disc images
  routes/             the web addresses (API endpoints), grouped by topic
"""

import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from config import logger, mongo_client
import media_storage
from routes import archive, articles, burn, kit, source

app = FastAPI(title="Offline Wikipedia — Dual M-Disc Archive")

for module in (articles, archive, burn, kit, source):
    app.include_router(module.router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        media_storage.connect()
        logger.info("Media Disk (object storage) initialized")
    except Exception as e:
        media_storage.status["ready"] = False
        logger.error(f"Object storage init failed, images will inline to Mongo: {e}")


@app.on_event("shutdown")
async def shutdown():
    mongo_client.close()
