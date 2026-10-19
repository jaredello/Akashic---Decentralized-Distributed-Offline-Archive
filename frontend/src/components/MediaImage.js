import React, { useEffect, useState } from "react";
import { mediaUrl, http } from "@/lib/api";
import { useDisks } from "@/context/DiskContext";

// Fetches an image from the Media Disk as a blob so the read is measured and
// the Media Disk activity LED fires, demonstrating the second data source.
export const MediaImage = ({ id, caption, className = "", imgClassName = "", onLoaded, delay = 0 }) => {
  const { beginRead, endRead } = useDisks();
  const [src, setSrc] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked = null;
    let alive = true;
    const run = async () => {
      beginRead("media", (caption || "image").slice(0, 28));
      try {
        const res = await http.get(`/media/${id}`, { responseType: "blob" });
        if (!alive) return;
        const url = URL.createObjectURL(res.data);
        revoked = url;
        setSrc(url);
        endRead("media", { bytes: res.data.size, label: (caption || "image").slice(0, 28) });
      } catch (e) {
        if (!alive) return;
        setFailed(true);
        endRead("media", { bytes: 0, label: "ERR" });
      } finally {
        onLoaded && onLoaded();
      }
    };
    const t = setTimeout(run, delay);
    return () => {
      alive = false;
      clearTimeout(t);
      if (revoked) URL.revokeObjectURL(revoked);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (failed) return null;

  return (
    <figure
      data-testid={`media-figure-${id}`}
      className={`bg-[#f8f9fa] border border-[#c8ccd1] p-1 ${className}`}
    >
      {src ? (
        <img
          src={src}
          alt={caption || ""}
          className={`block w-full h-auto fade-in ${imgClassName}`}
        />
      ) : (
        <div className="w-full aspect-[4/3] bg-[#eaecf0] animate-pulse flex items-center justify-center">
          <span className="mono text-[10px] text-[#72777d]">READING MEDIA DISK…</span>
        </div>
      )}
      {caption && (
        <figcaption className="text-[11px] leading-snug text-[#54595d] px-1 py-1">
          {caption}
        </figcaption>
      )}
    </figure>
  );
};

export { mediaUrl };
