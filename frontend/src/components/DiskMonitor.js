import React, { useEffect, useRef } from "react";
import { Disc3, X, Cpu, Activity } from "lucide-react";
import { useDisks } from "@/context/DiskContext";
import { fmtBytes } from "@/lib/api";

const DriveCard = ({ disk, active, sessionBytes, sessionReads, accent }) => {
  if (!disk) return null;
  const pct = disk.total_bytes ? (disk.used_bytes / disk.total_bytes) * 100 : 0;
  const count = disk.article_count ?? disk.image_count ?? 0;
  const countLabel = disk.article_count != null ? "ARTICLES" : "IMAGES";
  return (
    <div className="border border-[#1f1f1f] bg-[#121212] p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Disc3
            size={16}
            className={active ? "led-active" : ""}
            style={{ color: active ? accent : "#3a3a3a" }}
          />
          <span className="mono text-[11px] text-white font-bold tracking-widest">{disk.label}</span>
        </div>
        <span className="mono text-[9px] text-[#555]">{disk.slot}</span>
      </div>

      <div className="flex items-center gap-2 mb-2">
        <i
          className={`w-2.5 h-2.5 rounded-full ${active ? "led-active" : ""}`}
          style={{ color: active ? accent : "#333", background: active ? accent : "#333", boxShadow: active ? `0 0 8px ${accent}` : "none" }}
        />
        <span className="mono text-[10px]" style={{ color: active ? accent : "#5a5a5a" }}>
          {active ? "READING…" : disk.status}
        </span>
      </div>

      <div className="mono text-[9px] text-[#6b6b6b] leading-relaxed mb-1">
        <div className="truncate">DRV {disk.drive}</div>
        <div className="truncate">MED {disk.medium}</div>
      </div>

      <div className="h-1.5 bg-[#000] border border-[#222] my-2 relative overflow-hidden">
        <div
          className="h-full"
          style={{ width: `${Math.max(pct, disk.used_bytes > 0 ? 0.6 : 0)}%`, background: accent }}
        />
      </div>
      <div className="flex justify-between mono text-[9px] text-[#6b6b6b]">
        <span>{fmtBytes(disk.used_bytes)} used</span>
        <span>of 100 GB</span>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3 pt-2 border-t border-[#1f1f1f]">
        <div>
          <div className="mono text-[8px] text-[#555] tracking-wider">{countLabel}</div>
          <div className="mono text-sm text-white">{count}</div>
        </div>
        <div>
          <div className="mono text-[8px] text-[#555] tracking-wider">READ (SESSION)</div>
          <div className="mono text-sm" style={{ color: accent }}>{fmtBytes(sessionBytes)}</div>
          <div className="mono text-[8px] text-[#555]">{sessionReads} ops</div>
        </div>
      </div>
    </div>
  );
};

export const DiskMonitor = () => {
  const { monitorOpen, setMonitorOpen, status, logs, textActive, mediaActive, session } = useDisks();
  const logEnd = useRef(null);

  useEffect(() => {
    // newest first; keep scrolled to top
  }, [logs]);

  const hw = status?.hardware;

  return (
    <>
      {monitorOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setMonitorOpen(false)}
        />
      )}
      <aside
        data-testid="disk-monitor"
        className={`fixed right-0 top-14 bottom-0 w-[320px] max-w-[88vw] bg-[#0A0A0A] border-l border-[#1f1f1f] z-50 flex flex-col monitor-scanlines transition-transform duration-300 ${
          monitorOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1f1f1f]">
          <div className="flex items-center gap-2">
            <Cpu size={15} className="text-[#00FF41]" />
            <span className="mono text-[11px] text-white font-bold tracking-widest">DISK MONITOR</span>
          </div>
          <button
            data-testid="close-monitor"
            onClick={() => setMonitorOpen(false)}
            className="text-[#777] hover:text-white"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-4 py-2 border-b border-[#1f1f1f]">
          <div className="mono text-[9px] text-[#6b6b6b] leading-relaxed">
            CONTROLLER · {hw ? `${hw.drive_count}× ${hw.drive_model}` : "—"}
          </div>
          <div className="mono text-[9px] text-[#4a4a4a]">
            DUAL-DRIVE PARALLEL STREAM · NO NETWORK
          </div>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto monitor-log flex-1">
          <DriveCard
            disk={status?.text_disk}
            active={textActive}
            sessionBytes={session.text}
            sessionReads={session.textReads}
            accent="#00FF41"
          />
          <DriveCard
            disk={status?.media_disk}
            active={mediaActive}
            sessionBytes={session.media}
            sessionReads={session.mediaReads}
            accent="#FFB000"
          />

          <div className="border border-[#1f1f1f] bg-[#0d0d0d]">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-[#1f1f1f]">
              <Activity size={12} className="text-[#00FF41]" />
              <span className="mono text-[10px] text-[#9a9a9a] tracking-widest">I/O LOG</span>
            </div>
            <div className="p-2 space-y-0.5 max-h-56 overflow-y-auto monitor-log" data-testid="io-log">
              {logs.length === 0 && (
                <div className="mono text-[10px] text-[#444] px-1 py-2">
                  awaiting disc read…
                </div>
              )}
              {logs.map((l) => (
                <div key={l.key} className="mono text-[10px] flex gap-2 px-1">
                  <span className="text-[#444]">{l.t}</span>
                  <span style={{ color: l.disk === "text" ? "#00FF41" : "#FFB000" }}>
                    {l.disk === "text" ? "T0" : "M1"}
                  </span>
                  <span className="text-[#8a8a8a] truncate">{l.msg}</span>
                </div>
              ))}
              <div ref={logEnd} />
            </div>
          </div>
        </div>

        <div className="px-4 py-2 border-t border-[#1f1f1f]">
          <div className="mono text-[8px] text-[#3f3f3f] leading-relaxed">
            Software demonstration. Each logical disk maps to a physical M-DISC
            read from its own ZenDrive in the hardware build.
          </div>
        </div>
      </aside>
    </>
  );
};
