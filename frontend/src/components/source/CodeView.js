/**
 * Shows one file: colour-coded code with line numbers, or a formatted view for Markdown guides,
 * or the picture itself for images.
 */
import React, { useMemo, useState } from "react";
import hljs from "highlight.js/lib/common";
import "highlight.js/styles/github.css";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { API } from "@/lib/api";

const Code = ({ content, language }) => {
  const html = useMemo(() => {
    const lang = hljs.getLanguage(language) ? language : "plaintext";
    return hljs.highlight(content, { language: lang, ignoreIllegals: true }).value;
  }, [content, language]);
  const lineCount = content.split("\n").length;
  return (
    <div className="flex text-[12.5px] leading-[1.6] overflow-auto border border-[#eaecf0] rounded-sm bg-white" data-testid="source-code">
      <pre aria-hidden className="select-none text-right text-[#9aa0a6] bg-[#f8f9fa] border-r border-[#eaecf0] px-3 py-3 m-0 mono">
        {Array.from({ length: lineCount }, (_, i) => i + 1).join("\n")}
      </pre>
      <pre className="m-0 px-4 py-3 mono flex-1 min-w-0"><code className="hljs !bg-transparent !p-0" dangerouslySetInnerHTML={{ __html: html }} /></pre>
    </div>
  );
};

// Links between guides (e.g. "docs/ARCHITECTURE.md") open inside the viewer instead of leaving the page.
const resolveLink = (fromPath, href) => {
  const parts = fromPath.split("/").slice(0, -1);
  for (const seg of href.split("#")[0].split("/")) {
    if (seg === "..") parts.pop();
    else if (seg && seg !== ".") parts.push(seg);
  }
  return parts.join("/");
};

const Markdown = ({ content, path, onOpen }) => {
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(content)), [content]);
  const onClick = (e) => {
    const a = e.target.closest("a");
    const href = a?.getAttribute("href");
    if (!href || /^(https?:|mailto:|#)/.test(href)) return;
    e.preventDefault();
    onOpen(resolveLink(path, href));
  };
  return (
    <article onClick={onClick} className="source-markdown border border-[#eaecf0] rounded-sm bg-white px-8 py-6" data-testid="source-markdown"
      dangerouslySetInnerHTML={{ __html: html }} />
  );
};

export const CodeView = ({ file, onOpen }) => {
  const [showCode, setShowCode] = useState(false);
  if (file.kind === "image") {
    return (
      <div className="border border-[#eaecf0] rounded-sm p-6 bg-[repeating-conic-gradient(#f1f3f5_0%_25%,#fff_0%_50%)] bg-[length:20px_20px]">
        <img src={`${API}/source/raw?path=${encodeURIComponent(file.path)}`} alt={file.path} className="max-h-[480px] mx-auto" data-testid="source-image" />
      </div>
    );
  }
  if (file.kind !== "text") {
    return <p className="text-sm text-[#54595d]">This file is {file.kind === "too_large" ? "too large to show here" : "not text"}. Use “Raw” or download the full source.</p>;
  }
  const isMarkdown = file.language === "markdown";
  return (
    <div>
      {isMarkdown && (
        <div className="flex gap-1 mb-2" data-testid="source-md-toggle">
          {["Formatted", "Code"].map((label, i) => (
            <button key={label} onClick={() => setShowCode(i === 1)}
              className={`px-3 h-7 text-xs font-semibold rounded-sm border ${showCode === (i === 1) ? "bg-[#202122] text-white border-[#202122]" : "bg-white border-[#a2a9b1] hover:bg-[#f8f9fa]"}`}>
              {label}
            </button>
          ))}
        </div>
      )}
      {isMarkdown && !showCode
        ? <Markdown content={file.content} path={file.path} onOpen={onOpen} />
        : <Code content={file.content} language={file.language} />}
    </div>
  );
};
