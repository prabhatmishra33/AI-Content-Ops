"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { Spinner } from "@/components/spinner";
import { VideoThumb } from "@/components/video-thumb";
import { useSessionStore } from "@/store/session-store";

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

const STATE_LABEL: Record<string, string> = {
  PENDING: "In Review",
  PROCESSING: "Processing",
  APPROVED: "Approved",
  REJECTED: "Not Approved",
  PUBLISHED: "Published",
};

function stateLabel(state: string) {
  return STATE_LABEL[state] ?? state;
}

function stateClass(state: string) {
  if (state === "APPROVED" || state === "PUBLISHED") return "chip-success";
  if (state === "REJECTED") return "chip-danger";
  if (state === "PROCESSING") return "chip-warn";
  return "chip";
}

export default function VideoHistoryPage() {
  const user = useSessionStore((s) => s.user);
  const isUploader = user?.role === "uploader";

  const q = useQuery({
    queryKey: ["video-history"],
    queryFn: () => apiRequest<VideoHistoryItem[]>("/videos/history"),
    refetchInterval: 8000
  });

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">
          {isUploader ? "My Videos" : "Uploaded Videos"}
        </h1>
        <p className="mt-1 text-sm text-blue-100">
          {isUploader
            ? "Track your submissions and see their current review status."
            : "All videos submitted by contributors on the platform."}
        </p>
      </div>

      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>Preview</th>
              <th>Filename</th>
              <th>Submitted</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading ? (
              <tr>
                <td className="py-8 text-center" colSpan={5}>
                  <span className="inline-flex items-center gap-2 text-sm text-slate-500">
                    <Spinner size="sm" />
                    Loading your videos...
                  </span>
                </td>
              </tr>
            ) : null}
            {q.isError ? (
              <tr>
                <td className="py-8 text-center text-sm text-rose-600" colSpan={5}>
                  {q.error instanceof Error ? q.error.message : "Unable to load upload history"}
                </td>
              </tr>
            ) : null}
            {!q.isLoading && !q.isError && (q.data ?? []).length === 0 ? (
              <tr>
                <td className="py-8 text-center text-sm text-slate-500" colSpan={5}>
                  You haven&apos;t submitted any videos yet.
                </td>
              </tr>
            ) : null}
            {(q.data ?? []).map((v) => (
              <tr key={v.video_id}>
                <td><VideoThumb videoId={v.video_id} /></td>
                <td>{v.filename}</td>
                <td>{new Date(v.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</td>
                <td><span className={stateClass(v.state)}>{stateLabel(v.state)}</span></td>
                <td>
                  <Link className="btn-secondary" href={`/videos/${v.video_id}`}>
                    View
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
