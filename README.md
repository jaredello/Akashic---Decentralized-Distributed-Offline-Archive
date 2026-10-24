# Offline Wikipedia on two M-DISCs

Wikipedia stored on two archival discs and read back with no internet. **All the article text goes on
one disc and all the images on another.** Both drives are read at the same time, so browsing feels like
the real Wikipedia site.

This project is fully **open source** ([MIT License](LICENSE)). You can browse every file inside the app
on its **Source** page, download the whole thing as a zip, or fork it on GitHub.

## What's in here

| Folder | What it is | Who it's for |
|---|---|---|
| [`frontend/`](frontend/src) | The website (React). It has a Wikipedia-style reader, a live Disk Monitor, a Burn to Disc screen and a Source page. | Anyone with a browser |
| [`backend/`](backend) | The server (Python, FastAPI). It downloads articles from Wikipedia, keeps the "Text Disc" and the "Media Disc", and builds real disc images. | Runs behind the website |
| [`disckit/`](disckit) | **DiscKit**, a Mac desktop app that splits *all* of English Wikipedia (from a Kiwix file) across two 100 GB discs. It burns both discs at once and reads them back together, with full-text search. | Your Mac with two M-DISC drives |
| [`docs/`](docs) | Plain-English guides. | Everyone |
| [`.github/`](.github) | Automatic jobs. GitHub builds the DiscKit Mac app for you. | Maintainers |

**New here? Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).** It explains in everyday language how a
Wikipedia page travels from the internet onto the two discs and back to your screen.

## The two ways to use it

1. **The web app (demo):** pick topics, grow an archive of a few hundred interlinked articles, preview the
   offline site, then download two ISO disc images and burn them.
2. **DiscKit (the real thing):** download the full English Wikipedia from [Kiwix](https://download.kiwix.org/zim/wikipedia/)
   (~110 GB). DiscKit splits it into a ~55 GB Text Disc (with a full-text search index) and a ~60 GB Media
   Disc of thumbnails. See [disckit/README.md](disckit/README.md).

## Running the web app yourself

You need Python 3.11+, Node 18+, Yarn and MongoDB.

```bash
# backend
cd backend
pip install -r requirements.txt
# create backend/.env containing:
#   MONGO_URL=mongodb://localhost:27017
#   DB_NAME=offline_wiki
#   CORS_ORIGINS=*
#   EMERGENT_LLM_KEY=...   (optional: object storage for images; without it images stay in MongoDB)
uvicorn server:app --reload --port 8001

# frontend (new terminal)
cd frontend
yarn install
# create frontend/.env containing:  REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```

Then open http://localhost:3000. The first visit downloads 18 starter articles from Wikipedia, which takes
about a minute.

## Tests

```bash
cd backend && pytest          # server tests plus DiscKit (needs: pip install libzim zstandard)
```

## Contributing

Improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

Article text and images come from [Wikipedia](https://www.wikipedia.org/) and Wikimedia Commons under
CC BY-SA and their own licenses. Offline Wikipedia files come from [Kiwix](https://kiwix.org/).
The hardware this demo models is a Verbatim 100 GB M-DISC BD-R in an ASUS ZenDrive U9M.
