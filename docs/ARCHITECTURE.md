# How it all works: a plain-English walkthrough

This guide explains the whole project without assuming you're a programmer. Words in **bold** are the
names you'll see in the code.

---

## 1. The big idea

A web page is really two kinds of thing: **words** (small, compress well) and **pictures** (big,
already compressed). This project stores them on two separate discs:

```
        ┌────────────────────────┐        ┌────────────────────────┐
        │  DRIVE 0 · TEXT DISC   │        │  DRIVE 1 · MEDIA DISC  │
        │  every article's text, │        │  every image           │
        │  links, search index   │        │                        │
        └───────────┬────────────┘        └───────────┬────────────┘
                    │      both read at the same time  │
                    └───────────────┬──────────────────┘
                                    ▼
                      a page that looks like Wikipedia
```

When you open an article, its text comes from drive 0 while its pictures stream from drive 1, both at
the same time. The project comes in two forms:

| | **Web app** (this website) | **DiscKit** (Mac app) |
|---|---|---|
| How much | a few hundred articles you choose | all of English Wikipedia |
| Where the "discs" are | simulated: a database (text) and file storage (images) | real folders, then real burned M-DISCs |
| Output | two `.iso` disc images to download | two discs burned directly, both at once |

---

## 2. The web app, step by step

### 2.1 Getting articles from Wikipedia
`backend/wikipedia_api.py` asks Wikipedia's public website for four things:
1. a **summary** (official title, one-line description, main picture),
2. the article as **plain text**, with headings written like `== History ==`,
3. a **list of images** used in the article,
4. the **links** to other articles (used to find related pages).

Wikipedia limits how fast you may ask. If it replies "slow down" (HTTP 429), the code waits and tries
again, waiting longer each time.

### 2.2 Turning text into a page
`backend/article_text.py`:
- `split_into_sections` turns the plain text into an introduction plus sections ("Early life",
  "Career"…). It drops end-of-page lists such as *References* and *External links*.
- `add_article_links` finds the first mention of any **other archived article** in the text and turns it
  into a link. That is what makes the offline copy feel like the web: you can click from *Jupiter* to
  *Solar System*.

### 2.3 Filling the two discs
`backend/archive_builder.py` does the downloading:

```
 title ──► fetch summary + text + up to 3 images
             │                       │
             ▼                       ▼
     TEXT DISC (MongoDB        MEDIA DISC (object storage;
     collection "text_disk")   index in "media_disk")
```

- **Starter archive**: the first time you open the site, 18 well-known articles are downloaded.
- **Grow the archive**: on the Burn page, you pick a topic (Space, History…) and a target size. The code
  reads the links of that topic's "root" articles and counts which pages are linked most often. It
  downloads those first, so the archive ends up tightly interlinked. Topics live in `backend/topics.py`.
- When it finishes, every article is re-linked (`relink_all_articles`) so new arrivals get linked too.

Progress is kept in a small dictionary called **progress**, which the website polls every couple of
seconds.

### 2.4 Reading it in the browser
The website (`frontend/src`) asks the backend for data at addresses beginning with `/api`:

| Screen | File | Uses |
|---|---|---|
| Home (grid of articles) | `pages/Portal.js` | `/api/articles` |
| Article reader | `pages/Article.js` | `/api/articles/<name>`, `/api/media/<id>` |
| Burn to Disc | `pages/Burn.js` + `components/burn/*` | `/api/seed/*`, `/api/burn/*`, `/api/disks/status` |
| Source code | `pages/Source.js` + `components/source/*` | `/api/source/*` |

The **Disk Monitor** sidebar (`components/DiskMonitor.js`) flickers each drive's light when that drive
is being read. `context/DiskContext.js` keeps track of this for the whole site: reading an article
lights drive 0, and loading a picture (`components/MediaImage.js`) lights drive 1.

### 2.5 Burning to disc
`backend/disc_site.py` writes the archive as a **plain offline website**: one HTML page per article
plus an `index.html` home page. Pages on the Text Disc point to pictures at `../media/<id>.jpg`, which
lives on the Media Disc.

`backend/disc_images.py` packs each half into an **ISO 9660** disc image, the standard format every
computer can read. It then records a **SHA-256 checksum** for each image: a fingerprint you can compare
after burning to prove the disc is a perfect copy. The **Preview** button shows the same pages, served
straight from the server, so you can try them before burning.

```
 Text Disc data ──► disc_site.py ──► articles/*.html, index.html ──► disc_images.py ──► offline-wiki-text.iso
 Media Disc data ─────────────────► media/*.jpg, manifest.json ────► disc_images.py ──► offline-wiki-media.iso
                                                                     + SHA256SUMS
```

### 2.6 How the backend is organised
`backend/server.py` only wires the pieces together. Each other file has one job:

| File | Job |
|---|---|
| `config.py` | database connection, logging, disc size (100 GB) |
| `wikipedia_api.py` | talking to Wikipedia |
| `article_text.py` | text → sections, adding links |
| `topics.py` | starter articles and themes |
| `archive_builder.py` | downloading into the two discs |
| `media_storage.py` | the image store (Media Disc) |
| `disc_site.py` | the offline website's pages |
| `disc_images.py` | building `.iso` images |
| `routes/*.py` | the web addresses, grouped: `articles`, `archive`, `burn`, `kit`, `source` |

---

## 3. DiscKit: all of Wikipedia on two discs

Downloading 7 million articles one by one would take months. Instead DiscKit starts from a **Kiwix
`.zim` file**: the whole of Wikipedia already bundled in one download (about 110 GB, with small
thumbnail images).

### 3.1 Splitting
`disckit/disckit/builder.py` walks through every entry in the file and asks `rules.py` where it belongs:

| Goes to the **Text Disc** | Goes to the **Media Disc** |
|---|---|
| article pages (HTML), styles (CSS), scripts, redirects | images, drawings (SVG), audio, video, fonts, PDFs |

The same works for **any folder of files** (`sources/folder.py`) and for **whole websites**
(`sources/website.py`, which follows links on one site and rewrites them to work offline). Adding a new
kind of source means writing one small file in `sources/`.

### 3.2 How a disc is laid out
`disckit/disckit/volume.py` writes each disc as:

```
DISCKIT.json     what this disc is (Text or Media, which set it belongs to, main page)
index.db         a small database: where every file is, plus titles and the search index
packs/pack-00000.bin, pack-00001.bin …   the actual data, in 1 GB chunks
SHA256SUMS       fingerprints of every file, to check the burned disc
```

Text is grouped into 1 MB bundles and **compressed** (zstd), which shrinks Wikipedia's HTML to roughly a
tenth of its size. Pictures are stored as they are, because they're already compressed.

### 3.3 Full-text search
While building, `textindex.py` strips each page down to its words and adds them to a **full-text index**
(SQLite FTS5) on the Text Disc. When you search:
1. an article whose title exactly matches comes first,
2. then the rest are ranked by relevance (**bm25**: words in the title count more than words in the
   body; rare words count more than common ones),
3. for each result, the reader opens the article on the disc and cuts out a short excerpt with your
   words highlighted.

For all of English Wikipedia the index adds roughly 15–25 GB, which still fits on a 100 GB disc.
*Plan capacity* measures it for your file before you build.

### 3.4 Burning and reading
- `burn.py` uses the Mac's built-in disc tools (`drutil`, `hdiutil`) to burn **both discs at the same
  time** on two drives, using UDF (the filesystem Blu-ray discs need). It can also check a burned disc
  against its fingerprints.
- `reader/server.py` is the **Two-Drive Reader**: a tiny web server on your own Mac. It opens both discs
  and serves them together as one website, so a page's text comes from drive 1 and its pictures from
  drive 2. `reader/shell.html` is the Wikipedia-style frame around the pages, with search and the live
  Disc I/O monitor.
- `gui.py` is the desktop window with three tabs (Build, Burn, Read). `cli.py` does the same from the
  Terminal.

### 3.5 The Mac app
`disckit/packaging/macos/build_app.sh` turns DiscKit into a normal `DiscKit.app` (with its own icon)
inside a `.dmg` installer. GitHub runs it automatically on a Mac (`.github/workflows/disckit-macos.yml`).
Once Apple Developer secrets are added, the build also signs the app and gets Apple's approval
(**notarization**), so it opens with a plain double-click. See `disckit/packaging/macos/SIGNING.md`.

---

## 4. Safety notes
- The code contains no passwords or keys. Settings live in `.env` files, which are never shown on the
  Source page or included in downloads.
- Article text from Wikipedia is cleaned before it's put on a page (`DOMPurify` in the browser,
  escaping on the server), so it can't run scripts.
- The Source page only serves files from an allow-list of project folders.

## 5. Glossary
- **M-DISC**: a Blu-ray disc designed to last for centuries. This project assumes the 100 GB size.
- **ISO image**: a single file containing an exact copy of a disc, ready to burn.
- **Kiwix / .zim**: a project and file format for carrying websites like Wikipedia offline.
- **Checksum (SHA-256)**: a fingerprint of a file. If even one bit changes, the fingerprint changes.
- **API / endpoint**: a web address the website calls to fetch or change data, e.g. `/api/articles`.
- **Full-text index**: a lookup table from every word to the articles containing it, which makes search instant.
