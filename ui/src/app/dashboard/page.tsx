"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { useSessionStore } from "@/store/session-store";
import type { ReviewTask } from "@/lib/types";
import { Spinner } from "@/components/spinner";

type AdminSummaryMetrics = {
  videos_uploaded: number;
  videos_reviewed_gate_2: number;
  videos_ready_to_publish: number;
  videos_below_impact_threshold: number;
  rewarded_users: number;
  total_rewards_points: number;
  impact_threshold_p2: number;
};

export default function DashboardPage() {
  const user = useSessionStore((s) => s.user);

  const reviewTasksQ = useQuery({
    queryKey: ["review-tasks-dashboard"],
    queryFn: () => apiRequest<ReviewTask[]>("/reviews/tasks?status=PENDING"),
    enabled: user?.role === "moderator" || user?.role === "admin",
    refetchInterval: 10000
  });

  const walletQ = useQuery({
    queryKey: ["wallet-dashboard", user?.username],
    queryFn: () => apiRequest<{ balance_points: number; uploader_ref: string }>(`/wallet/${user?.username}`),
    enabled: user?.role === "uploader"
  });

  const adminMetricsQ = useQuery({
    queryKey: ["admin-summary-metrics"],
    queryFn: () => apiRequest<AdminSummaryMetrics>("/ops/metrics/admin-summary"),
    enabled: user?.role === "admin",
    refetchInterval: 15000
  });

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">
          {user?.role === "uploader" ? `Hey, ${user.username}` : "Welcome"}
        </h1>
        <p className="mt-1 text-sm text-blue-100">
          {user?.role === "uploader"
            ? "Submit videos, track their progress, and check your earned rewards."
            : "Track content progress, review work items, and reward updates in one place."}
        </p>
        <div className="mt-4">
          <span className="chip border-blue-200/40 bg-white/15 text-blue-50">Role: {user?.role}</span>
        </div>
      </div>

      {user?.role === "admin" ? (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Videos Uploaded</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {adminMetricsQ.isLoading ? <Spinner size="md" /> : (adminMetricsQ.data?.videos_uploaded ?? 0)}
            </p>
          </div>
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Videos Reviewed at Gate 2</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {adminMetricsQ.isLoading ? <Spinner size="md" /> : (adminMetricsQ.data?.videos_reviewed_gate_2 ?? 0)}
            </p>
          </div>
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Ready To Be Published</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {adminMetricsQ.isLoading ? <Spinner size="md" /> : (adminMetricsQ.data?.videos_ready_to_publish ?? 0)}
            </p>
          </div>
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Not Reaching Impact Threshold</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {adminMetricsQ.isLoading ? <Spinner size="md" /> : (adminMetricsQ.data?.videos_below_impact_threshold ?? 0)}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              Current minimum threshold: {adminMetricsQ.data?.impact_threshold_p2 ?? "-"}
            </p>
          </div>
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Users Getting Rewards</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {adminMetricsQ.isLoading ? <Spinner size="md" /> : (adminMetricsQ.data?.rewarded_users ?? 0)}
            </p>
          </div>
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Total Rewards Offered</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {adminMetricsQ.isLoading ? <Spinner size="md" /> : (adminMetricsQ.data?.total_rewards_points ?? 0)}
            </p>
            <p className="mt-2 text-xs text-slate-500">Points across all contributors</p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        {user?.role === "admin" || user?.role === "moderator" ? (
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Pending Review Items</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {reviewTasksQ.isLoading ? <Spinner size="md" /> : (reviewTasksQ.data?.length ?? 0)}
            </p>
            <Link className="mt-3 inline-block text-sm font-medium text-brand-700 underline" href="/reviews/queue">
              Open inbox
            </Link>
          </div>
        ) : null}
        {user?.role === "uploader" ? (
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Reward Points</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight">
              {walletQ.isLoading ? <Spinner size="md" /> : (walletQ.data?.balance_points ?? 0)}
            </p>
            <Link className="mt-3 inline-block text-sm font-medium text-brand-700 underline" href="/profile/wallet">
              View rewards
            </Link>
          </div>
        ) : (
          <div className="card">
            <p className="text-sm font-semibold text-slate-500">Review Queue Health</p>
            <p className="mt-2 text-sm text-slate-600">
              Monitor pending tasks and keep approvals moving across both review gates.
            </p>
            <Link className="mt-3 inline-block text-sm font-medium text-brand-700 underline" href="/reviews/queue">
              Open inbox
            </Link>
          </div>
        )}
        <div className="card">
          <p className="text-sm font-semibold text-slate-500">Quick Actions</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {user?.role === "admin" || user?.role === "uploader" ? (
              <Link className="btn-secondary" href="/videos/upload">
                Submit Video
              </Link>
            ) : null}
            {user?.role === "admin" || user?.role === "moderator" ? (
              <Link className="btn-secondary" href="/reviews/queue">
                Open Reviews
              </Link>
            ) : null}
            {user?.role === "admin" ? (
              <Link className="btn-secondary" href="/ops/dlq">
                Recover Issues
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
