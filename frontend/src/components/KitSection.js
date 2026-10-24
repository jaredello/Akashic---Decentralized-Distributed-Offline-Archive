/**
 * The "DiscKit for Mac" section on the Burn page: what the desktop app does and where to get it.
 */
import React, { useEffect, useState } from "react";
import { Laptop, Download, FileArchive, FolderOpen, Globe, Disc3, BookOpen, Search, Github, Terminal } from "lucide-react";
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
  { icon: Search, label: "Full-text search" },
];

const AppDownload = ({ info }) => {
  const dmg = info?.app?.dmg_url;
  if (dmg) {
    return (
      <a href={dmg} data-testid="kit-dmg-btn"
        className="inline-flex items-center justify-center gap-2 h-10 px-5 rounded-sm bg-[#3366cc] text-white text-sm font-semibold hover:bg-[#2a4b8d] transition-colors">
        <Download size={16} /> Download DiscKit.app (.dmg)
      </a>
    );
  }
  return (
    <ol className="text-xs text-[#54595d] space-y-1 list-decimal ml-4" data-testid="kit-dmg-steps">
      <li>Use <b>Save to GitHub</b> in the chat box to push this project.</li>
      <li>On GitHub open <b>Actions → Build DiscKit.app (macOS)</b>; GitHub's Macs build it in about 5 minutes.</li>
      <li>Download the <span className="mono">DiscKit-macOS-arm64</span> file from that run, open the .dmg and drag DiscKit into Applications.</li>
    </ol>
  );
};

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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-[#eaecf0] border-t border-[#eaecf0]">
        <div className="bg-white p-5" data-testid="kit-app-option">
          <div className="flex items-center gap-2 mb-1">
            <img src="/disckit-icon.png" alt="DiscKit app icon" className="w-9 h-9" data-testid="kit-app-icon" />
            <div>
              <div className="wiki-serif text-base text-[#202122]">DiscKit.app <span className="mono text-[10px] text-[#15803d] align-middle ml-1">RECOMMENDED</span></div>
              <div className="mono text-[10px] text-[#72777d]">Apple Silicon · no Python needed · {info ? `v${info.version}` : "…"}</div>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-[#54595d] mb-3"><Github size={12} /> Built automatically on GitHub's Macs</div>
          <AppDownload info={info} />
          <p className="text-[11px] text-[#72777d] mt-3">
            The app isn't signed by Apple yet. On first launch, right-click it and choose <b>Open</b>. On macOS 15 or later, go to System Settings → Privacy &amp; Security → <b>Open Anyway</b>.
          </p>
          {info?.app?.signing_ready && (
            <p className="text-[11px] text-[#54595d] mt-2 border-l-2 border-[#15803d] pl-2" data-testid="kit-signing-note">
              <b>Ready for signing:</b> once you have an Apple Developer account, add 5 secrets to your GitHub repo and every build is signed and approved by Apple (it opens with a normal double-click, even offline). Step-by-step guide: <span className="mono">{info.app.signing_guide}</span> in the kit.
            </p>
          )}
        </div>
        <div className="bg-white p-5" data-testid="kit-source-option">
          <div className="flex items-center gap-2 mb-1">
            <Terminal size={18} className="text-[#202122]" />
            <div className="wiki-serif text-base text-[#202122]">Source kit</div>
          </div>
          <p className="text-xs text-[#54595d] mb-3">Same app, run with your own Python 3.10+. It also includes the app build script.</p>
          <a
            href={`${API}/kit/download`}
            download
            data-testid="kit-download-btn"
            className="inline-flex items-center justify-center gap-2 h-10 px-5 rounded-sm bg-[#202122] text-white text-sm font-semibold hover:bg-black transition-colors"
          >
            <Download size={16} /> Download source kit (.zip)
          </a>
          <div className="mono text-[11px] text-[#72777d] mt-2" data-testid="kit-meta">
            {info ? `v${info.version} · ${info.file_count} files · ${fmtBytes(info.size_bytes)}` : "Loading…"}
          </div>
        </div>
      </div>
      <p className="px-5 py-4 border-t border-[#eaecf0] text-xs text-[#72777d]">
        Get the newest <span className="mono">wikipedia_en_all_maxi</span> file (about 110 GB) from{" "}
        <a className="text-[#3366cc] hover:underline" href="https://download.kiwix.org/zim/wikipedia/" target="_blank" rel="noreferrer">download.kiwix.org</a>.
        With full-text search switched on, the index adds roughly 15–25 GB to the Text Disc.
      </p>
    </section>
  );
};
