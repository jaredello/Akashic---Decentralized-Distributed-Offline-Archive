/**
 * The folder tree on the left of the Source page. Folders open and close; the selected file is
 * highlighted, and typing in the filter box shows only matching file names.
 */
import React, { useState } from "react";
import { ChevronRight, Folder, FolderOpen, FileCode2, FileText, Image as ImageIcon } from "lucide-react";

const fileIcon = (name) => {
  if (/\.(png|jpe?g|svg|ico|gif|webp)$/i.test(name)) return ImageIcon;
  if (/\.(md|txt)$/i.test(name) || name === "LICENSE") return FileText;
  return FileCode2;
};

const matches = (node, q) =>
  node.type === "file" ? node.path.toLowerCase().includes(q) : node.children.some((c) => matches(c, q));

// Flatten the visible part of the tree into rows (folder rows plus the files inside open folders).
const visibleRows = (nodes, depth, open, q, rows = []) => {
  nodes.forEach((node) => {
    if (q && !matches(node, q)) return;
    rows.push({ node, depth });
    if (node.type === "dir" && (q || open.has(node.path))) visibleRows(node.children, depth + 1, open, q, rows);
  });
  return rows;
};

const FileRow = ({ node, depth, active, onSelect }) => {
  const Icon = fileIcon(node.name);
  return (
    <button
      onClick={() => onSelect(node.path)}
      data-testid={`source-file-${node.path}`}
      style={{ paddingLeft: 8 + depth * 14 }}
      className={`flex items-center gap-1.5 w-full text-left py-[3px] pr-2 text-[13px] rounded-sm transition-colors ${
        active ? "bg-[#eaf3ff] text-[#2a4b8d] font-semibold" : "text-[#202122] hover:bg-[#f1f3f5]"
      }`}
    >
      <Icon size={13} className="shrink-0 text-[#72777d]" />
      <span className="truncate">{node.name}</span>
    </button>
  );
};

const FolderRow = ({ node, depth, isOpen, toggle }) => (
  <button
    onClick={() => toggle(node.path)}
    data-testid={`source-folder-${node.path}`}
    title={node.summary || ""}
    style={{ paddingLeft: 8 + depth * 14 }}
    className="flex items-center gap-1 w-full text-left py-[3px] pr-2 text-[13px] text-[#202122] hover:bg-[#f1f3f5] rounded-sm"
  >
    <ChevronRight size={12} className={`shrink-0 text-[#72777d] transition-transform ${isOpen ? "rotate-90" : ""}`} />
    {isOpen ? <FolderOpen size={13} className="shrink-0 text-[#b45309]" /> : <Folder size={13} className="shrink-0 text-[#b45309]" />}
    <span className="truncate font-medium">{node.name}</span>
  </button>
);

export const FileTree = ({ tree, selected, onSelect, open, toggle }) => {
  const [filter, setFilter] = useState("");
  const q = filter.trim().toLowerCase();
  return (
    <div>
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter files…"
        data-testid="source-filter"
        className="w-full h-8 px-2.5 mb-2 text-[13px] border border-[#a2a9b1] rounded-sm outline-none focus:border-[#3366cc] focus:shadow-[inset_0_0_0_1px_#3366cc]"
      />
      <nav data-testid="source-tree">
        {visibleRows(tree, 0, open, q).map(({ node, depth }) => (node.type === "file"
          ? <FileRow key={node.path} node={node} depth={depth} active={node.path === selected} onSelect={onSelect} />
          : <FolderRow key={node.path} node={node} depth={depth} isOpen={Boolean(q) || open.has(node.path)} toggle={toggle} />))}
      </nav>
    </div>
  );
};
