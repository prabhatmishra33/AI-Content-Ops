"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { Spinner } from "@/components/spinner";
import { VideoThumb } from "@/components/video-thumb";

type VideoHistoryItem = {
  video_id: string;
  uploader_ref: string;
  filename: string;
  thumbnail_uri?: string | null;
  created_at: string;
  job_id?: string | null;
  state: string;
  priority: string;
};

export default function VideoHistoryPage() {
  const q = useQuery({
    queryKey: ["video-history"],
    queryFn: () => apiRequest<VideoHistoryItem[]>("/videos/history"),
    refetchInterval: 8000
  });

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">My Uploaded Videos</h1>
        <p className="mt-1 text-sm text-blue-100">Track all your uploads and open each timeline to see full workflow progress.</p>
      </div>

      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>Preview</th>
              <th>Filename</th>
              <th>Submitted</th>
              <th>State</th>
              <th>Priority</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading ? (
              <tr>
                <td className="py-8 text-center" colSpan={6}>
                  <span className="inline-flex items-center gap-2 text-sm text-slate-500">
                    <Spinner size="sm" />
                    Loading upload history...
                  </span>
                </td>
              </tr>
            ) : null}
            {q.isError ? (
              <tr>
                <td className="py-8 text-center text-sm text-rose-600" colSpan={6}>
                  {q.error instanceof Error ? q.error.message : "Unable to load upload history"}
                </td>
              </tr>
            ) : null}
            {!q.isLoading && !q.isError && (q.data ?? []).length === 0 ? (
              <tr>
                <td className="py-8 text-center text-sm text-slate-500" colSpan={6}>
                  No uploads found yet.
                </td>
              </tr>
            ) : null}
            {(q.data ?? []).map((v) => (
              <tr key={v.video_id}>
                <td><VideoThumb videoId={v.video_id} /></td>
                <td>{v.filename}</td>
                <td>{new Date(v.created_at).toLocaleString()}</td>
                <td><span className="chip">{v.state}</span></td>
                <td><span className="chip">{v.priority}</span></td>
                <td>
                  <Link className="btn-secondary" href={`/videos/${v.video_id}`}>
                    Open Timeline
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
