"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { Spinner } from "@/components/spinner";
import { useSessionStore } from "@/store/session-store";

type WalletData = {
  uploader_ref: string;
  balance_points: number;
  transactions?: Array<{ video_id: string; points: number; reason: string; created_at: string }>;
};

type AdminRewardsOverview = {
  total_rewarded_users: number;
  total_points_issued: number;
  users: WalletData[];
};

export default function WalletPage() {
  const user = useSessionStore((s) => s.user);
  const [uploaderRef, setUploaderRef] = useState(user?.username ?? "");
  const [userFilter, setUserFilter] = useState("");

  const q = useQuery({
    queryKey: ["wallet", uploaderRef],
    queryFn: () => apiRequest<WalletData>(`/wallet/${encodeURIComponent(uploaderRef)}`),
    enabled: !!uploaderRef && user?.role !== "admin"
  });

  const adminQ = useQuery({
    queryKey: ["wallet-admin-overview"],
    queryFn: () => apiRequest<AdminRewardsOverview>("/wallet/admin/overview"),
    enabled: user?.role === "admin"
  });

  const filteredUsers = (adminQ.data?.users ?? []).filter((u) =>
    u.uploader_ref.toLowerCase().includes(userFilter.trim().toLowerCase())
  );

  return (
    <div className="space-y-4">
      <div className="card">
        <h1 className="text-xl font-semibold">Wallet & Rewards</h1>
      </div>

      {user?.role === "admin" ? (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="card">
              <p className="text-sm text-slate-500">Total Rewarded Users</p>
              <p className="text-2xl font-semibold">
                {adminQ.isLoading ? <Spinner size="sm" /> : (adminQ.data?.total_rewarded_users ?? 0)}
              </p>
            </div>
            <div className="card">
              <p className="text-sm text-slate-500">Total Points Issued</p>
              <p className="text-2xl font-semibold">
                {adminQ.isLoading ? <Spinner size="sm" /> : (adminQ.data?.total_points_issued ?? 0)}
              </p>
            </div>
          </div>

          <div className="card">
            <label className="label">Filter Users</label>
            <input
              className="input mt-1 max-w-sm"
              placeholder="Search by user id"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
            />
          </div>

          <div className="card">
            <h2 className="mb-2 font-semibold">Rewarded Users</h2>
            <div className="space-y-3 text-sm">
              {adminQ.isLoading ? (
                <div className="flex h-20 items-center justify-center rounded bg-slate-100">
                  <Spinner size="sm" />
                </div>
              ) : null}
              {!adminQ.isLoading && filteredUsers.length === 0 ? (
                <p className="text-slate-500">No users match the filter.</p>
              ) : null}
              {filteredUsers.map((u) => (
                <details className="rounded border border-slate-200 p-3" key={u.uploader_ref}>
                  <summary className="cursor-pointer font-medium">
                    {u.uploader_ref} · {u.balance_points} points · {u.transactions?.length ?? 0} rewards
                  </summary>
                  <div className="mt-3 space-y-2">
                    {(u.transactions ?? []).map((t, idx) => (
                      <div className="rounded border border-slate-100 bg-slate-50 p-2" key={`${u.uploader_ref}-${t.video_id}-${idx}`}>
                        <div className="font-medium">
                          {t.points} points ({t.reason})
                        </div>
                        <div className="text-slate-600">
                          video_id: {t.video_id} | {new Date(t.created_at).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="card">
            <label className="label">Your User ID</label>
            <input className="input mt-1 max-w-sm bg-slate-50 text-slate-600" value={uploaderRef} readOnly />
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
        </>
      )}
    </div>
  );
}
