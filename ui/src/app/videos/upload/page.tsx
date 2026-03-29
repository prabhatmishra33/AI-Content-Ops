"use client";

import { useState } from "react";
import Link from "next/link";
import { apiRequest } from "@/lib/api";
import { generateIdempotencyKey } from "@/lib/idempotency";
import type { VideoUploadResponse } from "@/lib/types";
import { VideoPreview } from "@/components/video-preview";
import { Spinner } from "@/components/spinner";

export default function UploadVideoPage() {
  const [uploaderRef, setUploaderRef] = useState("demo_user_1");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<VideoUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onUpload = async (e: React.FormEvent) => {
    e.preventDefault();
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

      <form className="card space-y-3" onSubmit={onUpload}>
        <div>
          <label className="label">Your User ID</label>
          <input className="input mt-1" value={uploaderRef} onChange={(e) => setUploaderRef(e.target.value)} />
        </div>
        <div>
          <label className="label">Video File</label>
          <input className="mt-1 block text-sm" type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        {error ? <p className="chip-danger">{error}</p> : null}
        <button className="btn-primary" disabled={loading} type="submit">
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <Spinner size="sm" className="border-white/40 border-t-white" />
              Uploading...
            </span>
          ) : (
            "Upload"
          )}
        </button>
      </form>

      {result ? (
        <div className="card space-y-3 text-sm">
          <h2 className="section-title">Submission Details</h2>
          <p>
            <span className="font-medium">video_id:</span> {result.video_id}
          </p>
          <p>
            <span className="font-medium">job_id:</span> {result.job_id}
          </p>
          <p>
            <span className="font-medium">thumbnail_uri:</span> {result.thumbnail_uri ?? "null"}
          </p>
          <VideoPreview videoId={result.video_id} />
          <div className="flex gap-2">
            <Link className="btn-primary" href={`/videos/${result.video_id}`}>
              Open Video Timeline
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
