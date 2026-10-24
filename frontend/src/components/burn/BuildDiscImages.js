/**
 * "Build disc images": packs everything into two .iso files, shows progress, then offers the
 * downloads, the SHA256SUMS checksum file and burning instructions.
 */
import React from "react";
import { Disc3, Loader2, AlertTriangle, CheckCircle2, ShieldCheck, Eye } from "lucide-react";
import { API } from "@/lib/api";
import { DiscCard } from "@/components/burn/DiscCard";

const BuildProgress = ({ burn }) => {
  const pct = burn.total ? Math.round((burn.progress / burn.total) * 100) : 0;
  return (
    <div className="mt-4" data-testid="build-progress">
      <div className="h-2 bg-[#eaecf0] rounded-full overflow-hidden">
        <div className="h-full bg-[#202122] transition-all" style={{ width: `${Math.max(pct, 6)}%` }} />
      </div>
      <div className="mono text-xs text-[#72777d] mt-1 capitalize">{burn.step}… {burn.total ? `(${burn.progress}/${burn.total})` : ""}</div>
    </div>
  );
};

const FinishedImages = ({ exportRec, onPreview }) => (
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
        onClick={onPreview}
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
);

export const BuildDiscImages = ({ burn, exportRec, seedRunning, onBuild, onPreview }) => {
  const running = burn?.state === "running";
  let label = exportRec ? "Rebuild disc images" : "Build disc images";
  if (running) label = "Building…";
  return (
    <section className="mt-6 border border-[#c8ccd1] rounded-sm p-5">
      <div className="flex items-center gap-2 mb-1">
        <Disc3 size={17} className="text-[#202122]" />
        <h2 className="wiki-serif text-xl text-[#000]">Build disc images</h2>
      </div>
      <p className="text-sm text-[#54595d] mb-4">
        Package everything currently on the disks into two <span className="mono text-xs">.iso</span> files.
      </p>
      <button
        onClick={onBuild}
        disabled={running || seedRunning}
        data-testid="build-discs-btn"
        className="flex items-center gap-2 h-10 px-5 rounded-sm bg-[#202122] text-white text-sm font-semibold hover:bg-black disabled:opacity-50 transition-colors"
      >
        {running ? <Loader2 size={16} className="animate-spin" /> : <Disc3 size={16} />}
        {label}
      </button>
      {running && <BuildProgress burn={burn} />}
      {burn?.state === "error" && (
        <div className="flex items-center gap-2 text-sm text-[#dd3333] mt-3">
          <AlertTriangle size={15} /> {burn.error}
        </div>
      )}
      {exportRec && !running && <FinishedImages exportRec={exportRec} onPreview={onPreview} />}
    </section>
  );
};
