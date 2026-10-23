"""DiscKit desktop app (Tkinter, ships with Python on macOS)."""

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__
from . import burn as burner
from .builder import DISC_SIZES_GB, Progress, build, plan
from .rules import Rules
from .sources import open_source
from .volume import GB

SETTINGS = Path.home() / ".disckit.json"
TEXT_C, MEDIA_C = "#15803d", "#b45309"


def human(b):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1000 or unit == "TB":
            return f"{b:.1f} {unit}" if unit != "B" else f"{int(b)} B"
        b /= 1000


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"DiscKit {__version__} — Text Disc + Media Disc")
        self.geometry("880x760")
        self.minsize(780, 640)
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.progress = None
        self.reader = None
        self.s = self._load_settings()
        self.v = {k: tk.StringVar(value=str(self.s.get(k, d))) for k, d in {
            "kind": "zim", "target": "", "text_out": "", "media_out": "", "disc": "100 GB M-DISC BDXL",
            "label": "WIKIPEDIA", "max_pages": 500, "max_depth": 5, "delay": 0.5,
            "burn_text": "", "burn_media": "", "drive_text": "", "drive_media": "",
            "read_text": "", "read_media": "", "port": 8800}.items()}
        self.svg = tk.BooleanVar(value=self.s.get("svg", False))
        self.external = tk.BooleanVar(value=self.s.get("external", True))
        self.fulltext = tk.BooleanVar(value=self.s.get("fulltext", True))
        self.verify_after = tk.BooleanVar(value=True)
        self._ui()
        self.after(150, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # ---------- plumbing ----------
    def _load_settings(self):
        try:
            return json.loads(SETTINGS.read_text())
        except Exception:
            return {}

    def _save_settings(self):
        data = {k: v.get() for k, v in self.v.items()}
        data.update(svg=self.svg.get(), external=self.external.get(), fulltext=self.fulltext.get())
        try:
            SETTINGS.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def log(self, msg):
        self.q.put(("log", str(msg)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", payload + "\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "call":
                    payload()
        except queue.Empty:
            pass
        if self.progress:
            self._show_progress(self.progress.snapshot())
        if self.reader:
            self._show_io()
        self.after(300, self._drain)

    def ui(self, fn):
        self.q.put(("call", fn))

    def _thread(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _quit(self):
        self._save_settings()
        if self.reader:
            self.reader.stop()
        self.destroy()

    def _row(self, parent, label, var, browse=None, width=52):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=3)
        ttk.Label(f, text=label, width=16).pack(side="left")
        e = ttk.Entry(f, textvariable=var, width=width)
        e.pack(side="left", fill="x", expand=True)
        b = None
        if browse:
            b = ttk.Button(f, text="Choose…", command=browse)
            b.pack(side="left", padx=(6, 0))
        return e, b

    def _pick_dir(self, var, title):
        def f():
            d = filedialog.askdirectory(title=title)
            if d:
                var.set(d)
        return f

    # ---------- layout ----------
    def _ui(self):
        head = ttk.Frame(self, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        ttk.Label(head, text="DiscKit", font=("Georgia", 22)).pack(side="left")
        ttk.Label(head, text="  Split an archive across a Text Disc and a Media Disc, burn both, read both at once.",
                  foreground="#54595d").pack(side="left", pady=(8, 0))
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=6)
        for name, builder in (("1  Build discs", self._build_tab), ("2  Burn", self._burn_tab),
                              ("3  Read", self._read_tab)):
            frame = ttk.Frame(nb, padding=14)
            nb.add(frame, text=name)
            builder(frame)
        lf = ttk.LabelFrame(self, text="Activity", padding=6)
        lf.pack(fill="both", padx=12, pady=(0, 12))
        self.logbox = ScrolledText(lf, height=8, font=("Menlo", 11), state="disabled", wrap="word")
        self.logbox.pack(fill="both", expand=True)

    def _build_tab(self, t):
        src = ttk.LabelFrame(t, text="Source", padding=10)
        src.pack(fill="x")
        kinds = ttk.Frame(src)
        kinds.pack(fill="x", pady=(0, 6))
        for val, txt in (("zim", "Kiwix file (.zim) — e.g. full English Wikipedia"),
                         ("folder", "Folder of files"), ("website", "Website (copy from the internet)")):
            ttk.Radiobutton(kinds, text=txt, value=val, variable=self.v["kind"],
                            command=self._kind_changed).pack(side="left", padx=(0, 14))
        _, self.src_browse = self._row(src, "File / folder / URL", self.v["target"], self._browse_source)
        self.web = ttk.Frame(src)
        for lbl, key, lo, hi, inc in (("Max pages", "max_pages", 1, 1_000_000, 50),
                                      ("Link depth", "max_depth", 0, 50, 1),
                                      ("Delay (s)", "delay", 0, 10, 0.1)):
            ttk.Label(self.web, text=lbl).pack(side="left", padx=(0, 4))
            ttk.Spinbox(self.web, from_=lo, to=hi, increment=inc, textvariable=self.v[key],
                        width=8).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(self.web, text="Also copy images/CSS from other domains",
                        variable=self.external).pack(side="left")

        out = ttk.LabelFrame(t, text="Disc staging folders (each needs as much free space as the disc)",
                             padding=10)
        out.pack(fill="x", pady=10)
        self._row(out, "Text Disc folder", self.v["text_out"],
                  self._pick_dir(self.v["text_out"], "Empty folder for the Text Disc"))
        self._row(out, "Media Disc folder", self.v["media_out"],
                  self._pick_dir(self.v["media_out"], "Empty folder for the Media Disc"))
        opts = ttk.Frame(out)
        opts.pack(fill="x", pady=(6, 0))
        ttk.Label(opts, text="Disc size", width=16).pack(side="left")
        ttk.Combobox(opts, textvariable=self.v["disc"], values=list(DISC_SIZES_GB), state="readonly",
                     width=22).pack(side="left")
        ttk.Label(opts, text="   Disc label").pack(side="left")
        ttk.Entry(opts, textvariable=self.v["label"], width=14).pack(side="left", padx=4)
        opts2 = ttk.Frame(out)
        opts2.pack(fill="x", pady=(6, 0))
        ttk.Label(opts2, text="", width=16).pack(side="left")
        ttk.Checkbutton(opts2, text="Full-text search (index every word)", variable=self.fulltext).pack(side="left")
        ttk.Checkbutton(opts2, text="Keep SVG drawings on Text Disc", variable=self.svg).pack(side="left", padx=14)

        bar = ttk.Frame(t)
        bar.pack(fill="x")
        self.plan_btn = ttk.Button(bar, text="Plan capacity", command=self._plan)
        self.plan_btn.pack(side="left")
        self.build_btn = ttk.Button(bar, text="Build both discs", command=self._build)
        self.build_btn.pack(side="left", padx=8)
        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self.cancel.set, state="disabled")
        self.cancel_btn.pack(side="left")
        self.plan_lbl = ttk.Label(t, text="", foreground="#54595d", justify="left")
        self.plan_lbl.pack(fill="x", pady=(8, 4))

        prog = ttk.Frame(t)
        prog.pack(fill="x", pady=4)
        self.overall = ttk.Progressbar(prog, maximum=100)
        self.overall.pack(fill="x")
        self.status = ttk.Label(prog, text="Idle", foreground="#54595d")
        self.status.pack(anchor="w", pady=(2, 8))
        self.fill = {}
        for role, color in (("text", TEXT_C), ("media", MEDIA_C)):
            f = ttk.Frame(prog)
            f.pack(fill="x", pady=2)
            ttk.Label(f, text=f"{role.title()} Disc", foreground=color, width=12).pack(side="left")
            c = tk.Canvas(f, height=14, bg="#eaecf0", highlightthickness=0)
            c.pack(side="left", fill="x", expand=True)
            lbl = ttk.Label(f, text="0 B", width=26, anchor="e")
            lbl.pack(side="left")
            self.fill[role] = (c, lbl, color)
        self._kind_changed()

    def _burn_tab(self, t):
        d = ttk.LabelFrame(t, text="Drives (connect both M-DISC burners)", padding=10)
        d.pack(fill="x")
        top = ttk.Frame(d)
        top.pack(fill="x")
        ttk.Button(top, text="Detect drives", command=self._detect).pack(side="left")
        self.drives_lbl = ttk.Label(top, text="  Not scanned yet", foreground="#54595d")
        self.drives_lbl.pack(side="left")
        self.drive_boxes = []
        for role, var_path, var_drive in (("Text", "burn_text", "drive_text"), ("Media", "burn_media", "drive_media")):
            f = ttk.LabelFrame(t, text=f"{role} Disc", padding=10)
            f.pack(fill="x", pady=6)
            self._row(f, "Folder or .iso", self.v[var_path], self._pick_burn_src(self.v[var_path]))
            r = ttk.Frame(f)
            r.pack(fill="x", pady=3)
            ttk.Label(r, text="Burn on drive", width=16).pack(side="left")
            cb = ttk.Combobox(r, textvariable=self.v[var_drive], state="readonly", width=48)
            cb.pack(side="left")
            self.drive_boxes.append(cb)
        b = ttk.Frame(t)
        b.pack(fill="x", pady=6)
        ttk.Checkbutton(b, text="Verify after burning", variable=self.verify_after).pack(side="left")
        ttk.Button(b, text="Burn both discs at once", command=self._burn_both).pack(side="left", padx=10)
        ttk.Button(b, text="Make .iso images…", command=self._make_isos).pack(side="left")
        ttk.Button(b, text="Verify a mounted disc…", command=self._verify).pack(side="left", padx=10)
        ttk.Label(t, foreground="#54595d", wraplength=780, justify="left", text=(
            "Tip: the folders default to the ones you just built. Burning writes a UDF filesystem, which "
            "handles 100 GB BDXL M-DISCs. Label the discs TEXT and MEDIA after they eject.")).pack(fill="x", pady=6)

    def _read_tab(self, t):
        f = ttk.LabelFrame(t, text="Discs to read", padding=10)
        f.pack(fill="x")
        self._row(f, "Drive 1 · Text", self.v["read_text"], self._pick_dir(self.v["read_text"], "Text Disc"))
        self._row(f, "Drive 2 · Media", self.v["read_media"], self._pick_dir(self.v["read_media"], "Media Disc"))
        r = ttk.Frame(f)
        r.pack(fill="x", pady=(6, 0))
        ttk.Button(r, text="Find discs in /Volumes", command=self._autodetect).pack(side="left")
        ttk.Button(r, text="Use the folders I just built", command=self._use_built).pack(side="left", padx=8)
        ttk.Label(r, text="Port").pack(side="left", padx=(20, 4))
        ttk.Spinbox(r, from_=1024, to=65535, textvariable=self.v["port"], width=7).pack(side="left")
        b = ttk.Frame(t)
        b.pack(fill="x", pady=10)
        self.start_btn = ttk.Button(b, text="Start reading in browser", command=self._start_reader)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(b, text="Stop", command=self._stop_reader, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.url_lbl = ttk.Label(b, text="", foreground="#3366cc", cursor="hand2")
        self.url_lbl.pack(side="left", padx=8)
        self.url_lbl.bind("<Button-1>", lambda e: self.reader and __import__("webbrowser").open(self.reader.url))
        io = ttk.LabelFrame(t, text="Live disc activity", padding=10)
        io.pack(fill="x")
        self.io_lbls = []
        for color in (TEXT_C, MEDIA_C):
            lbl = ttk.Label(io, text="—", foreground=color, font=("Menlo", 11))
            lbl.pack(anchor="w", pady=2)
            self.io_lbls.append(lbl)

    # ---------- build ----------
    def _kind_changed(self):
        web = self.v["kind"].get() == "website"
        if web:
            self.web.pack(fill="x", pady=(6, 0))
            self.src_browse.configure(state="disabled")
        else:
            self.web.pack_forget()
            self.src_browse.configure(state="normal")

    def _browse_source(self):
        if self.v["kind"].get() == "zim":
            p = filedialog.askopenfilename(title="Choose a Kiwix .zim file", filetypes=[("Kiwix ZIM", "*.zim")])
        else:
            p = filedialog.askdirectory(title="Choose a folder")
        if p:
            self.v["target"].set(p)

    def _make_source(self):
        kind, target = self.v["kind"].get(), self.v["target"].get().strip()
        if not target:
            raise ValueError("Choose a source first.")
        opts = {}
        if kind == "website":
            opts = dict(max_pages=int(float(self.v["max_pages"].get())),
                        max_depth=int(float(self.v["max_depth"].get())),
                        delay=float(self.v["delay"].get()), external_assets=self.external.get(), log=self.log)
        return open_source(kind, target, **opts)

    def _disc_gb(self):
        return DISC_SIZES_GB.get(self.v["disc"].get(), 100)

    def _busy(self, on):
        st = "disabled" if on else "normal"
        self.plan_btn.configure(state=st)
        self.build_btn.configure(state=st)
        self.cancel_btn.configure(state="normal" if on else "disabled")

    def _plan(self):
        self._save_settings()
        self.cancel.clear()
        self._busy(True)
        self.plan_lbl.configure(text="Scanning source…")

        def work():
            try:
                r = plan(self._make_source(), Rules(self.svg.get()), self._disc_gb(), cancel=self.cancel,
                         fulltext=self.fulltext.get())
                if not r["estimable"]:
                    txt = r["note"]
                else:
                    t, m = r["text"], r["media"]
                    txt = (f"Text Disc: {t['items']:,} items, ~{human(t['est_bytes'])} "
                           f"({t['fill_pct']:.1f}% — {'fits' if t['fits'] else 'DOES NOT FIT'}; "
                           f"text compresses to {t['compression_ratio'] * 100:.0f}%"
                           + (f"; incl. ~{human(t['fulltext_bytes'])} search index" if t["fulltext_bytes"] else "")
                           + ")\n"
                           f"Media Disc: {m['items']:,} items, ~{human(m['est_bytes'])} "
                           f"({m['fill_pct']:.1f}% — {'fits' if m['fits'] else 'DOES NOT FIT'})   "
                           f"· {r['redirects']:,} redirects")
                self.ui(lambda: self.plan_lbl.configure(text=txt))
                self.log(txt)
            except Exception as e:
                self.log(f"Plan failed: {e}")
                self.ui(lambda e=e: self.plan_lbl.configure(text=f"Plan failed: {e}"))
            finally:
                self.ui(lambda: self._busy(False))
        self._thread(work)

    def _build(self):
        text_out, media_out = self.v["text_out"].get().strip(), self.v["media_out"].get().strip()
        if not text_out or not media_out:
            return messagebox.showwarning("DiscKit", "Choose a folder for each disc.")
        if Path(text_out).resolve() == Path(media_out).resolve():
            return messagebox.showwarning("DiscKit", "The Text and Media discs need different folders.")
        self._save_settings()
        self.cancel.clear()
        self._busy(True)
        self.progress = Progress()

        def work():
            try:
                build(self._make_source(), text_out, media_out, self._disc_gb(), Rules(self.svg.get()),
                      self.v["label"].get().strip().upper() or "DISCKIT", self.progress, self.log, self.cancel,
                      fulltext=self.fulltext.get())

                def after():
                    self.v["burn_text"].set(text_out)
                    self.v["burn_media"].set(media_out)
                    self.v["read_text"].set(text_out)
                    self.v["read_media"].set(media_out)
                self.ui(after)
            except Exception as e:
                self.log(f"Build failed: {e}")
                self.ui(lambda e=e: messagebox.showerror("DiscKit", str(e)))
            finally:
                self.ui(lambda: self._busy(False))
        self._thread(work)

    def _show_progress(self, s):
        pct = (s["done"] / s["total"] * 100) if s["total"] else 0
        self.overall["value"] = 100 if s["phase"] == "done" else pct
        eta = ""
        if s["phase"] == "building" and s["rate"] > 0 and s["total"] > s["done"]:
            mins = (s["total"] - s["done"]) / s["rate"] / 60
            eta = f" · ~{mins:.0f} min left" if mins >= 1 else " · <1 min left"
        self.status.configure(text=f"{s['phase'].title()} · {s['done']:,}/{s['total']:,} entries · "
                                   f"{s['rate']:.0f}/s{eta} · {s['current'][:60]}")
        cap = self._disc_gb() * GB
        for role in ("text", "media"):
            c, lbl, color = self.fill[role]
            used = s[f"{role}_bytes"]
            c.delete("all")
            w = max(c.winfo_width(), 1)
            c.create_rectangle(0, 0, max(w * min(used / cap, 1), 2 if used else 0), 14, fill=color, width=0)
            lbl.configure(text=f"{human(used)} · {s[f'{role}_items']:,} items · {used / cap * 100:.2f}%")
        if s["phase"] in ("done", "error"):
            self.progress = None

    # ---------- burn ----------
    def _pick_burn_src(self, var):
        def f():
            p = filedialog.askdirectory(title="Staged disc folder (or cancel to pick an .iso)")
            if not p:
                p = filedialog.askopenfilename(title="Disc image", filetypes=[("Disc image", "*.iso")])
            if p:
                var.set(p)
        return f

    def _detect(self):
        def work():
            try:
                drives = burner.list_drives()
                names = [f"{i}: {d}" for i, d in drives]

                def show():
                    for cb in self.drive_boxes:
                        cb.configure(values=names)
                    if len(names) >= 1 and not self.v["drive_text"].get():
                        self.v["drive_text"].set(names[0])
                    if len(names) >= 2 and not self.v["drive_media"].get():
                        self.v["drive_media"].set(names[1])
                    self.drives_lbl.configure(text=f"  {len(names)} drive(s) found")
                self.ui(show)
                for n in names:
                    self.log(f"Drive {n}")
            except Exception as e:
                self.log(f"Drive scan failed: {e}")
        self._thread(work)

    def _burn_both(self):
        jobs = []
        for role, pv, dv in (("Text", "burn_text", "drive_text"), ("Media", "burn_media", "drive_media")):
            path, drive = self.v[pv].get().strip(), self.v[dv].get().strip()
            if path and drive:
                jobs.append((role, path, int(drive.split(":")[0])))
        if not jobs:
            return messagebox.showwarning("DiscKit", "Pick a folder and a drive for at least one disc.")
        if len(jobs) == 2 and jobs[0][2] == jobs[1][2]:
            return messagebox.showwarning("DiscKit", "Choose two different drives to burn both discs at once.")
        if not messagebox.askyesno("DiscKit", "Insert blank M-DISCs in the selected drives, then press Yes to burn."):
            return
        self._save_settings()
        for role, path, drive in jobs:
            def work(role=role, path=path, drive=drive):
                try:
                    burner.burn(path, drive, log=lambda m: self.log(f"[{role}] {m}"),
                                verify=self.verify_after.get())
                    self.log(f"[{role}] Burn complete.")
                except Exception as e:
                    self.log(f"[{role}] Burn failed: {e}")
            self._thread(work)

    def _make_isos(self):
        out = filedialog.askdirectory(title="Where should the .iso images go?")
        if not out:
            return
        label = self.v["label"].get().strip().upper() or "DISCKIT"

        def work():
            for role, pv in (("TEXT", "burn_text"), ("MEDIA", "burn_media")):
                src = self.v[pv].get().strip()
                if not src or src.endswith(".iso"):
                    continue
                try:
                    iso = burner.make_image(src, Path(out) / f"{label}_{role}.iso", f"{label}_{role}", self.log)
                    self.log(f"Created {iso}")
                except Exception as e:
                    self.log(f"Image failed ({role}): {e}")
        self._thread(work)

    def _verify(self):
        d = filedialog.askdirectory(title="Choose a mounted disc (or staged folder)", initialdir="/Volumes")
        if d:
            self._thread(lambda: self._safe(lambda: burner.verify(d, self.log)))

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:
            self.log(f"Error: {e}")

    # ---------- read ----------
    def _autodetect(self):
        discs = burner.find_discs()
        for p in discs:
            role = json.loads((p / "DISCKIT.json").read_text()).get("role")
            self.v["read_text" if role == "text" else "read_media"].set(str(p))
        self.log(f"Found {len(discs)} DiscKit disc(s) in /Volumes" if discs else "No DiscKit discs mounted.")

    def _use_built(self):
        self.v["read_text"].set(self.v["text_out"].get())
        self.v["read_media"].set(self.v["media_out"].get())

    def _start_reader(self):
        from .reader.server import ReaderServer
        roots = [p for p in (self.v["read_text"].get().strip(), self.v["read_media"].get().strip()) if p]
        try:
            self.reader = ReaderServer(roots, port=int(self.v["port"].get()))
            url = self.reader.start(open_browser=True)
        except Exception as e:
            self.reader = None
            return messagebox.showerror("DiscKit", f"Could not start reader: {e}")
        self._save_settings()
        self.url_lbl.configure(text=url)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.log(f"Reader running at {url}")

    def _stop_reader(self):
        if self.reader:
            self.reader.stop()
            self.reader = None
        self.url_lbl.configure(text="")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        for lbl in self.io_lbls:
            lbl.configure(text="—")
        self.log("Reader stopped.")

    def _show_io(self):
        for lbl, v in zip(self.io_lbls, self.reader.lib.volumes):
            s = v.stats()
            dot = "●" if s["active"] else "○"
            lbl.configure(text=f"{dot} Drive {s['disc_index']} {s['role'].upper():5}  {human(s['throughput_bps'])}/s  "
                               f"reads {s['reads']:,}  from disc {human(s['bytes_read'])}  {s['last_path'][:40]}")


def run():
    App().mainloop()
