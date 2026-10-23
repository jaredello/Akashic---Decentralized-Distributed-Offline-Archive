import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";
import { http } from "@/lib/api";

const DiskContext = createContext(null);
export const useDisks = () => useContext(DiskContext);

const MAX_LOGS = 50;
const ts = () => new Date().toLocaleTimeString("en-GB", { hour12: false });

export const DiskProvider = ({ children }) => {
  const [status, setStatus] = useState(null);
  const [textActive, setTextActive] = useState(false);
  const [mediaActive, setMediaActive] = useState(false);
  const [session, setSession] = useState({ text: 0, media: 0, textReads: 0, mediaReads: 0 });
  const [logs, setLogs] = useState([]);
  const [monitorOpen, setMonitorOpen] = useState(true);
  const textTimer = useRef(null);
  const mediaTimer = useRef(null);

  const refreshStatus = useCallback(async () => {
    try {
      const { data } = await http.get("/disks/status");
      setStatus(data);
    } catch (e) {
      console.warn("disk status unavailable", e);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    const iv = setInterval(refreshStatus, 8000);
    return () => clearInterval(iv);
  }, [refreshStatus]);

  const pushLog = useCallback((disk, msg) => {
    setLogs((prev) => [{ t: ts(), disk, msg, key: Math.random() }, ...prev].slice(0, MAX_LOGS));
  }, []);

  const beginRead = useCallback((disk, label) => {
    if (disk === "text") {
      clearTimeout(textTimer.current);
      setTextActive(true);
      pushLog("text", `SEEK  ${label}`);
    } else {
      clearTimeout(mediaTimer.current);
      setMediaActive(true);
      pushLog("media", `SEEK  ${label}`);
    }
  }, [pushLog]);

  const endRead = useCallback((disk, { bytes = 0, label = "" } = {}) => {
    if (disk === "text") {
      setSession((s) => ({ ...s, text: s.text + bytes, textReads: s.textReads + 1 }));
      pushLog("text", `READ  ${label} · ${bytes} B`);
      textTimer.current = setTimeout(() => setTextActive(false), 220);
    } else {
      setSession((s) => ({ ...s, media: s.media + bytes, mediaReads: s.mediaReads + 1 }));
      pushLog("media", `READ  ${label} · ${bytes} B`);
      mediaTimer.current = setTimeout(() => setMediaActive(false), 220);
    }
  }, [pushLog]);

  const value = {
    status, refreshStatus, logs,
    textActive, mediaActive, session,
    beginRead, endRead, pushLog,
    monitorOpen, setMonitorOpen,
    toggleMonitor: () => setMonitorOpen((o) => !o),
  };
  return <DiskContext.Provider value={value}>{children}</DiskContext.Provider>;
};
