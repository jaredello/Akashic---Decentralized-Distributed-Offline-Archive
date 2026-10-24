/**
 * Four quick numbers about the archive (articles, images, and how much each disc holds),
 * plus the button that opens the Combined Preview of both discs.
 */
import React from "react";
import { Database, FileText, Image as ImageIcon, HardDrive, Eye } from "lucide-react";
import { fmtBytes } from "@/lib/api";

export const ArchiveStats = ({ status, onPreview }) => {
  const stats = [
    { icon: FileText, label: "Articles", val: status?.text_disk?.article_count ?? "—", c: "#15803d" },
    { icon: ImageIcon, label: "Images", val: status?.media_disk?.image_count ?? "—", c: "#b45309" },
    { icon: Database, label: "Text Disk", val: fmtBytes(status?.text_disk?.used_bytes || 0), c: "#15803d" },
    { icon: HardDrive, label: "Media Disk", val: fmtBytes(status?.media_disk?.used_bytes || 0), c: "#b45309" },
  ];
  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
        {stats.map((s) => (
          <div key={s.label} className="border border-[#eaecf0] bg-[#f8f9fa] rounded-sm p-3">
            <s.icon size={15} style={{ color: s.c }} />
            <div className="mono text-lg text-[#202122] mt-1">{s.val}</div>
            <div className="text-[11px] text-[#72777d]">{s.label}</div>
          </div>
        ))}
      </div>
      <button
        onClick={onPreview}
        data-testid="preview-btn"
        className="flex items-center gap-2 h-10 px-5 mt-4 rounded-sm border border-[#3366cc] text-[#3366cc] text-sm font-semibold hover:bg-[#eaf3ff] transition-colors"
      >
        <Eye size={16} /> Preview offline site (both discs combined)
      </button>
      <p className="text-xs text-[#72777d] mt-1.5">
        Opens the exact Text + Media disc content in a new tab — test-browse it before you burn.
      </p>
    </>
  );
};
