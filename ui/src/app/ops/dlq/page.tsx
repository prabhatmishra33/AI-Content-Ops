"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { generateIdempotencyKey } from "@/lib/idempotency";
import { Spinner } from "@/components/spinner";

type DlqEvent = {
  id: number;
  task_name: string;
  payload: Record<string, unknown>;
  error: string;
  status: string;
  created_at: string;
  replayed_at?: string | null;
};

export default function DlqPage() {
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replayingId, setReplayingId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const q = useQuery({
    queryKey: ["dlq", status],
    queryFn: () => apiRequest<DlqEvent[]>(`/ops/dlq${status ? `?status=${encodeURIComponent(status)}` : ""}`),
    refetchInterval: 10000
  });

  const replay = async (eventId: number) => {
    setError(null);
    setMessage(null);
    setReplayingId(eventId);
    try {
      const res = await apiRequest<{ task_id: string }>(`/ops/dlq/${eventId}/replay`, {
        method: "POST",
        idempotencyKey: generateIdempotencyKey(`dlq-${eventId}`)
      });
      setMessage(`Replayed DLQ event ${eventId}, task ${res.task_id}`);
      await queryClient.invalidateQueries({ queryKey: ["dlq"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setReplayingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">Issue Recovery</h1>
        <p className="mt-1 text-sm text-blue-100">Review failed actions and retry them safely.</p>
      </div>
      <div className="card">
        <label className="label">Filter by State</label>
        <input className="input mt-1 max-w-sm" placeholder="NEW / REPLAYED" value={status} onChange={(e) => setStatus(e.target.value)} />
      </div>
      {message ? <div className="card"><span className="chip-success">{message}</span></div> : null}
      {error ? <div className="card"><span className="chip-danger">{error}</span></div> : null}
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Action Name</th>
              <th>Status</th>
              <th>Issue</th>
              <th>Created At</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading ? (
              <tr>
                <td className="py-8 text-center" colSpan={6}>
                  <span className="inline-flex items-center gap-2 text-sm text-slate-500">
                    <Spinner size="sm" />
                    Loading recovery items...
                  </span>
                </td>
              </tr>
            ) : null}
            {(q.data ?? []).map((e) => (
              <tr key={e.id}>
                <td>{e.id}</td>
                <td>{e.task_name}</td>
                <td>{e.status === "REPLAYED" ? <span className="chip-success">{e.status}</span> : <span className="chip-warn">{e.status}</span>}</td>
                <td className="max-w-md truncate" title={e.error}>
                  {e.error}
                </td>
                <td>{new Date(e.created_at).toLocaleString()}</td>
                <td>
                  <button className="btn-secondary" disabled={replayingId === e.id} onClick={() => replay(e.id)}>
                    {replayingId === e.id ? (
                      <span className="inline-flex items-center gap-2">
                        <Spinner size="sm" />
                        Replaying...
                      </span>
                    ) : (
                      "Replay"
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
