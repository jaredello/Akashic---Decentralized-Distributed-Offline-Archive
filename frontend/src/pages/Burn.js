import React, { useEffect, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  Disc3, Download, Database, FileText, Image as ImageIcon, Sparkles,
  Loader2, ArrowLeft, CheckCircle2, AlertTriangle, HardDrive, Gauge,
  ShieldCheck, Eye, Copy, Check,
} from "lucide-react";
import { toast } from "sonner";
import { http, API, fmtBytes } from "@/lib/api";
import { useDisks } from "@/context/DiskContext";
import { KitSection } from "@/components/KitSection";

const DISC_TOTAL = 100 * 1000 * 1000 * 1000;

const ShaRow = ({ sha }) => {
  const [copied, setCopied] = useState(false);
  if (!sha) return null;
  const copy = () => {
    navigator.clipboard?.writeText(sha);
    setCopied(true);
    toast.success("SHA-256 copied");
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      onClick={copy}
      data-testid="sha-copy"
      title="Copy full SHA-256"
      className="flex items-center gap-1.5 w-full text-left mono text-[10px] text-[#54595d] bg-[#f8f9fa] border border-[#eaecf0] rounded-sm px-2 py-1 mb-3 hover:bg-[#eef1f4]"
    >
      <ShieldCheck size={12} className="text-[#15803d] shrink-0" />
      <span className="truncate">{sha}</span>
      {copied ? <Check size={11} className="shrink-0 text-[#15803d]" /> : <Copy size={11} className="shrink-0" />}
    </button>
  );
};

const DiscCard = ({ kind, entry }) => {
  const isText = kind === "text";
  const accent = isText ? "#15803d" : "#b45309";
  const size = entry?.[kind]?.size || 0;
  const sha = entry?.[kind]?.sha256;
  const count = isText ? entry?.text?.article_count : entry?.media?.image_count;
  const pct = Math.max((size / DISC_TOTAL) * 100, size > 0 ? 0.4 : 0);
  return (
    <div className="border border-[#c8ccd1] bg-white rounded-sm overflow-hidden" data-testid={`disc-card-${kind}`}>
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[#eaecf0]" style={{ background: "#f8f9fa" }}>
        <Disc3 size={26} style={{ color: accent }} />
        <div>
          <div className="wiki-serif text-base text-[#202122]">{isText ? "Text Disc" : "Media Disc"}</div>
          <div className="mono text-[10px] text-[#72777d]">{isText ? "DRIVE 0 · article text" : "DRIVE 1 · images"}</div>
        </div>
      </div>
      <div className="p-4">
        <div className="flex items-baseline justify-between mb-1">
          <span className="mono text-2xl text-[#202122]">{fmtBytes(size)}</span>
          <span className="mono text-[11px] text-[#72777d]">of 100 GB M-DISC</span>
        </div>
        <div className="h-2 bg-[#eaecf0] rounded-full overflow-hidden mb-2">
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: accent }} />
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[#54595d] mb-3">
          {isText ? <FileText size={13} /> : <ImageIcon size={13} />}
          {count ?? 0} {isText ? "articles" : "images"} · ISO 9660 (Joliet)
        </div>
        <ShaRow sha={sha} />
        <a
          href={`${API}/burn/download/${kind}`}
          download
          data-testid={`download-${kind}`}
          className="flex items-center justify-center gap-2 w-full h-10 rounded-sm text-white text-sm font-semibold transition-opacity hover:opacity-90"
          style={{ background: accent }}
        >
          <Download size={16} /> Download {isText ? "Text" : "Media"} disc image
        </a>
      </div>
    </div>
  );
};

export default function Burn() {
  const { status, refreshStatus } = useDisks();
  const [seed, setSeed] = useState(null);
  const [burn, setBurn] = useState(null);
  const [exportRec, setExportRec] = useState(null);
  const [target, setTarget] = useState(150);
  const [themes, setThemes] = useState([]);
  const [theme, setTheme] = useState("");
  const seedPoll = useRef(null);
  const burnPoll = useRef(null);

  const loadBurn = useCallback(async () => {
    const { data } = await http.get("/burn/status");
    setBurn(data.burn);
    setExportRec(data.export);
    return data.burn;
  }, []);

  useEffect(() => {
    loadBurn();
    http.get("/seed/status").then(({ data }) => setSeed(data));
    http.get("/seed/themes").then(({ data }) => setThemes(data)).catch((e) => console.warn("themes unavailable", e));
    return () => {
      clearInterval(seedPoll.current);
      clearInterval(burnPoll.current);
    };
  }, [loadBurn]);

  const grow = async () => {
    await http.post("/seed/expand", null, { params: { target, ...(theme ? { theme } : {}) } });
    clearInterval(seedPoll.current);
    seedPoll.current = setInterval(async () => {
      const { data } = await http.get("/seed/status");
      setSeed(data);
      refreshStatus();
      if (data.state === "done") clearInterval(seedPoll.current);
    }, 2000);
  };

  const build = async () => {
    await http.post("/burn");
    clearInterval(burnPoll.current);
    burnPoll.current = setInterval(async () => {
      const b = await loadBurn();
      if (b.state === "done" || b.state === "error") clearInterval(burnPoll.current);
    }, 2500);
  };

  const seedRunning = seed?.state === "running";
  const burnRunning = burn?.state === "running";
  const seedPct = seed?.total ? Math.round((seed.done / seed.total) * 100) : 0;
  const burnPct = burn?.total ? Math.round((burn.progress / burn.total) * 100) : 0;
  const cap = status?.capacity;
  const overCapacity = cap && (cap.text.over_capacity || cap.media.over_capacity || cap.largest_media_over_disc);
  let buildLabel = exportRec ? "Rebuild disc images" : "Build disc images";
  if (burnRunning) buildLabel = "Building…";
  const previewUrl = `${API}/preview/index.html`;
  const openPreview = () => window.open(previewUrl, "_blank", "noopener");

  return (
    <div className="max-w-[1000px] mx-auto px-4 py-6">
      <Link to="/" className="inline-flex items-center gap-1 text-[#3366cc] text-sm hover:underline mb-3">
        <ArrowLeft size={14} /> Offline Wikipedia
      </Link>

      <h1 className="wiki-serif text-4xl text-[#000] border-b border-[#eaecf0] pb-2">Burn to Disc</h1>
      <p className="text-sm text-[#54595d] mt-2 max-w-2xl">
        Export the archive as two ISO 9660 disc images — one for the <b>Text Disc</b> and one for
        the <b>Media Disc</b> — ready to write to Verbatim M-DISC media with your ASUS ZenDrive.
        The Text Disc holds a fully browsable offline website; the Media Disc holds every image.
      </p>

      {/* Current archive */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
        {[
          { icon: FileText, label: "Articles", val: status?.text_disk?.article_count ?? "—", c: "#15803d" },
          { icon: ImageIcon, label: "Images", val: status?.media_disk?.image_count ?? "—", c: "#b45309" },
          { icon: Database, label: "Text Disk", val: fmtBytes(status?.text_disk?.used_bytes || 0), c: "#15803d" },
          { icon: HardDrive, label: "Media Disk", val: fmtBytes(status?.media_disk?.used_bytes || 0), c: "#b45309" },
        ].map((s) => (
          <div key={s.label} className="border border-[#eaecf0] bg-[#f8f9fa] rounded-sm p-3">
            <s.icon size={15} style={{ color: s.c }} />
            <div className="mono text-lg text-[#202122] mt-1">{s.val}</div>
            <div className="text-[11px] text-[#72777d]">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Combined Preview */}
      <button
        onClick={openPreview}
        data-testid="preview-btn"
        className="flex items-center gap-2 h-10 px-5 mt-4 rounded-sm border border-[#3366cc] text-[#3366cc] text-sm font-semibold hover:bg-[#eaf3ff] transition-colors"
      >
        <Eye size={16} /> Preview offline site (both discs combined)
      </button>
      <p className="text-xs text-[#72777d] mt-1.5">
        Opens the exact Text + Media disc content in a new tab — test-browse it before you burn.
      </p>

      <KitSection />

      {/* Capacity Planner */}
      <section className="mt-8 border border-[#c8ccd1] rounded-sm p-5" data-testid="capacity-planner">
        <div className="flex items-center gap-2 mb-1">
          <Gauge size={17} className="text-[#3366cc]" />
          <h2 className="wiki-serif text-xl text-[#000]">Disc capacity planner</h2>
        </div>
        <p className="text-sm text-[#54595d] mb-4">
          Estimated how much each 100 GB M-DISC can hold at the current average item size.
        </p>
        {overCapacity && (
          <div className="flex items-center gap-2 text-sm text-[#dd3333] bg-[#fdeaea] border border-[#f3b5b5] rounded-sm px-3 py-2 mb-4" data-testid="capacity-warning">
            <AlertTriangle size={15} /> A disc has exceeded its 100 GB capacity — remove items before burning.
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { k: "text", label: "Text Disc", c: "#15803d", unit: "articles",
              count: status?.text_disk?.article_count || 0, used: status?.text_disk?.used_bytes || 0 },
            { k: "media", label: "Media Disc", c: "#b45309", unit: "images",
              count: status?.media_disk?.image_count || 0, used: status?.media_disk?.used_bytes || 0 },
          ].map((d) => {
            const p = cap?.[d.k];
            const fill = Math.max(p?.fill_pct || 0, d.used > 0 ? 0.4 : 0);
            return (
              <div key={d.k} className="border border-[#eaecf0] rounded-sm p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="wiki-serif text-base" style={{ color: d.c }}>{d.label}</span>
                  <span className="mono text-[11px] text-[#72777d]">{fmtBytes(d.used)} used</span>
                </div>
                <div className="h-2 bg-[#eaecf0] rounded-full overflow-hidden mb-1">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(fill, 100)}%`, background: d.c }} />
                </div>
                <div className="mono text-[10px] text-[#9aa0a6] mb-3">{(p?.fill_pct ?? 0).toFixed(4)}% of 100 GB</div>
                <dl className="text-sm space-y-1.5">
                  <div className="flex justify-between"><dt className="text-[#54595d]">Avg per {d.unit.slice(0, -1)}</dt><dd className="mono">{fmtBytes(p?.avg_item_bytes || 0)}</dd></div>
                  <div className="flex justify-between"><dt className="text-[#54595d]">Fits per disc</dt><dd className="mono font-bold" style={{ color: d.c }}>~{(p?.est_items_per_disc || 0).toLocaleString()} {d.unit}</dd></div>
                  <div className="flex justify-between"><dt className="text-[#54595d]">Headroom left</dt><dd className="mono">~{(p?.headroom_items || 0).toLocaleString()} more</dd></div>
                </dl>
              </div>
            );
          })}
        </div>
      </section>

      {/* Grow the archive */}
      <section className="mt-8 border border-[#c8ccd1] rounded-sm p-5">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={17} className="text-[#3366cc]" />
          <h2 className="wiki-serif text-xl text-[#000]">Grow the archive</h2>
        </div>
        <p className="text-sm text-[#54595d] mb-4">
          Crawl Wikipedia's link graph outward and pull in the most densely interlinked pages,
          so the offline copy reads like the real site. Pick a theme to grow a tight web around
          one subject, or leave it on <b>Everything</b> to expand the whole archive.
        </p>
        <label className="text-xs text-[#54595d] mono block mb-2">PICK A TOPIC</label>
        <div className="flex flex-wrap gap-2 mb-4" data-testid="theme-chips">
          {[{ key: "", label: "Everything" }, ...themes].map((t) => (
            <button
              key={t.key || "all"}
              onClick={() => setTheme(t.key)}
              disabled={seedRunning}
              data-testid={`theme-${t.key || "all"}`}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors disabled:opacity-50 ${
                theme === t.key
                  ? "bg-[#3366cc] border-[#3366cc] text-white"
                  : "bg-white border-[#a2a9b1] text-[#202122] hover:bg-[#f8f9fa]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row sm:items-end gap-4">
          <div>
            <label className="text-xs text-[#54595d] mono block mb-1">TARGET ARTICLE COUNT</label>
            <input
              type="range" min="30" max="400" step="10" value={target}
              data-testid="grow-target"
              onChange={(e) => setTarget(Number(e.target.value))}
              disabled={seedRunning}
              className="w-56 accent-[#3366cc] align-middle"
            />
            <span className="mono text-sm text-[#202122] ml-3">{target}</span>
          </div>
          <button
            onClick={grow}
            disabled={seedRunning}
            data-testid="grow-archive-btn"
            className="flex items-center gap-2 h-10 px-5 rounded-sm bg-[#3366cc] text-white text-sm font-semibold hover:bg-[#2a4b8d] disabled:opacity-50 transition-colors"
          >
            {seedRunning ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {seedRunning ? "Growing…" : "Grow archive"}
          </button>
        </div>
        {seedRunning && (
          <div className="mt-4" data-testid="grow-progress">
            <div className="h-2 bg-[#eaecf0] rounded-full overflow-hidden">
              <div className="h-full bg-[#3366cc] transition-all" style={{ width: `${seed.phase === "discovering" ? 8 : seedPct}%` }} />
            </div>
            <div className="mono text-xs text-[#72777d] mt-1">
              {seed.phase === "discovering" ? "Mapping Wikipedia links…" : `Writing to discs ${seed.done}/${seed.total}`} · {seed.current}
            </div>
          </div>
        )}
        {!seedRunning && seed?.errors?.length > 0 && (
          <div className="mono text-[11px] text-[#b45309] mt-3">{seed.errors.length} article(s) skipped during last run.</div>
        )}
      </section>

      {/* Build disc images */}
      <section className="mt-6 border border-[#c8ccd1] rounded-sm p-5">
        <div className="flex items-center gap-2 mb-1">
          <Disc3 size={17} className="text-[#202122]" />
          <h2 className="wiki-serif text-xl text-[#000]">Build disc images</h2>
        </div>
        <p className="text-sm text-[#54595d] mb-4">
          Package everything currently on the disks into two <span className="mono text-xs">.iso</span> files.
        </p>
        <button
          onClick={build}
          disabled={burnRunning || seedRunning}
          data-testid="build-discs-btn"
          className="flex items-center gap-2 h-10 px-5 rounded-sm bg-[#202122] text-white text-sm font-semibold hover:bg-black disabled:opacity-50 transition-colors"
        >
          {burnRunning ? <Loader2 size={16} className="animate-spin" /> : <Disc3 size={16} />}
          {buildLabel}
        </button>

        {burnRunning && (
          <div className="mt-4" data-testid="build-progress">
            <div className="h-2 bg-[#eaecf0] rounded-full overflow-hidden">
              <div className="h-full bg-[#202122] transition-all" style={{ width: `${Math.max(burnPct, 6)}%` }} />
            </div>
            <div className="mono text-xs text-[#72777d] mt-1 capitalize">{burn.step}… {burn.total ? `(${burn.progress}/${burn.total})` : ""}</div>
          </div>
        )}
        {burn?.state === "error" && (
          <div className="flex items-center gap-2 text-sm text-[#dd3333] mt-3">
            <AlertTriangle size={15} /> {burn.error}
          </div>
        )}

        {exportRec && !burnRunning && (
          <div className="mt-5">
            <div className="flex items-center gap-1.5 text-sm text-[#15803d] mb-3">
              <CheckCircle2 size={15} /> Disc images ready to burn
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <DiscCard kind="text" entry={exportRec} />
              <DiscCard kind="media" entry={exportRec} />
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-4">
              <a
                href={`${API}/burn/checksums`}
                download
                data-testid="download-checksums"
                className="flex items-center gap-2 h-9 px-4 rounded-sm border border-[#15803d] text-[#15803d] text-sm font-semibold hover:bg-[#edf7f0] transition-colors"
              >
                <ShieldCheck size={15} /> Download SHA256SUMS
              </a>
              <button
                onClick={openPreview}
                className="flex items-center gap-2 h-9 px-4 rounded-sm border border-[#3366cc] text-[#3366cc] text-sm font-semibold hover:bg-[#eaf3ff] transition-colors"
              >
                <Eye size={15} /> Preview before burning
              </button>
            </div>
            <p className="text-xs text-[#72777d] mt-3 max-w-2xl">
              Write each image to its own Verbatim M-DISC with the ASUS ZenDrive (e.g. your burning
              tool's "Burn image to disc"). Label them <b>TEXT</b> and <b>MEDIA</b>, then open
              <span className="mono text-[11px]"> index.html</span> on the Text Disc to browse offline.
              After burning, verify with <span className="mono text-[11px]">sha256sum -c SHA256SUMS</span> to
              confirm the discs match this archive.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
