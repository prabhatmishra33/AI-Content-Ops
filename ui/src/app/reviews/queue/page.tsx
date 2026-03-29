"use client";

import Link from "next/link";
import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { generateIdempotencyKey } from "@/lib/idempotency";
import type { ReviewTask } from "@/lib/types";
import { Spinner } from "@/components/spinner";

export default function ReviewsQueuePage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [gate, setGate] = useState<"" | "GATE_1" | "GATE_2">(
    (searchParams.get("gate") as "" | "GATE_1" | "GATE_2") || ""
  );
  const [status, setStatus] = useState(searchParams.get("status") || "PENDING");
  const [reviewerRef, setReviewerRef] = useState(searchParams.get("reviewer_ref") || "moderator_1");
  const [error, setError] = useState<string | null>(null);
  const [claimingTaskId, setClaimingTaskId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const syncQueryState = (next: { gate?: string; status?: string; reviewer_ref?: string }) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next.gate !== undefined) {
      if (next.gate) params.set("gate", next.gate);
      else params.delete("gate");
    }
    if (next.status !== undefined) params.set("status", next.status);
    if (next.reviewer_ref !== undefined) params.set("reviewer_ref", next.reviewer_ref);
    router.replace(`${pathname}?${params.toString()}`);
  };

  const q = useQuery({
    queryKey: ["review-tasks", gate, status],
    queryFn: () =>
      apiRequest<ReviewTask[]>(
        `/reviews/tasks?status=${encodeURIComponent(status)}${gate ? `&gate=${encodeURIComponent(gate)}` : ""}`
      ),
    refetchInterval: 5000
  });

  const claimTask = async (taskId: string) => {
    setError(null);
    setClaimingTaskId(taskId);
    try {
      await apiRequest(`/reviews/tasks/${taskId}/claim?reviewer_ref=${encodeURIComponent(reviewerRef)}`, {
        method: "POST",
        idempotencyKey: generateIdempotencyKey(`claim-${taskId}`)
      });
      await queryClient.invalidateQueries({ queryKey: ["review-tasks"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Claim failed");
    } finally {
      setClaimingTaskId(null);
    }
  };

  const queueContext = encodeURIComponent(
    `/reviews/queue?status=${encodeURIComponent(status)}${gate ? `&gate=${encodeURIComponent(gate)}` : ""}&reviewer_ref=${encodeURIComponent(reviewerRef)}`
  );

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">Review Inbox</h1>
        <p className="mt-1 text-sm text-blue-100">Pick pending items, avoid overlap, and complete approval decisions.</p>
      </div>

      <div className="card grid gap-3 md:grid-cols-4">
        <div>
          <label className="label">Review Stage</label>
          <select
            className="input mt-1"
            value={gate}
            onChange={(e) => {
              const v = e.target.value as "" | "GATE_1" | "GATE_2";
              setGate(v);
              syncQueryState({ gate: v });
            }}
          >
            <option value="">All</option>
            <option value="GATE_1">GATE_1</option>
            <option value="GATE_2">GATE_2</option>
          </select>
        </div>
        <div>
          <label className="label">Task Status</label>
          <select
            className="input mt-1"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              syncQueryState({ status: e.target.value });
            }}
          >
            <option value="PENDING">PENDING</option>
            <option value="IN_PROGRESS">IN_PROGRESS</option>
            <option value="DONE">DONE</option>
          </select>
        </div>
        <div>
          <label className="label">Reviewer ID</label>
          <input
            className="input mt-1"
            value={reviewerRef}
            onChange={(e) => {
              setReviewerRef(e.target.value);
              syncQueryState({ reviewer_ref: e.target.value });
            }}
          />
        </div>
      </div>

      {error ? <div className="card"><span className="chip-danger">{error}</span></div> : null}

      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>Task</th>
              <th>Process</th>
              <th>Video</th>
              <th>Stage</th>
              <th>Urgency</th>
              <th>Status</th>
              <th>Reviewer</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading ? (
              <tr>
                <td className="py-8 text-center" colSpan={8}>
                  <span className="inline-flex items-center gap-2 text-sm text-slate-500">
                    <Spinner size="sm" />
                    Loading review items...
                  </span>
                </td>
              </tr>
            ) : null}
            {(q.data ?? []).map((t) => (
              <tr key={t.task_id}>
                <td>{t.task_id}</td>
                <td>{t.job_id}</td>
                <td>{t.video_id}</td>
                <td><span className="chip">{t.gate}</span></td>
                <td><span className="chip">{t.priority}</span></td>
                <td>{t.status === "PENDING" ? <span className="chip-warn">{t.status}</span> : <span className="chip-success">{t.status}</span>}</td>
                <td>{t.reviewer_ref ?? "-"}</td>
                <td>
                  <div className="flex flex-wrap items-center gap-2">
                  <button
                    className="btn-secondary"
                    disabled={claimingTaskId === t.task_id}
                    onClick={() => claimTask(t.task_id)}
                  >
                    {claimingTaskId === t.task_id ? (
                      <span className="inline-flex items-center gap-2">
                        <Spinner size="sm" />
                        Assigning...
                      </span>
                    ) : (
                      "Assign to Me"
                    )}
                  </button>
                  <Link className="btn-secondary" href={`/reviews/tasks/${t.task_id}?from=${queueContext}`}>
                    Review Now
                  </Link>
                  <Link className="btn-secondary" href={`/videos/${t.video_id}?from=${queueContext}`}>
                    View Video Details
                  </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
