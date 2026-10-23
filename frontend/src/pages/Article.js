import React, { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { FileText, WifiOff, Loader2, ArrowLeft } from "lucide-react";
import { http, fmtBytes } from "@/lib/api";
import { MediaImage } from "@/components/MediaImage";
import { useDisks } from "@/context/DiskContext";
import DOMPurify from "dompurify";

const clean = (html) => ({ __html: DOMPurify.sanitize(html || "") });

export default function Article() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { beginRead, endRead } = useDisks();
  const [article, setArticle] = useState(null);
  const [phase, setPhase] = useState("loading-text");
  const [notFound, setNotFound] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    let alive = true;
    setArticle(null);
    setNotFound(false);
    setPhase("loading-text");
    window.scrollTo(0, 0);
    beginRead("text", slug);
    http
      .get(`/articles/${slug}`)
      .then(({ data }) => {
        if (!alive) return;
        endRead("text", { bytes: data.size_bytes || 0, label: data.title });
        setArticle(data);
        setPhase("media");
      })
      .catch(() => {
        if (!alive) return;
        endRead("text", { bytes: 0, label: "404" });
        setNotFound(true);
      });
    return () => {
      alive = false;
    };
  }, [slug, beginRead, endRead]);

  const onBodyClick = useCallback(
    (e) => {
      const a = e.target.closest("[data-wikilink]");
      if (a) {
        e.preventDefault();
        navigate(`/wiki/${a.getAttribute("data-wikilink")}`);
      }
    },
    [navigate]
  );

  if (notFound) {
    return (
      <div className="max-w-[760px] mx-auto px-4 py-20 text-center">
        <h1 className="wiki-serif text-2xl text-[#202122]">Not on these discs</h1>
        <p className="text-sm text-[#54595d] mt-2">This article was not written to the Text Disk.</p>
        <Link to="/" className="text-[#3366cc] hover:underline text-sm mt-4 inline-block">← Back to the archive</Link>
      </div>
    );
  }

  if (!article) {
    return (
      <div className="max-w-[900px] mx-auto px-4 py-16">
        <div className="flex items-center gap-2 mono text-sm text-[#15803d]">
          <Loader2 size={16} className="animate-spin" /> READING TEXT DISK (DRIVE 0)…
        </div>
        <div className="mt-6 space-y-3">
          <div className="h-8 w-2/3 bg-[#eaecf0] animate-pulse rounded-sm" />
          <div className="h-4 w-full bg-[#f0f1f3] animate-pulse rounded-sm" />
          <div className="h-4 w-11/12 bg-[#f0f1f3] animate-pulse rounded-sm" />
          <div className="h-4 w-10/12 bg-[#f0f1f3] animate-pulse rounded-sm" />
        </div>
      </div>
    );
  }

  const lead = article.media?.find((m) => m.is_lead);
  const inline = (article.media || []).filter((m) => !m.is_lead);

  return (
    <article data-testid="article-view" className="max-w-[900px] mx-auto px-4 py-6">
      <Link to="/" className="inline-flex items-center gap-1 text-[#3366cc] text-sm hover:underline mb-3">
        <ArrowLeft size={14} /> Offline Wikipedia
      </Link>

      <h1 className="wiki-serif text-4xl text-[#000] border-b border-[#eaecf0] pb-2">{article.title}</h1>
      {article.description && (
        <p className="text-sm text-[#54595d] italic mt-1">{article.description}</p>
      )}
      <div className="flex flex-wrap items-center gap-3 mono text-[11px] text-[#72777d] mt-2">
        <span className="flex items-center gap-1 text-[#15803d]"><FileText size={12} /> TEXT DISK · {fmtBytes(article.size_bytes)}</span>
        <span className="flex items-center gap-1"><WifiOff size={12} /> offline read</span>
      </div>

      {/* Infobox — lead image streamed from the Media Disk */}
      {lead && (
        <div className="md:float-right clear-right w-full md:w-[300px] bg-[#f8f9fa] border border-[#a2a9b1] md:ml-6 mt-4 mb-4">
          <div className="text-center wiki-serif text-base font-bold text-[#000] px-2 py-2 border-b border-[#c8ccd1]">
            {article.title}
          </div>
          <div className="p-2">
            <MediaImage id={lead.id} caption={lead.caption} />
          </div>
          <dl className="text-xs text-[#202122] px-2 pb-2 space-y-1">
            <div className="flex gap-2 border-t border-[#eaecf0] pt-1">
              <dt className="font-bold w-20 shrink-0">Source</dt>
              <dd>Media Disk · Drive 1</dd>
            </div>
            <div className="flex gap-2">
              <dt className="font-bold w-20 shrink-0">Medium</dt>
              <dd>Verbatim M-DISC</dd>
            </div>
          </dl>
        </div>
      )}

      {/* Table of contents */}
      {article.toc?.length > 1 && (
        <nav className="inline-block bg-[#f8f9fa] border border-[#c8ccd1] p-3 my-4 text-sm" data-testid="toc">
          <div className="wiki-serif font-bold text-[#000] mb-1">Contents</div>
          <ol className="list-decimal ml-5 space-y-0.5">
            {article.toc.map((t) => (
              <li key={t.anchor}>
                <a href={`#${t.anchor}`} className="text-[#3366cc] hover:underline">{t.title}</a>
              </li>
            ))}
          </ol>
        </nav>
      )}

      <div ref={bodyRef} onClick={onBodyClick} className="article-body">
        <div dangerouslySetInnerHTML={clean(article.lead_html)} />

        {article.sections.map((s, i) => (
          <section key={s.anchor} id={s.anchor} className="scroll-mt-20">
            <h2 className="wiki-serif text-2xl text-[#000] border-b border-[#eaecf0] pb-1 mt-8 mb-3">
              {s.title}
            </h2>
            {inline[i] && (
              <MediaImage
                id={inline[i].id}
                caption={inline[i].caption}
                delay={300 + i * 250}
                className="md:float-right w-full md:w-56 md:ml-5 mb-3"
              />
            )}
            <div dangerouslySetInnerHTML={clean(s.html)} />
          </section>
        ))}
        <div className="clear-both" />
      </div>

      <footer className="mt-10 pt-4 border-t border-[#eaecf0] text-xs text-[#72777d]">
        Retrieved offline from the <b className="text-[#15803d]">Text Disk (Drive 0)</b> and{" "}
        <b className="text-[#b45309]">Media Disk (Drive 1)</b>. Content sourced from Wikipedia,
        the free encyclopedia, and archived to M-DISC.
      </footer>
    </article>
  );
}
