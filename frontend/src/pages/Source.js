/**
 * Source page (/source): browse and read the app's complete, open-source code.
 * The folder tree is on the left; the chosen file shows on the right with a plain-English
 * summary taken from the file's own header comment. ?file=path/to/file opens a file directly.
 */
import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Download, Code2, Copy, ExternalLink, Info, Scale } from "lucide-react";
import { toast } from "sonner";
import { http, API, fmtBytes } from "@/lib/api";
import { FileTree } from "@/components/source/FileTree";
import { CodeView } from "@/components/source/CodeView";

const START_FILE = "README.md";
const parentsOf = (path) => path.split("/").slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join("/"));

const findFolder = (nodes, path) => {
  for (const n of nodes) {
    if (n.type !== "dir") continue;
    if (n.path === path) return n;
    const hit = findFolder(n.children, path);
    if (hit) return hit;
  }
  return null;
};

const FileHeader = ({ file, folderNote }) => {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(file.content || "");
      toast.success("File copied");
    } catch {
      toast.error("Couldn't copy. Your browser blocked clipboard access.");
    }
  };
  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="mono text-[15px] text-[#202122] break-all" data-testid="source-file-path">{file.path}</h2>
        <span className="mono text-[11px] text-[#72777d]">{file.lines ? `${file.lines} lines · ` : ""}{fmtBytes(file.size)}</span>
        <div className="flex gap-2 ml-auto">
          {file.kind === "text" && (
            <button onClick={copy} data-testid="source-copy-btn" className="flex items-center gap-1 h-7 px-2.5 text-xs border border-[#a2a9b1] rounded-sm hover:bg-[#f8f9fa]">
              <Copy size={12} /> Copy
            </button>
          )}
          <a href={`${API}/source/raw?path=${encodeURIComponent(file.path)}`} target="_blank" rel="noreferrer" data-testid="source-raw-link"
            className="flex items-center gap-1 h-7 px-2.5 text-xs border border-[#a2a9b1] rounded-sm hover:bg-[#f8f9fa]">
            <ExternalLink size={12} /> Raw
          </a>
        </div>
      </div>
      {(file.summary || folderNote) && (
        <div className="flex gap-2 mt-3 p-3 bg-[#f8f9fa] border-l-2 border-[#3366cc] text-[13px] text-[#202122] leading-relaxed" data-testid="source-summary">
          <Info size={15} className="shrink-0 text-[#3366cc] mt-0.5" />
          <div>
            {file.summary && <p className="m-0"><b>What this file does:</b> {file.summary}</p>}
            {folderNote && <p className="m-0 mt-1 text-[#54595d]"><b>Folder:</b> {folderNote}</p>}
          </div>
        </div>
      )}
    </div>
  );
};

export default function Source() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("file") || START_FILE;
  const [tree, setTree] = useState([]);
  const [stats, setStats] = useState(null);
  const [open, setOpen] = useState(new Set());
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    http.get("/source/tree").then(({ data }) => {
      setTree(data.tree);
      setStats({ files: data.file_count, bytes: data.total_bytes });
    });
  }, []);

  useEffect(() => {
    setOpen((prev) => new Set([...prev, ...parentsOf(selected)]));
    setError("");
    http.get("/source/file", { params: { path: selected } })
      .then(({ data }) => setFile(data))
      .catch(() => { setFile(null); setError(`“${selected}” is not part of the public source.`); });
    window.scrollTo({ top: 0 });
  }, [selected]);

  const select = useCallback((path) => setParams({ file: path }), [setParams]);
  const toggle = (path) => setOpen((prev) => {
    const next = new Set(prev);
    next.has(path) ? next.delete(path) : next.add(path);
    return next;
  });
  const folderNote = file && findFolder(tree, parentsOf(file.path).slice(-1)[0] || "")?.summary;

  return (
    <div className="max-w-[1280px] mx-auto px-4 py-6" data-testid="source-page">
      <div className="flex flex-wrap items-end gap-4 border-b border-[#eaecf0] pb-3 mb-5">
        <div>
          <h1 className="wiki-serif text-4xl text-[#000] flex items-center gap-3"><Code2 size={30} className="text-[#3366cc]" /> Source code</h1>
          <p className="text-sm text-[#54595d] mt-1 max-w-2xl">
            This whole project is open source under the <b>MIT License</b>: read it, copy it, change it and share it.
            Start with the README, then the plain-English guide in <span className="mono text-xs">docs/</span>.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="mono text-[11px] text-[#72777d]" data-testid="source-stats">
            {stats ? `${stats.files} files · ${fmtBytes(stats.bytes)}` : "…"}
          </span>
          <button onClick={() => select("LICENSE")} className="flex items-center gap-1.5 h-9 px-3 text-xs font-semibold border border-[#a2a9b1] rounded-sm hover:bg-[#f8f9fa]" data-testid="source-license-btn">
            <Scale size={14} /> License
          </button>
          <a href={`${API}/source/download`} download data-testid="source-download-btn"
            className="flex items-center gap-2 h-9 px-4 rounded-sm bg-[#202122] text-white text-sm font-semibold hover:bg-black transition-colors">
            <Download size={15} /> Download all source (.zip)
          </a>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-[290px_minmax(0,1fr)] gap-6">
        <aside className="md:sticky md:top-20 md:self-start md:max-h-[calc(100vh-6rem)] md:overflow-auto pr-1">
          <FileTree tree={tree} selected={selected} onSelect={select} open={open} toggle={toggle} />
        </aside>
        <main className="min-w-0">
          {error && <p className="text-sm text-[#dd3333]" data-testid="source-error">{error}</p>}
          {file && !error && (
            <>
              <FileHeader file={file} folderNote={folderNote} />
              <CodeView key={file.path} file={file} onOpen={select} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
