"use client";

import { useState } from "react";
import Link from "next/link";
import { apiRequest } from "@/lib/api";
import { generateIdempotencyKey } from "@/lib/idempotency";
import type { VideoUploadResponse } from "@/lib/types";
import { VideoPreview } from "@/components/video-preview";
import { Spinner } from "@/components/spinner";
import { useSessionStore } from "@/store/session-store";

export default function UploadVideoPage() {
  const user = useSessionStore((s) => s.user);
  const uploaderRef = user?.username ?? "";
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<VideoUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploaderRef) {
      setError("Unable to detect logged-in user. Please login again.");
      return;
    }
    if (!file) {
      setError("Please select a file");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const idem = generateIdempotencyKey("upload");
      const form = new FormData();
      form.append("uploader_ref", uploaderRef);
      form.append("idempotency_key", idem);
      form.append("file", file);
      const data = await apiRequest<VideoUploadResponse>("/videos/upload/file", {
        method: "POST",
        body: form,
        isFormData: true,
        idempotencyKey: idem
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">Submit a Video</h1>
        <p className="mt-1 text-sm text-blue-100">Upload from your device and start the review and publishing process.</p>
      </div>

      <form className="card space-y-4" onSubmit={onUpload}>
        <div>
          <label className="label">Video File</label>
          <p className="mb-2 text-xs text-slate-500">Accepted formats: MP4, MOV, AVI, WebM</p>
          <input
            className="mt-1 block w-full cursor-pointer rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-1.5 file:text-sm file:font-medium"
            type="file"
            accept="video/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        {error ? <p className="chip-danger">{error}</p> : null}
        <button className="btn-primary" disabled={loading || !file} type="submit">
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <Spinner size="sm" className="border-white/40 border-t-white" />
              Uploading...
            </span>
          ) : (
            "Submit Video"
          )}
        </button>
      </form>

      {result ? (
        <div className="card space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              ✓
            </div>
            <div>
              <p className="font-semibold text-slate-800">Video submitted successfully!</p>
              <p className="text-sm text-slate-500">Your video is now in the review queue.</p>
            </div>
          </div>
          <VideoPreview videoId={result.video_id} />
          <Link className="btn-primary" href={`/videos/${result.video_id}`}>
            Track Progress
          </Link>
        </div>
      ) : null}
    </div>
  );
}
