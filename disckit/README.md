# DiscKit for macOS

Split an archive across a **Text Disc** and a **Media Disc**, burn both on two M-DISC drives at once, then
read them together: every page comes from drive 1 while its images stream from drive 2.

Works with any **Kiwix .zim file** (full English Wikipedia, Wiktionary, Stack Exchange, Gutenberg…), any
**folder of files**, or a **website** copied from the internet.

## 1. Install
**Easiest — DiscKit.app (no Python needed, Apple Silicon):**
1. Open `DiscKit-<version>-macOS-arm64.dmg` and drag **DiscKit** into Applications.
2. First launch only (the app isn't signed by Apple yet):
   macOS 14 and earlier: right-click DiscKit → Open → Open.
   macOS 15+: double-click, press Done, then System Settings → Privacy & Security → **Open Anyway**.

Where the .dmg comes from: this repo contains `.github/workflows/disckit-macos.yml`. After "Save to GitHub",
GitHub's own Macs build the app automatically — open your repo → **Actions** → *Build DiscKit.app (macOS)* →
latest run → download **DiscKit-macOS-arm64**. Push a tag like `disckit-v1.1.0` to also publish it as a Release.
To build it yourself on a Mac: `bash packaging/macos/build_app.sh` (output in `dist/`).
To sign and notarize the app so it opens with a plain double-click, follow `packaging/macos/SIGNING.md`.
Without those secrets the build still works and makes an unsigned app.

**Alternative — run from source:** double-click **install.command** (needs Python 3.10+ with Tk 8.6, from
python.org or `brew install python python-tk`), then **DiscKit.command**.

## 2. Get English Wikipedia
Download the full English Wikipedia with images (~110 GB) from the Kiwix library:
<https://download.kiwix.org/zim/wikipedia/> → newest `wikipedia_en_all_maxi_YYYY-MM.zim`.
To try things quickly first, grab a small one such as `wikipedia_en_ray-charles_maxi_*.zim` (3 MB).

## 3. Build both discs
Double-click **DiscKit.command** → tab **1 Build discs**
- Source: *Kiwix file*, choose the `.zim`.
- Pick two **empty** staging folders, ideally on an external SSD with ~200 GB free.
- Disc size: *100 GB M-DISC BDXL*.
- Press **Plan capacity** to check both discs fit, then **Build both discs**.
  Full English Wikipedia takes a few hours; progress and an estimate are shown live.

What goes where (automatic, by file type):
| Text Disc (drive 1) | Media Disc (drive 2) |
|---|---|
| HTML articles + references, CSS, JavaScript, redirects, search index | images (WebP/JPEG/PNG/GIF), SVG, audio, video, fonts, PDFs |

**Full-text search** (on by default): every word of every article is indexed on the Text Disc
(SQLite FTS5). For full English Wikipedia that adds roughly 15–25 GB — *Plan capacity* measures it for your file.
Text is compressed in 1 MB clusters with zstd. Each disc gets `DISCKIT.json`, `index.db`,
`packs/pack-NNNNN.bin` (≤ 1 GB each) and a `SHA256SUMS` file.

## 4. Burn
Tab **2 Burn** → *Detect drives* → choose a drive for each disc → **Burn both discs at once**.
Both burners run in parallel (macOS `drutil`, UDF filesystem, verify + eject).
*Make .iso images…* creates UDF disc images instead, if you'd rather burn with another tool.
*Verify a mounted disc…* re-checks every file against `SHA256SUMS`.

## 5. Read from both drives
Insert both discs, then either tab **3 Read** → *Find discs in /Volumes* → **Start reading in browser**,
or double-click **Read Discs.command**. Your browser opens a Wikipedia-style reader. Type to jump to a title, or press **Enter** to search
every word: results show the best matches first with your words highlighted. Also:
random article, and a live **Disc I/O monitor** that shows each drive spinning as it's read.

## Command line
```
.venv/bin/python -m disckit plan  zim wikipedia_en_all_maxi.zim
.venv/bin/python -m disckit build zim wikipedia_en_all_maxi.zim --text-out /Volumes/SSD/TEXT --media-out /Volumes/SSD/MEDIA --label WIKI
.venv/bin/python -m disckit build website https://example.org --max-pages 2000 --text-out T --media-out M
.venv/bin/python -m disckit build folder ~/Archive --text-out T --media-out M --disc-gb 25
.venv/bin/python -m disckit drives
.venv/bin/python -m disckit burn /Volumes/SSD/TEXT --drive 1
.venv/bin/python -m disckit verify /Volumes/WIKI_TEXT
.venv/bin/python -m disckit read                 # auto-detects mounted discs
# (with the app installed, use /Applications/DiscKit.app/Contents/MacOS/DiscKit instead of .venv/bin/python -m disckit)
```

## Extending
Sources live in `disckit/sources/` — subclass `Source`, yield `Item`s, register it in `open_source`.
The disc format records `disc_index`/`disc_count`, ready for multi-disc spanning later.
