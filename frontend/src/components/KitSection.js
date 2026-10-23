import React, { useEffect, useState } from "react";
import { Laptop, Download, FileArchive, FolderOpen, Globe, Disc3, BookOpen } from "lucide-react";
import { http, API, fmtBytes } from "@/lib/api";

const STEPS = [
  { icon: FileArchive, color: "#15803d", title: "Build", body: "Pick a Kiwix .zim (e.g. full English Wikipedia), a folder, or a website. DiscKit splits it into a Text Disc and a Media Disc." },
  { icon: Disc3, color: "#202122", title: "Burn", body: "Detect both M-DISC drives and burn the two discs at the same time, with checksums verified." },
  { icon: BookOpen, color: "#b45309", title: "Read", body: "Insert both discs and read in your browser: articles come from drive 1, images stream from drive 2." },
];

const SOURCES = [
  { icon: FileArchive, label: "Kiwix .zim files" },
  { icon: FolderOpen, label: "Any folder of files" },
  { icon: Globe, label: "Whole websites" },
];

export const KitSection = () => {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    http.get("/kit/info").then(({ data }) => setInfo(data)).catch((e) => console.warn("kit info unavailable", e));
  }, []);

  return (
    <section className="mt-8 border border-[#c8ccd1] rounded-sm overflow-hidden" data-testid="kit-section">
      <div className="p-5 bg-[#f8f9fa] border-b border-[#eaecf0]">
        <div className="flex items-center gap-2 mb-1">
          <Laptop size={17} className="text-[#202122]" />
          <h2 className="wiki-serif text-xl text-[#000]">DiscKit for Mac: archive all of Wikipedia</h2>
        </div>
        <p className="text-sm text-[#54595d] max-w-2xl">
          The full English Wikipedia is too big for this browser demo. DiscKit is a desktop app that runs on your Mac,
          next to your two M-DISC drives. It splits the full archive (~55 GB of text, ~60 GB of images) across two 100 GB discs.
        </p>
        <div className="flex flex-wrap gap-2 mt-3">
          {SOURCES.map((s) => (
            <span key={s.label} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white border border-[#a2a9b1] text-xs text-[#202122]">
              <s.icon size={12} /> {s.label}
            </span>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[#eaecf0]">
        {STEPS.map((s, i) => (
          <div key={s.title} className="p-4" data-testid={`kit-step-${i + 1}`}>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="mono text-[10px] text-[#72777d]">0{i + 1}</span>
              <s.icon size={15} style={{ color: s.color }} />
              <span className="wiki-serif text-base">{s.title}</span>
            </div>
            <p className="text-xs text-[#54595d] leading-relaxed">{s.body}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-5 border-t border-[#eaecf0]">
        <a
          href={`${API}/kit/download`}
          download
          data-testid="kit-download-btn"
          className="inline-flex items-center justify-center gap-2 h-10 px-5 rounded-sm bg-[#202122] text-white text-sm font-semibold hover:bg-black transition-colors"
        >
          <Download size={16} /> Download DiscKit for macOS
        </a>
        <span className="mono text-[11px] text-[#72777d]" data-testid="kit-meta">
          {info ? `v${info.version} · ${info.file_count} files · ${fmtBytes(info.size_bytes)} · requires Python 3.10+` : "Loading…"}
        </span>
      </div>
      <p className="px-5 pb-5 -mt-2 text-xs text-[#72777d] max-w-2xl">
        Unzip the download, double-click <span className="mono">install.command</span> once, then open <span className="mono">DiscKit.command</span>.
        Get the newest <span className="mono">wikipedia_en_all_maxi</span> file from{" "}
        <a className="text-[#3366cc] hover:underline" href="https://download.kiwix.org/zim/wikipedia/" target="_blank" rel="noreferrer">download.kiwix.org</a>.
      </p>
    </section>
  );
};
