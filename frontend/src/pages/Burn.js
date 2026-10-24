/**
 * Burn to Disc screen. Holds the live state of the two background jobs (growing the archive and
 * building disc images) and lays out the sections, which live in components/burn/.
 */
import React, { useEffect, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { http, API } from "@/lib/api";
import { useDisks } from "@/context/DiskContext";
import { KitSection } from "@/components/KitSection";
import { ArchiveStats } from "@/components/burn/ArchiveStats";
import { CapacityPlanner } from "@/components/burn/CapacityPlanner";
import { GrowArchive } from "@/components/burn/GrowArchive";
import { BuildDiscImages } from "@/components/burn/BuildDiscImages";

const openPreview = () => window.open(`${API}/preview/index.html`, "_blank", "noopener");

export default function Burn() {
  const { status, refreshStatus } = useDisks();
  const [seed, setSeed] = useState(null);
  const [burn, setBurn] = useState(null);
  const [exportRec, setExportRec] = useState(null);
  const [target, setTarget] = useState(150);
  const [themes, setThemes] = useState([]);
  const [theme, setTheme] = useState("");
  const seedPoll = useRef(null);
  const burnPoll = useRef(null);

  const loadBurn = useCallback(async () => {
    const { data } = await http.get("/burn/status");
    setBurn(data.burn);
    setExportRec(data.export);
    return data.burn;
  }, []);

  useEffect(() => {
    loadBurn();
    http.get("/seed/status").then(({ data }) => setSeed(data));
    http.get("/seed/themes").then(({ data }) => setThemes(data)).catch((e) => console.warn("themes unavailable", e));
    return () => {
      clearInterval(seedPoll.current);
      clearInterval(burnPoll.current);
    };
  }, [loadBurn]);

  // Start growing the archive, then check progress every 2 seconds until it finishes.
  const grow = async () => {
    await http.post("/seed/expand", null, { params: { target, ...(theme ? { theme } : {}) } });
    clearInterval(seedPoll.current);
    seedPoll.current = setInterval(async () => {
      const { data } = await http.get("/seed/status");
      setSeed(data);
      refreshStatus();
      if (data.state === "done") clearInterval(seedPoll.current);
    }, 2000);
  };

  // Start building the two disc images, then check progress until done or failed.
  const build = async () => {
    await http.post("/burn");
    clearInterval(burnPoll.current);
    burnPoll.current = setInterval(async () => {
      const b = await loadBurn();
      if (b.state === "done" || b.state === "error") clearInterval(burnPoll.current);
    }, 2500);
  };

  return (
    <div className="max-w-[1000px] mx-auto px-4 py-6">
      <Link to="/" className="inline-flex items-center gap-1 text-[#3366cc] text-sm hover:underline mb-3">
        <ArrowLeft size={14} /> Offline Wikipedia
      </Link>
      <h1 className="wiki-serif text-4xl text-[#000] border-b border-[#eaecf0] pb-2">Burn to Disc</h1>
      <p className="text-sm text-[#54595d] mt-2 max-w-2xl">
        Export the archive as two ISO 9660 disc images — one for the <b>Text Disc</b> and one for
        the <b>Media Disc</b> — ready to write to Verbatim M-DISC media with your ASUS ZenDrive.
        The Text Disc holds a fully browsable offline website; the Media Disc holds every image.
      </p>
      <ArchiveStats status={status} onPreview={openPreview} />
      <KitSection />
      <CapacityPlanner status={status} />
      <GrowArchive seed={seed} themes={themes} theme={theme} setTheme={setTheme}
        target={target} setTarget={setTarget} onGrow={grow} />
      <BuildDiscImages burn={burn} exportRec={exportRec} seedRunning={seed?.state === "running"}
        onBuild={build} onPreview={openPreview} />
    </div>
  );
}
