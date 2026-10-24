/**
 * "Grow the archive": pick a topic and a target size, then follow Wikipedia's links to add
 * the most interlinked related articles. Shows live progress while it runs.
 */
import React from "react";
import { Sparkles, Loader2 } from "lucide-react";

const ThemeChips = ({ themes, theme, setTheme, disabled }) => (
  <div className="flex flex-wrap gap-2 mb-4" data-testid="theme-chips">
    {[{ key: "", label: "Everything" }, ...themes].map((t) => {
      const selected = theme === t.key;
      const look = selected
        ? "bg-[#3366cc] border-[#3366cc] text-white"
        : "bg-white border-[#a2a9b1] text-[#202122] hover:bg-[#f8f9fa]";
      return (
        <button
          key={t.key || "all"}
          onClick={() => setTheme(t.key)}
          disabled={disabled}
          data-testid={`theme-${t.key || "all"}`}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors disabled:opacity-50 ${look}`}
        >
          {t.label}
        </button>
      );
    })}
  </div>
);

const GrowProgress = ({ seed }) => {
  const discovering = seed.phase === "discovering";
  const pct = seed.total ? Math.round((seed.done / seed.total) * 100) : 0;
  return (
    <div className="mt-4" data-testid="grow-progress">
      <div className="h-2 bg-[#eaecf0] rounded-full overflow-hidden">
        <div className="h-full bg-[#3366cc] transition-all" style={{ width: `${discovering ? 8 : pct}%` }} />
      </div>
      <div className="mono text-xs text-[#72777d] mt-1">
        {discovering ? "Mapping Wikipedia links…" : `Writing to discs ${seed.done}/${seed.total}`} · {seed.current}
      </div>
    </div>
  );
};

export const GrowArchive = ({ seed, themes, theme, setTheme, target, setTarget, onGrow }) => {
  const running = seed?.state === "running";
  return (
    <section className="mt-8 border border-[#c8ccd1] rounded-sm p-5">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={17} className="text-[#3366cc]" />
        <h2 className="wiki-serif text-xl text-[#000]">Grow the archive</h2>
      </div>
      <p className="text-sm text-[#54595d] mb-4">
        Crawl Wikipedia's link graph outward and pull in the most densely interlinked pages,
        so the offline copy reads like the real site. Pick a theme to grow a tight web around
        one subject, or leave it on <b>Everything</b> to expand the whole archive.
      </p>
      <label className="text-xs text-[#54595d] mono block mb-2">PICK A TOPIC</label>
      <ThemeChips themes={themes} theme={theme} setTheme={setTheme} disabled={running} />
      <div className="flex flex-col sm:flex-row sm:items-end gap-4">
        <div>
          <label className="text-xs text-[#54595d] mono block mb-1">TARGET ARTICLE COUNT</label>
          <input
            type="range" min="30" max="400" step="10" value={target}
            data-testid="grow-target"
            onChange={(e) => setTarget(Number(e.target.value))}
            disabled={running}
            className="w-56 accent-[#3366cc] align-middle"
          />
          <span className="mono text-sm text-[#202122] ml-3">{target}</span>
        </div>
        <button
          onClick={onGrow}
          disabled={running}
          data-testid="grow-archive-btn"
          className="flex items-center gap-2 h-10 px-5 rounded-sm bg-[#3366cc] text-white text-sm font-semibold hover:bg-[#2a4b8d] disabled:opacity-50 transition-colors"
        >
          {running ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
          {running ? "Growing…" : "Grow archive"}
        </button>
      </div>
      {running && <GrowProgress seed={seed} />}
      {!running && seed?.errors?.length > 0 && (
        <div className="mono text-[11px] text-[#b45309] mt-3">{seed.errors.length} article(s) skipped during last run.</div>
      )}
    </section>
  );
};
