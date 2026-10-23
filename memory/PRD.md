# PRD — Offline Wikipedia: Dual M-Disc Archive

## Original problem statement
Build an app with offline downloadable functionality that streams media from two
M-disc reader/writers (ASUS ZenDrive U9M) simultaneously. Demonstrate by putting
Wikipedia TEXT on one M-disc (Verbatim 100GB) and Wikipedia MEDIA on a second,
then "play" both simultaneously to recreate the Wikipedia web browsing experience
entirely offline — hosting the site from the discs instead of the internet.

## User choices
- Software demonstration now, clear path to swap in real drives later.
- Two logical data stores: **Text Disk** (article text) + **Media Disk** (images).
- Fetch ~15-20 real Wikipedia articles via the Wikipedia API.
- Authentic Wikipedia look.
- A closable Disk Monitor sidebar, Wikipedia experience stays the main focus.

## Architecture
- **Text Disk** = MongoDB `text_disk` collection (article slug, title, description,
  lead_html, sections[], media refs, size_bytes).
- **Media Disk** = Emergent Object Storage (`offline-wiki/media/...`), reference rows
  in Mongo `media_disk` (with Mongo-inline fallback if object storage is unavailable).
- Backend FastAPI (`/app/backend/server.py`): `/api/seed`, `/api/seed/status`,
  `/api/articles`, `/api/articles/{slug}`, `/api/search`, `/api/media/{id}`,
  `/api/disks/status`. Seeding fetches Wikipedia summary + plain-text extract
  (`exsectionformat=wiki`) parsed into sections, plus images via media-list; throttled
  with 429/503 retry+backoff. Cross-article links injected via `data-wikilink`.
- Frontend React: Portal (Main-Page style home), Article (serif reading view with TOC,
  infobox, inline media, streaming phases), DiskMonitor (black terminal sidebar with two
  drives + live I/O log), SearchBox autocomplete, DiskContext (session read stats/LEDs).
- Seed state derived from DB counts so it survives restarts.

## User personas
- Archivist / hobbyist building a long-lived offline knowledge vault on M-DISC.
- Visitor browsing Wikipedia with zero internet, from the two discs.

## Core requirements (static)
- Dual-source playback: text from Drive 0, media from Drive 1, visibly simultaneous.
- Authentic Wikipedia reading experience with working cross-article navigation.
- Everything served offline at read time (no internet calls once seeded).

## Implemented (2026-06)
- Full dual-disk offline Wikipedia demo: initial 18 seeded articles, images on Media Disk.
- Portal, article reader, autocomplete search, cross-article links.
- Disk Monitor sidebar with per-drive status, capacity, session byte counters, I/O log.
- **Bigger Archive**: link-graph crawl (`/api/seed/expand`) that ranks the most densely
  interlinked real Wikipedia pages (identifier/list pages filtered out) and seeds up to
  ~hundreds; corpus-wide cross-links rebuilt from raw text (`_relinkify_all`). Articles are
  readable immediately on seed; links finalize when the run completes. UI: slider + progress
  on the Burn page.
- **Burn to Disc** (`/burn` tab): builds two real ISO 9660 (Joliet+RockRidge) disc images via
  pycdlib — Text Disc (browsable offline site: index.html + per-article pages cross-linked +
  data JSON + CSS) and Media Disc (all images + manifest). Stored to object storage, streamed
  via `/api/burn/download/{text|media}` with proper Content-Disposition. Verified valid ISOs.
- Verified: backend 9/9 tests (first MVP), feature endpoints + ISO validity + UI via curl/screenshots.

## Backlog / future (P1/P2)
- P1: Real-hardware adapter — replace Text/Media Disk data access with reads from two
  mounted M-DISC volumes (ASUS ZenDrive) via a local bridge; keep the same API.
- P1: Larger/selectable article set and an in-app "burn to disc" (export) flow.
- P2: Full-text search across body (not just titles); offline PWA packaging.
- P2: Richer infoboxes/tables from Wikipedia and inter-wiki link coverage beyond the set.

## Next tasks
- Await user feedback; optionally expand the seeded corpus or add hardware bridge.

## Iteration 2 (2026-06) — capacity, checksums, themes, preview
- **Checksum Manifest**: burn computes SHA-256 of each ISO, shown on disc cards (copy) and
  downloadable as `SHA256SUMS` via `/api/burn/checksums`; verified it matches the ISO byte-for-byte.
- **Disc Capacity Planner**: `/api/disks/status` returns a `capacity` block (avg item size,
  est items per 100 GB disc, headroom, fill %, over-capacity + largest-media warnings). UI card
  on the Burn page with a warning banner when a disc exceeds 100 GB.
- **Pick Topics**: theme presets (`/api/seed/themes`); `/api/seed/expand?theme=` seeds a tightly
  interlinked web around one subject (roots from the theme). UI theme chips.
- **Combined Preview**: `/api/preview/*` serves the generated Text + Media disc content together
  (index.html, per-article pages, assets, media) so the offline site is browsable before burning.
  "Preview" buttons open it in a new tab. Verified index + article render with images loaded.

## Roadmap update (Jun 2026) – Full English Wikipedia goal
- User confirmed: explanation only for now, no code changes.
- Target: English Wikipedia; Media Disk = Kiwix-style WebP thumbnails (~55-60 GB); Text Disk = all articles + references (~50-60 GB, nopic).
- Blockers in current app: live API crawling too slow (use Wikimedia/Kiwix dumps), cloud pod can't hold 100GB+, ISO9660 -> need UDF for BDXL, full-res images, browser download of 100GB ISO impractical.
- Future (P1): local CLI pipeline (dump -> text disc + media disc), offline two-drive reader, UDF image builder, capacity planner for full dump.
- Future (P2): multi-disc spanning (higher-res media across N discs); generalize the dual/multi-disc system for other applications (not just Wikipedia).

## DiscKit for macOS (Jun 2026) — DONE
Location: /app/disckit (downloadable zip via GET /api/kit/download, info at /api/kit/info; Burn page "DiscKit for Mac" section in components/KitSection.js)
- Local Archive Builder: Tkinter desktop app (gui.py) + CLI (python -m disckit plan|build|read|drives|image|burn|verify|gui)
- Sources (universal): Kiwix .zim (libzim), any folder, website crawler (same host + external assets, robots.txt, link rewriting)
- Disc format disckit/1: DISCKIT.json, index.db (SQLite entries/redirects/titles), packs/pack-NNNNN.bin (<=1GiB), SHA256SUMS; text + SVG compressed in 1MB zstd clusters; images raw; set_id + disc_index/disc_count ready for spanning
- Rules: text/html/css/js -> Text Disc; image/audio/video/font/pdf -> Media Disc
- Burn (macOS): drutil burn -udf both drives in parallel, hdiutil makehybrid UDF .iso, verify against SHA256SUMS
- Two-Drive Reader: stdlib threaded HTTP server serving union of both discs at root, Wikipedia-style shell at /_disckit/ with search, random, closable live Disc I/O monitor
- Tested: iteration_2 (all issues fixed: non-empty folder rejection, pre-validation, friendly CLI errors, website key dedup, testids, kit whitelist)
## Backlog
- P1 Multi-disc spanning (N discs, higher-res media)
- P2 Full-text search on Text Disc; package as signed .app

## Code review fixes (Jun 2026) — DONE (iteration_3, 100% frontend)
- DOMPurify sanitizes article HTML; Article useEffect deps fixed; nested ternaries removed (Burn, KitSection); empty catches log warnings
- Verified false positives: server.py `is` comparisons (all `is None`), `data` at server.py:333, DiskContext/Burn hook deps
- Deferred: large refactors (split Burn.js / Portal.js / server.py _run_burn)
- Open security audit items: SEC-001 rate-limit/cap /api/burn & /api/seed/expand; SEC-002 CORS allowlist
