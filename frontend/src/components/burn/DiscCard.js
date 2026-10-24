/**
 * One finished disc image (Text or Media): its size on a 100 GB disc, checksum and download button.
 */
import React, { useState } from "react";
import { Disc3, Download, FileText, Image as ImageIcon, ShieldCheck, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { API, fmtBytes } from "@/lib/api";

export const DISC_TOTAL = 100 * 1000 * 1000 * 1000;

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

export const DiscCard = ({ kind, entry }) => {
  const isText = kind === "text";
  const accent = isText ? "#15803d" : "#b45309";
  const size = entry?.[kind]?.size || 0;
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
        <ShaRow sha={entry?.[kind]?.sha256} />
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
