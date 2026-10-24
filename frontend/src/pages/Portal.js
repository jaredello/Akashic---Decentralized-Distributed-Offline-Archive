/**
 * Home page: the Wikipedia-style main page with a grid of every archived article.
 * On first visit it asks the backend to download the starter articles.
 */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Disc3, FileText, Image as ImageIcon, WifiOff, ChevronRight, Loader2 } from "lucide-react";
import { http, mediaUrl, fmtBytes } from "@/lib/api";
import { useDisks } from "@/context/DiskContext";

const Card = ({ a }) => (
  <Link
    to={`/wiki/${a.slug}`}
    data-testid={`article-card-${a.slug}`}
    className="group flex gap-3 p-2 border border-[#eaecf0] hover:border-[#a2a9b1] hover:bg-[#f8f9fa] transition-colors"
  >
    <div className="w-16 h-16 shrink-0 bg-[#eaecf0] border border-[#c8ccd1] overflow-hidden">
      {a.lead_media_id ? (
        <img src={mediaUrl(a.lead_media_id)} alt="" className="w-full h-full object-cover" loading="lazy" />
      ) : (
        <div className="w-full h-full flex items-center justify-center">
          <FileText size={18} className="text-[#a2a9b1]" />
        </div>
      )}
    </div>
    <div className="min-w-0">
      <div className="wiki-serif text-[15px] text-[#3366cc] group-hover:underline leading-tight">
        {a.title}
      </div>
      <div className="text-xs text-[#54595d] line-clamp-2 mt-0.5">{a.description || "Encyclopedia article"}</div>
      <div className="mono text-[10px] text-[#9aa0a6] mt-1">{fmtBytes(a.size_bytes)} · TEXT DISK</div>
    </div>
  </Link>
);

export default function Portal() {
  const [articles, setArticles] = useState(null);
  const [seed, setSeed] = useState(null);
  const { status } = useDisks();

  const load = async () => {
    const { data } = await http.get("/articles");
    setArticles(data);
    return data;
  };

  useEffect(() => {
    let iv;
    const boot = async () => {
      const data = await load();
      if (data.length === 0) {
        // kick off seeding and poll
        try { await http.post("/seed"); } catch (e) { console.warn("seed request failed", e); }
        iv = setInterval(async () => {
          const { data: st } = await http.get("/seed/status");
          setSeed(st);
          if (st.state === "done") {
            clearInterval(iv);
            load();
          }
        }, 1500);
      }
    };
    boot();
    return () => iv && clearInterval(iv);
  }, []);

  if (articles && articles.length === 0) {
    const pct = seed ? Math.round((seed.done / seed.total) * 100) : 0;
    return (
      <div className="max-w-[760px] mx-auto px-4 py-20 text-center">
        <Disc3 size={46} className="mx-auto text-[#3366cc] animate-spin" style={{ animationDuration: "3s" }} />
        <h1 className="wiki-serif text-2xl mt-6 text-[#202122]">Burning the archive to disc…</h1>
        <p className="text-sm text-[#54595d] mt-2">
          Fetching Wikipedia articles and writing text to the Text Disk and media to the Media Disk.
        </p>
        <div className="mt-6 h-2 bg-[#eaecf0] rounded-full overflow-hidden max-w-sm mx-auto">
          <div className="h-full bg-[#3366cc] transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mono text-xs text-[#72777d] mt-2">
          {seed ? `${seed.done}/${seed.total} · ${seed.current || "finalizing"}` : "initializing…"}
        </div>
      </div>
    );
  }

  const featured = articles?.[0];
  const rest = articles?.slice(1) || [];

  return (
    <div className="max-w-[1100px] mx-auto px-4 py-6">
      {/* Banner */}
      <section className="border border-[#c8ccd1] bg-[#f8f9fa] rounded-sm overflow-hidden mb-6">
        <div className="px-6 py-6">
          <h1 className="wiki-serif text-3xl text-[#000] mb-1">Welcome to Offline Wikipedia</h1>
          <p className="text-sm text-[#54595d]">
            The free encyclopedia — hosted entirely on two M-Discs, with{" "}
            <b>no internet connection</b>. Text streams from Drive 0, media from Drive 1,
            played back simultaneously.
          </p>
          <div className="flex flex-wrap gap-4 mt-4 mono text-xs">
            <span className="flex items-center gap-1.5 text-[#15803d]"><FileText size={13} /> {status?.text_disk?.article_count ?? "—"} articles on Text Disk</span>
            <span className="flex items-center gap-1.5 text-[#b45309]"><ImageIcon size={13} /> {status?.media_disk?.image_count ?? "—"} images on Media Disk</span>
            <span className="flex items-center gap-1.5 text-[#54595d]"><WifiOff size={13} /> served offline</span>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-8">
        <main>
          {featured && (
            <section className="mb-8">
              <h2 className="wiki-serif text-xl text-[#000] border-b border-[#eaecf0] pb-1 mb-3">
                From today's featured article
              </h2>
              <Link to={`/wiki/${featured.slug}`} data-testid="featured-article" className="flex flex-col sm:flex-row gap-4 group">
                {featured.lead_media_id && (
                  <div className="sm:w-48 shrink-0 bg-[#f8f9fa] border border-[#c8ccd1] p-1 self-start">
                    <img src={mediaUrl(featured.lead_media_id)} alt="" className="w-full h-auto" />
                  </div>
                )}
                <div>
                  <h3 className="wiki-serif text-lg text-[#3366cc] group-hover:underline">{featured.title}</h3>
                  <p className="article-body mt-1">{featured.description || "Read this featured article from the offline archive."}</p>
                  <span className="inline-flex items-center gap-1 text-[#3366cc] text-sm mt-2 group-hover:underline">
                    Read more <ChevronRight size={14} />
                  </span>
                </div>
              </Link>
            </section>
          )}

          <section>
            <h2 className="wiki-serif text-xl text-[#000] border-b border-[#eaecf0] pb-1 mb-3">
              From the archive
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {rest.map((a) => <Card key={a.slug} a={a} />)}
            </div>
          </section>
        </main>

        <aside className="space-y-4">
          <div className="border border-[#c8ccd1] bg-[#f8f9fa] rounded-sm p-4">
            <h3 className="wiki-serif text-base text-[#000] border-b border-[#eaecf0] pb-1 mb-2">This archive</h3>
            <ul className="text-sm text-[#202122] space-y-1.5">
              <li className="flex justify-between"><span>Reader / writer</span><b className="text-right">{status?.hardware?.drive_model || "ASUS ZenDrive"}</b></li>
              <li className="flex justify-between"><span>Medium</span><b className="text-right text-xs">Verbatim M-DISC 100GB</b></li>
              <li className="flex justify-between"><span>Text Disk used</span><b>{fmtBytes(status?.text_disk?.used_bytes || 0)}</b></li>
              <li className="flex justify-between"><span>Media Disk used</span><b>{fmtBytes(status?.media_disk?.used_bytes || 0)}</b></li>
            </ul>
          </div>
          <div className="border border-[#c8ccd1] rounded-sm p-4">
            <h3 className="wiki-serif text-base text-[#000] border-b border-[#eaecf0] pb-1 mb-2">Did you know…</h3>
            <p className="text-sm text-[#202122] leading-relaxed">
              …that an M-DISC etches data into a rock-like layer rated to last
              <b> up to 1,000 years</b>, making it ideal for a truly offline
              encyclopedia that outlives the servers it was copied from?
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
