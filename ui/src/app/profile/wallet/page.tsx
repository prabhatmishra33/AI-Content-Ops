"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { Spinner } from "@/components/spinner";

type WalletData = {
  uploader_ref: string;
  balance_points: number;
  transactions?: Array<{ video_id: string; points: number; reason: string; created_at: string }>;
};

export default function WalletPage() {
  const [uploaderRef, setUploaderRef] = useState("demo_user_1");
  const q = useQuery({
    queryKey: ["wallet", uploaderRef],
    queryFn: () => apiRequest<WalletData>(`/wallet/${encodeURIComponent(uploaderRef)}`)
  });

  return (
    <div className="space-y-4">
      <div className="card">
        <h1 className="text-xl font-semibold">Wallet & Rewards</h1>
      </div>
      <div className="card">
        <label className="label">Uploader Ref</label>
        <input className="input mt-1 max-w-sm" value={uploaderRef} onChange={(e) => setUploaderRef(e.target.value)} />
      </div>
      <div className="card">
        <p className="text-sm text-slate-500">Balance</p>
        <p className="text-2xl font-semibold">{q.isLoading ? <Spinner size="sm" /> : (q.data?.balance_points ?? 0)}</p>
      </div>
      <div className="card">
        <h2 className="mb-2 font-semibold">Transactions</h2>
        <div className="space-y-2 text-sm">
          {q.isLoading ? (
            <div className="flex h-20 items-center justify-center rounded bg-slate-100">
              <Spinner size="sm" />
            </div>
          ) : null}
          {(q.data?.transactions ?? []).map((t, idx) => (
            <div className="rounded border border-slate-200 p-2" key={`${t.video_id}-${idx}`}>
              <div className="font-medium">
                {t.points} points ({t.reason})
              </div>
              <div className="text-slate-600">
                video_id: {t.video_id} | {new Date(t.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
