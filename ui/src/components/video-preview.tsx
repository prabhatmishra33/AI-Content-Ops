"use client";

import { useEffect, useState } from "react";
import { apiBlob } from "@/lib/api";
import { Spinner } from "@/components/spinner";

type Props = {
  videoId: string;
  className?: string;
};

export function VideoPreview({ videoId, className }: Props) {
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let thumbnailObj: string | null = null;
    let videoObj: string | null = null;
    let isMounted = true;

    const load = async () => {
      setError(null);
      setLoading(true);
      try {
        const t = await apiBlob(`/videos/${videoId}/thumbnail`);
        thumbnailObj = URL.createObjectURL(t);
        if (isMounted) setThumbnailUrl(thumbnailObj);
      } catch {
        if (isMounted) setThumbnailUrl(null);
      }
      try {
        const v = await apiBlob(`/videos/${videoId}/stream`);
        videoObj = URL.createObjectURL(v);
        if (isMounted) setVideoUrl(videoObj);
      } catch (e) {
        if (isMounted) setError(e instanceof Error ? e.message : "Preview unavailable");
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    load();
    return () => {
      isMounted = false;
      if (thumbnailObj) URL.revokeObjectURL(thumbnailObj);
      if (videoObj) URL.revokeObjectURL(videoObj);
    };
  }, [videoId]);

  return (
    <div className={className}>
      {loading ? (
        <div className="mb-2 flex h-16 items-center justify-center rounded-xl border border-slate-200 bg-slate-50">
          <span className="inline-flex items-center gap-2 text-sm text-slate-500">
            <Spinner size="sm" />
            Loading preview...
          </span>
        </div>
      ) : null}
      {thumbnailUrl ? (
        <img alt="Video thumbnail" className="mb-2 h-44 w-full rounded-xl border border-slate-200 object-cover shadow-sm" src={thumbnailUrl} />
      ) : (
        <div className="mb-2 flex h-44 w-full items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-100 text-sm text-slate-500">
          Thumbnail not available yet
        </div>
      )}
      {videoUrl ? (
        <video className="h-64 w-full rounded-xl border border-slate-200 bg-black shadow-sm" controls preload="metadata" src={videoUrl} />
      ) : (
        <div className="flex h-24 w-full items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-100 text-sm text-slate-500">
          Video preview not available
        </div>
      )}
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
