/**
 * Top bar on every page: logo, search, and links to Source, Burn to Disc and the Disk Monitor.
 */
import React from "react";
import { Link } from "react-router-dom";
import { BookOpen, HardDrive, WifiOff, Disc3, Code2 } from "lucide-react";
import { SearchBox } from "@/components/SearchBox";
import { useDisks } from "@/context/DiskContext";

export const Header = () => {
  const { toggleMonitor, monitorOpen, textActive, mediaActive } = useDisks();
  return (
    <header className="sticky top-0 z-40 bg-white border-b border-[#a2a9b1]">
      <div className="flex items-center gap-4 px-4 h-14 max-w-[1280px] mx-auto">
        <Link to="/" data-testid="home-link" className="flex items-center gap-2 shrink-0 group">
          <div className="w-9 h-9 rounded-full border border-[#c8ccd1] flex items-center justify-center bg-[#f8f9fa]">
            <BookOpen size={18} className="text-[#202122]" />
          </div>
          <div className="leading-none hidden sm:block">
            <div className="wiki-serif text-[17px] text-[#202122] group-hover:text-[#2a4b8d]">
              Offline Wikipedia
            </div>
            <div className="text-[10px] text-[#72777d] tracking-wide">
              The Free M-Disc Encyclopedia
            </div>
          </div>
        </Link>

        <div className="flex-1 flex justify-center px-2">
          <SearchBox />
        </div>

        <div className="hidden md:flex items-center gap-2 px-2.5 py-1 bg-[#f8f9fa] border border-[#a2a9b1] rounded-sm text-[#202122] text-xs font-semibold">
          <WifiOff size={13} className="text-[#54595d]" />
          OFFLINE · SERVED FROM DISC
        </div>

        <Link
          to="/source"
          data-testid="source-link"
          className="hidden sm:flex items-center gap-2 px-3 h-9 rounded-sm border border-[#a2a9b1] bg-white text-[#202122] text-xs font-semibold hover:bg-[#f8f9fa] transition-colors"
          title="Read the app's open-source code"
        >
          <Code2 size={15} className="text-[#3366cc]" />
          <span className="mono">SOURCE</span>
        </Link>

        <Link
          to="/burn"
          data-testid="burn-link"
          className="hidden sm:flex items-center gap-2 px-3 h-9 rounded-sm border border-[#a2a9b1] bg-white text-[#202122] text-xs font-semibold hover:bg-[#f8f9fa] transition-colors"
          title="Export the archive to disc images"
        >
          <Disc3 size={15} className="text-[#3366cc]" />
          <span className="mono">BURN TO DISC</span>
        </Link>

        <button
          data-testid="toggle-monitor"
          onClick={toggleMonitor}
          className={`relative flex items-center gap-2 px-3 h-9 rounded-sm border text-xs font-semibold transition-colors ${
            monitorOpen
              ? "bg-[#0A0A0A] border-[#0A0A0A] text-[#00FF41]"
              : "bg-white border-[#a2a9b1] text-[#202122] hover:bg-[#f8f9fa]"
          }`}
          title="Toggle Disk Monitor"
        >
          <HardDrive size={15} />
          <span className="hidden sm:inline mono">DISK MONITOR</span>
          <span className="flex gap-1">
            <i className={`w-1.5 h-1.5 rounded-full ${textActive ? "bg-[#00FF41] led-active" : "bg-[#2a7d3a]"}`} />
            <i className={`w-1.5 h-1.5 rounded-full ${mediaActive ? "bg-[#FFB000] led-active" : "bg-[#7d5a1f]"}`} />
          </span>
        </button>
      </div>
    </header>
  );
};
