"use client";

import { useEffect, useState } from "react";
import { apiBlob } from "@/lib/api";

type Props = {
  videoId: string;
  size?: number;
};

export function VideoThumb({ videoId, size = 38 }: Props) {
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let mounted = true;

    const load = async () => {
      try {
        const blob = await apiBlob(`/videos/${videoId}/thumbnail`);
        objectUrl = URL.createObjectURL(blob);
        if (mounted) setThumbUrl(objectUrl);
      } catch {
        if (mounted) setThumbUrl(null);
      }
    };

    load();
    return () => {
      mounted = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [videoId]);

  if (!thumbUrl) {
    return (
      <div
        className="flex items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-100 text-[10px] text-slate-500"
        style={{ width: size, height: size }}
        title={videoId}
      >
        N/A
      </div>
    );
  }

  return (
    <img
      alt="Video thumbnail"
      className="rounded-md border border-slate-200 object-cover"
      src={thumbUrl}
      style={{ width: size, height: size }}
      title={videoId}
    />
  );
}
