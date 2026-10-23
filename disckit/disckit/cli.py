"""Command line: python -m disckit <plan|build|read|drives|image|burn|verify|gui>"""

import argparse
import sys
import threading

from . import __version__
from .builder import Progress, build, plan
from .rules import Rules
from .sources import open_source
from .volume import GB, DiscFullError


def _source(a):
    opts = {}
    if a.source == "website":
        opts = dict(max_pages=a.max_pages, max_depth=a.max_depth, delay=a.delay,
                    external_assets=not a.no_external)
    return open_source(a.source, a.target, **opts)


def _add_source_args(p):
    p.add_argument("source", choices=["zim", "folder", "website"])
    p.add_argument("target", help=".zim file, folder path, or website URL")
    p.add_argument("--disc-gb", type=int, default=100, help="capacity of each disc (default 100)")
    p.add_argument("--svg-on-text", action="store_true", help="keep SVG drawings on the Text Disc")
    p.add_argument("--max-pages", type=int, default=500)
    p.add_argument("--max-depth", type=int, default=5)
    p.add_argument("--delay", type=float, default=0.5, help="seconds between website requests")
    p.add_argument("--no-external", action="store_true", help="don't copy images/CSS hosted on other domains")
    p.add_argument("--no-fulltext", action="store_true", help="skip the full-text search index")


def main(argv=None):
    try:
        return _main(argv)
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, RuntimeError, DiscFullError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _main(argv=None):
    ap = argparse.ArgumentParser(prog="disckit", description=f"DiscKit {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("plan", help="estimate how full each disc will be")
    _add_source_args(p)

    p = sub.add_parser("build", help="split a source into a Text Disc and a Media Disc")
    _add_source_args(p)
    p.add_argument("--text-out", required=True)
    p.add_argument("--media-out", required=True)
    p.add_argument("--label", default="DISCKIT")

    p = sub.add_parser("read", help="read both discs together in your browser")
    p.add_argument("discs", nargs="*", help="disc folders or mounted volumes (default: auto-detect in /Volumes)")
    p.add_argument("--port", type=int, default=8800)
    p.add_argument("--no-browser", action="store_true")

    sub.add_parser("drives", help="list optical drives (macOS)")
    p = sub.add_parser("image", help="make a UDF .iso from a staged disc folder (macOS)")
    p.add_argument("disc_dir"); p.add_argument("out_iso"); p.add_argument("--name", default="DISCKIT")
    p = sub.add_parser("burn", help="burn a disc folder or .iso to a drive (macOS)")
    p.add_argument("path"); p.add_argument("--drive", type=int, required=True)
    p = sub.add_parser("verify", help="check a disc against its SHA256SUMS")
    p.add_argument("disc")
    sub.add_parser("gui", help="open the desktop app")

    a = ap.parse_args(argv)
    if a.cmd in (None, "gui"):
        from .gui import run
        return run()

    if a.cmd == "plan":
        r = plan(_source(a), Rules(a.svg_on_text), a.disc_gb, fulltext=not a.no_fulltext)
        if not r["estimable"]:
            print(r["note"]); return
        for role in ("text", "media"):
            d = r[role]
            print(f"{role.title():5} Disc: {d['items']:>10,} items  ~{d['est_bytes'] / GB:8.2f} GB  "
                  f"({d['fill_pct']:5.1f}% of {a.disc_gb} GB)  {'fits' if d['fits'] else 'DOES NOT FIT'}")
        print(f"Redirects: {r['redirects']:,}   skipped: {r['skipped']:,}   "
              f"search index: ~{r['text']['fulltext_bytes'] / GB:.2f} GB (included in Text Disc)")
        return

    if a.cmd == "build":
        prog = Progress()
        done = threading.Event()

        def ticker():
            while not done.wait(2):
                s = prog.snapshot()
                sys.stderr.write(f"\r{s['done']:,}/{s['total']:,}  text {s['text_bytes'] / GB:.3f} GB  "
                                 f"media {s['media_bytes'] / GB:.3f} GB  {s['rate']:.0f}/s   ")
        threading.Thread(target=ticker, daemon=True).start()
        try:
            build(_source(a), a.text_out, a.media_out, a.disc_gb, Rules(a.svg_on_text), a.label, prog,
                  fulltext=not a.no_fulltext)
        finally:
            done.set(); sys.stderr.write("\n")
        return

    if a.cmd == "read":
        from .burn import find_discs
        from .reader.server import ReaderServer
        discs = a.discs or [str(p) for p in find_discs()]
        srv = ReaderServer(discs, port=a.port)
        print(f"Reading {len(discs)} disc(s) at {srv.url}  (Ctrl+C to stop)")
        try:
            srv.serve_forever(open_browser=not a.no_browser)
        except KeyboardInterrupt:
            pass
        return

    from . import burn as b
    if a.cmd == "drives":
        for i, d in b.list_drives():
            print(i, d)
    elif a.cmd == "image":
        b.make_image(a.disc_dir, a.out_iso, a.name)
    elif a.cmd == "burn":
        b.burn(a.path, a.drive)
    elif a.cmd == "verify":
        ok, bad = b.verify(a.disc)
        sys.exit(1 if bad else 0)
