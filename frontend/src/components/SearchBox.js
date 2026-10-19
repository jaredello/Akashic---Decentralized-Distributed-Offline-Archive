import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { http } from "@/lib/api";

export const SearchBox = () => {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    const id = setTimeout(async () => {
      try {
        const { data } = await http.get("/search", { params: { q } });
        setResults(data);
        setOpen(true);
      } catch (e) {
        setResults([]);
      }
    }, 180);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    const onClick = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const go = (slug) => {
    setOpen(false);
    setQ("");
    navigate(`/wiki/${slug}`);
  };

  return (
    <div className="relative w-full max-w-[420px]" ref={boxRef} data-testid="search-container">
      <div className="flex items-center w-full bg-white border border-[#a2a9b1] rounded-sm h-9 px-2 focus-within:border-[#3366cc] focus-within:ring-1 focus-within:ring-[#3366cc]">
        <Search size={16} className="text-[#54595d] shrink-0" />
        <input
          data-testid="search-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          placeholder="Search the offline archive"
          className="w-full bg-transparent outline-none px-2 text-sm text-[#202122] placeholder:text-[#72777d]"
          onKeyDown={(e) => {
            if (e.key === "Enter" && results[0]) go(results[0].slug);
          }}
        />
      </div>
      {open && results.length > 0 && (
        <ul
          data-testid="search-results"
          className="absolute z-50 mt-1 w-full bg-white border border-[#a2a9b1] rounded-sm shadow-lg overflow-hidden"
        >
          {results.map((r) => (
            <li key={r.slug}>
              <button
                data-testid={`search-result-${r.slug}`}
                onClick={() => go(r.slug)}
                className="w-full text-left px-3 py-2 hover:bg-[#eaf3ff] border-b border-[#eaecf0] last:border-0"
              >
                <div className="text-sm text-[#202122] font-medium">{r.title}</div>
                {r.description && (
                  <div className="text-xs text-[#72777d] truncate">{r.description}</div>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
