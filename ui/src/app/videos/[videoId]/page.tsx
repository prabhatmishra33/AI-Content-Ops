"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiRequest } from "@/lib/api";
import { VideoPreview } from "@/components/video-preview";
import { Spinner } from "@/components/spinner";
import { LocalizedAudioButton } from "@/components/localized-audio-button";
import { extractSpeakableEntries } from "@/lib/content-audio";

type VideoData = {
  video_id: string;
  uploader_ref: string;
  filename: string;
  content_type: string;
  storage_uri: string;
  thumbnail_uri?: string | null;
  created_at: string;
};

type AuditEvent = {
  event_type: string;
  actor_ref?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

type TimelineStage = {
  id: string;
  label: string;
  description: string;
};

const STAGES: TimelineStage[] = [
  { id: "uploaded", label: "Video Submitted", description: "Video received by platform" },
  { id: "phase_a", label: "Initial AI Review", description: "Safety, tags, impact, and policy checks" },
  { id: "gate_1", label: "Human Review 1", description: "First moderator decision" },
  { id: "phase_b", label: "AI Content Prep", description: "Content/localization generation" },
  { id: "gate_2", label: "Human Review 2", description: "Final moderator approval" },
  { id: "distribution", label: "Publishing", description: "Channel distribution step" },
  { id: "report", label: "Summary Report", description: "System-generated report artifact" },
  { id: "reward", label: "Reward Credited", description: "Points credited to user wallet" }
];

export default function VideoDetailPage() {
  const params = useParams<{ videoId: string }>();
  const searchParams = useSearchParams();
  const videoId = params.videoId;
  const returnTo = searchParams.get("from");

  const videoQ = useQuery({
    queryKey: ["video", videoId],
    queryFn: () => apiRequest<VideoData>(`/videos/${videoId}`),
    enabled: !!videoId
  });

  const statusQ = useQuery({
    queryKey: ["video-status", videoId],
    queryFn: () => apiRequest<{ job_id: string; state: string; priority: string; last_error?: string | null }>(`/videos/${videoId}/status`),
    enabled: !!videoId,
    refetchInterval: 6000
  });

  const aiQ = useQuery({
    queryKey: ["ai", videoId],
    queryFn: async () => {
      try {
        return await apiRequest<Record<string, unknown>>(`/ai-results/video/${videoId}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    enabled: !!videoId,
    retry: false,
    refetchInterval: (q) => (q.state.data ? false : 6000)
  });

  const reportQ = useQuery({
    queryKey: ["report", videoId],
    queryFn: async () => {
      try {
        return await apiRequest<Record<string, unknown>>(`/reports/video/${videoId}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    enabled: !!videoId,
    retry: false,
    refetchInterval: (q) => (q.state.data ? false : 6000)
  });

  const distQ = useQuery({
    queryKey: ["distribution", videoId],
    queryFn: async () => {
      try {
        return await apiRequest<Array<Record<string, unknown>>>(`/distribution/video/${videoId}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    enabled: !!videoId,
    retry: false,
    refetchInterval: (q) => (q.state.data ? false : 6000)
  });

  const jobId = statusQ.data?.job_id;
  const auditQ = useQuery({
    queryKey: ["audit-job", jobId],
    queryFn: () => apiRequest<AuditEvent[]>(`/audit/job/${jobId}`),
    enabled: !!jobId,
    refetchInterval: 6000
  });

  const timeline = useMemo(() => auditQ.data ?? [], [auditQ.data]);
  const eventTypes = useMemo(() => new Set((auditQ.data ?? []).map((e) => e.event_type)), [auditQ.data]);

  const stageState = (stageId: string): "done" | "current" | "pending" | "blocked" => {
    const state = statusQ.data?.state ?? "";
    const isRejected = state.includes("REJECTED");
    const isFailed = state === "FAILED";
    const isHold = state === "HOLD";

    const doneMap: Record<string, boolean> = {
      uploaded: eventTypes.has("JOB_CREATED"),
      phase_a: eventTypes.has("PHASE_A_COMPLETED"),
      gate_1: eventTypes.has("GATE_1_DECISION_APPROVE") || eventTypes.has("GATE_1_DECISION_REJECT"),
      phase_b: eventTypes.has("PHASE_B_COMPLETED"),
      gate_2: eventTypes.has("GATE_2_DECISION_APPROVE") || eventTypes.has("GATE_2_DECISION_REJECT"),
      distribution: eventTypes.has("DISTRIBUTION_COMPLETED") || eventTypes.has("DISTRIBUTION_PARTIAL_OR_FAILED"),
      report: eventTypes.has("REPORT_GENERATED"),
      reward: eventTypes.has("REWARD_CREDITED")
    };

    if (doneMap[stageId]) return "done";

    if (stageId === "phase_a" && isHold) return "current";
    if (stageId === "gate_1" && state === "IN_REVIEW_GATE_1") return "current";
    if (stageId === "phase_b" && state === "AI_PHASE_B_DONE") return "current";
    if (stageId === "gate_2" && state === "IN_REVIEW_GATE_2") return "current";
    if (stageId === "distribution" && state === "DISTRIBUTED") return "current";
    if (stageId === "report" && state === "REPORT_READY") return "current";
    if (stageId === "reward" && state === "COMPLETED") return "done";

    if (
      (isRejected && (stageId === "phase_b" || stageId === "gate_2" || stageId === "distribution" || stageId === "report" || stageId === "reward")) ||
      (isFailed && (stageId === "report" || stageId === "reward"))
    ) {
      return "blocked";
    }

    return "pending";
  };

  const aiData = aiQ.data ?? {};
  const hasAiData = !!aiQ.data && Object.keys(aiData).length > 0;
  const moderation = (aiData.moderation_flags as Record<string, unknown> | undefined) ?? {};
  const moderationFlags = (moderation.flags as Record<string, boolean> | undefined) ?? {};
  const hasSafetyFlags = Object.values(moderationFlags).some(Boolean);
  const moderationConfidence = Number(moderation.confidence ?? 0);

  const tags = (aiData.tags as Record<string, unknown> | undefined) ?? {};
  const primaryCategory = String(tags.primary_category ?? "Not available yet");
  const topicTags = Array.isArray(tags.tags) ? (tags.tags as string[]).slice(0, 5) : [];

  const impactScore = Number(aiData.impact_score ?? 0);
  const impactPct = Math.max(0, Math.min(100, Math.round(impactScore * 100)));
  const impactLabel = impactScore >= 0.7 ? "High Reach Potential" : impactScore >= 0.3 ? "Moderate Reach Potential" : "Low Reach Potential";

  const compliance = (aiData.compliance as Record<string, unknown> | undefined) ?? {};
  const complianceStatusRaw = String(compliance.status ?? "PENDING");
  const complianceViolations = Array.isArray(compliance.violations) ? (compliance.violations as string[]) : [];
  const generatedContent = (aiData.generated_content as Record<string, unknown> | undefined) ?? {};
  const localizedContent = (aiData.localized_content as Record<string, unknown> | undefined) ?? {};
  const hasGeneratedContent = Object.keys(generatedContent).length > 0;
  const hasLocalizedContent = Object.keys(localizedContent).length > 0;
  const generatedKeys = Object.keys(generatedContent).slice(0, 6);
  const localizedKeys = Object.keys(localizedContent).slice(0, 6);
  const generatedSpeakables = extractSpeakableEntries(generatedContent, "Generated");
  const localizedSpeakables = extractSpeakableEntries(localizedContent, "Localized");
  const complianceStatusLabel =
    complianceStatusRaw === "PASS"
      ? "Ready to proceed"
      : complianceStatusRaw === "PASS_WITH_WARNINGS"
        ? "Proceed with caution"
        : complianceStatusRaw === "FAIL"
          ? "Needs correction"
          : "Under review";

  const confidenceLabel =
    moderationConfidence >= 0.8 ? "High confidence" : moderationConfidence >= 0.5 ? "Medium confidence" : "Low confidence";

  const reportReady = !!reportQ.data && Object.keys(reportQ.data).length > 0;
  const publishingItems = Array.isArray(distQ.data) ? distQ.data : [];
  const publishingReady = publishingItems.length > 0;
  const reportSummary = typeof reportQ.data?.summary === "string" ? reportQ.data.summary : "";
  const reportCreatedAt = typeof reportQ.data?.created_at === "string" ? reportQ.data.created_at : "";

  const workflowState = statusQ.data?.state ?? "";
  const nextStepMessage =
    workflowState === "IN_REVIEW_GATE_1"
      ? "Awaiting first moderator decision."
      : workflowState === "IN_REVIEW_GATE_2"
        ? "Awaiting final moderator approval."
        : workflowState === "AI_PHASE_B_DONE"
          ? "AI content preparation is complete. Final review is next."
          : workflowState === "DISTRIBUTED"
            ? "Publishing is complete. Report and rewards are being finalized."
            : workflowState === "COMPLETED"
              ? "Workflow completed successfully."
              : workflowState === "HOLD"
                ? "On hold. A moderator action is required to continue."
                : "Processing is in progress.";

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">Video Progress</h1>
        <p className="mt-1 text-sm text-blue-100">Track review stages, decisions, and final publishing updates.</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="chip border-blue-200/40 bg-white/15 text-blue-50">Video ID: {videoId}</span>
          {returnTo ? (
            <Link className="btn-secondary border-white/40 bg-white/10 text-white hover:bg-white/20" href={returnTo}>
              Back to Review Inbox
            </Link>
          ) : null}
        </div>
      </div>

      <div className="card">
        <h2 className="mb-3 section-title">Workflow Pipeline</h2>
        <div className="space-y-0 md:hidden">
          {STAGES.map((s, idx) => {
            const st = stageState(s.id);
            const label =
              st === "done" ? "Completed" : st === "current" ? "In Progress" : st === "blocked" ? "Blocked" : "Pending";
            const dotClass =
              st === "done"
                ? "bg-emerald-500 ring-emerald-200"
                : st === "current"
                  ? "bg-amber-500 ring-amber-200"
                  : st === "blocked"
                    ? "bg-rose-500 ring-rose-200"
                    : "bg-slate-300 ring-slate-200";
            const lineClass =
              st === "done" ? "bg-emerald-300" : st === "current" ? "bg-amber-200" : st === "blocked" ? "bg-rose-200" : "bg-slate-200";
            const tone =
              st === "done" ? "chip-success" : st === "current" ? "chip-warn" : st === "blocked" ? "chip-danger" : "chip";

            return (
              <div key={s.id} className="grid grid-cols-[28px_1fr] gap-3">
                <div className="flex flex-col items-center">
                  <div className={`mt-1 h-4 w-4 rounded-full ring-4 ${dotClass}`} />
                  {idx < STAGES.length - 1 ? <div className={`mt-1 w-[2px] flex-1 min-h-10 ${lineClass}`} /> : null}
                </div>
                <div className="rounded-xl border border-slate-200 bg-white/70 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold">{s.label}</p>
                    <span className={tone}>{label}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{s.description}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="hidden md:block">
          <div className="flex items-start">
            {STAGES.map((s, idx) => {
              const st = stageState(s.id);
              const label =
                st === "done" ? "Completed" : st === "current" ? "In Progress" : st === "blocked" ? "Blocked" : "Pending";
              const dotClass =
                st === "done"
                  ? "bg-emerald-500 ring-emerald-200"
                  : st === "current"
                    ? "bg-amber-500 ring-amber-200"
                    : st === "blocked"
                      ? "bg-rose-500 ring-rose-200"
                      : "bg-slate-300 ring-slate-200";
              const lineClass =
                st === "done" ? "bg-emerald-300" : st === "current" ? "bg-amber-200" : st === "blocked" ? "bg-rose-200" : "bg-slate-200";
              const tone =
                st === "done" ? "chip-success" : st === "current" ? "chip-warn" : st === "blocked" ? "chip-danger" : "chip";

              return (
                <div key={s.id} className="flex min-w-0 flex-1 items-start">
                  <div className="min-w-0 flex-1 px-1">
                    <div className="flex items-center">
                      <div className={`h-4 w-4 shrink-0 rounded-full ring-4 ${dotClass}`} />
                    </div>
                    <div className="mt-2 min-w-0">
                      <p className="text-sm font-semibold leading-tight">{s.label}</p>
                      <div className="mt-1">
                        <span className={tone}>{label}</span>
                      </div>
                      <p className="mt-1 text-xs leading-tight text-slate-500">{s.description}</p>
                    </div>
                  </div>
                  {idx < STAGES.length - 1 ? <div className={`mx-1 mt-2 h-1 min-w-3 flex-1 rounded-full ${lineClass}`} /> : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card space-y-2 text-sm">
          <h2 className="section-title">Video</h2>
          <p>Filename: {videoQ.data?.filename ?? "-"}</p>
          <p>Uploader: {videoQ.data?.uploader_ref ?? "-"}</p>
          <p>Thumbnail URI: {videoQ.data?.thumbnail_uri ?? "null"}</p>
          {videoId ? <VideoPreview className="pt-2" videoId={videoId} /> : null}
        </div>
        <div className="card space-y-2 text-sm">
          <h2 className="section-title">Current Progress</h2>
          <p>
            State:{" "}
            <span className="chip-success">
              {statusQ.data?.state ?? "-"}
            </span>
          </p>
          <p>Priority: {statusQ.data?.priority ?? "-"}</p>
          <p>Latest Issue: {statusQ.data?.last_error ?? "-"}</p>
          <p>Process ID: {statusQ.data?.job_id ?? "-"}</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="card text-sm">
          <h2 className="mb-2 section-title">Content Insights</h2>
          {aiQ.isLoading || !hasAiData ? (
            <div className="flex h-32 items-center justify-center rounded bg-slate-100">
              <span className="inline-flex items-center gap-2 text-sm text-slate-500">
                <Spinner size="sm" />
                Insights are being generated...
              </span>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Safety Check</p>
                <p className="mt-1 font-medium text-slate-800">
                  {hasSafetyFlags ? "Potential harmful signals detected" : "No harmful signals detected"}
                </p>
                <p className="mt-1 text-xs text-slate-500">{confidenceLabel}</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Topic Understanding</p>
                <p className="mt-1 font-medium text-slate-800">{primaryCategory}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {topicTags.length === 0 ? <span className="text-xs text-slate-500">No topic tags yet</span> : null}
                  {topicTags.map((t) => (
                    <span key={t} className="chip">{t}</span>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Impact Potential</p>
                <p className="mt-1 font-medium text-slate-800">{impactLabel}</p>
                <div className="mt-2 h-2 rounded-full bg-slate-200">
                  <div className="h-2 rounded-full bg-blue-500" style={{ width: `${impactPct}%` }} />
                </div>
                <p className="mt-1 text-xs text-slate-500">Estimated impact score: {impactPct}%</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Policy Readiness</p>
                <p className="mt-1 font-medium text-slate-800">{complianceStatusLabel}</p>
                {complianceViolations.length > 0 ? (
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-slate-600">
                    {complianceViolations.slice(0, 3).map((v, idx) => (
                      <li key={`${idx}-${v}`}>{v}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">No policy issues reported.</p>
                )}
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Generated Content</p>
                {!hasGeneratedContent ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Content draft is not generated yet. It appears after Human Review 1 and AI Content Prep.
                  </p>
                ) : (
                  <>
                    <p className="mt-1 font-medium text-slate-800">Content draft is ready</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {generatedKeys.map((k) => (
                        <span key={k} className="chip">{k}</span>
                      ))}
                    </div>
                    {generatedSpeakables.length > 0 ? (
                      <div className="mt-2 space-y-1.5">
                        {generatedSpeakables.map((entry, idx) => (
                          <div key={`${entry.label}-${idx}`} className="flex items-center justify-between rounded border border-slate-200 px-2 py-1.5">
                            <span className="truncate text-xs text-slate-600">{entry.label}</span>
                            <LocalizedAudioButton iconOnly locale={entry.locale} textParts={entry.textParts} />
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Localized Content</p>
                {!hasLocalizedContent ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Localization output is not generated yet. It appears after AI localization runs.
                  </p>
                ) : (
                  <>
                    <p className="mt-1 font-medium text-slate-800">Localized content is ready</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {localizedKeys.map((k) => (
                        <span key={k} className="chip">{k}</span>
                      ))}
                    </div>
                    {localizedSpeakables.length > 0 ? (
                      <div className="mt-2 space-y-1.5">
                        {localizedSpeakables.map((entry, idx) => (
                          <div key={`${entry.label}-${idx}`} className="flex items-center justify-between rounded border border-slate-200 px-2 py-1.5">
                            <span className="truncate text-xs text-slate-600">{entry.label}</span>
                            <LocalizedAudioButton iconOnly locale={entry.locale} textParts={entry.textParts} />
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              </div>

              <details className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-600">
                  View Technical Details
                </summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded bg-white p-2 text-xs">{JSON.stringify(aiQ.data ?? {}, null, 2)}</pre>
              </details>
            </div>
          )}
        </div>
        <div className="card text-sm">
          <h2 className="mb-2 section-title">Summary Report</h2>
          {reportQ.isLoading ? (
            <div className="flex h-32 items-center justify-center rounded bg-slate-100">
              <Spinner size="sm" />
            </div>
          ) : (
            <div className="space-y-3">
              {!reportReady ? (
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <p className="font-medium text-slate-800">Report is not ready yet</p>
                  <p className="mt-1 text-xs text-slate-500">
                    A summary report will be generated after review and publishing steps are completed.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <p className="font-medium text-slate-800">Report generated</p>
                  {reportSummary ? (
                    <p className="mt-1 text-xs text-slate-700">{reportSummary}</p>
                  ) : (
                    <p className="mt-1 text-xs text-slate-500">Report summary is available in technical details.</p>
                  )}
                  {reportCreatedAt ? (
                    <p className="mt-2 text-[11px] text-slate-500">Generated at: {new Date(reportCreatedAt).toLocaleString()}</p>
                  ) : null}
                </div>
              )}
              <details className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-600">
                  View Technical Details
                </summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded bg-white p-2 text-xs">{JSON.stringify(reportQ.data ?? {}, null, 2)}</pre>
              </details>
            </div>
          )}
        </div>
        <div className="card text-sm">
          <h2 className="mb-2 section-title">Publishing Status</h2>
          {distQ.isLoading ? (
            <div className="flex h-32 items-center justify-center rounded bg-slate-100">
              <Spinner size="sm" />
            </div>
          ) : (
            <div className="space-y-3">
              {!publishingReady ? (
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <p className="font-medium text-slate-800">No channel updates available</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Publishing is not scheduled yet, or channel delivery is still pending.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <p className="font-medium text-slate-800">Channel delivery records</p>
                  <div className="mt-2 space-y-2">
                    {publishingItems.map((item, idx) => {
                      const channel = String(item.channel ?? "unknown");
                      const status = String(item.status ?? "UNKNOWN");
                      const externalId = item.external_id ? String(item.external_id) : null;
                      const createdAt = item.created_at ? String(item.created_at) : null;
                      const errorReason = item.error_reason ? String(item.error_reason) : null;
                      return (
                        <div className="rounded border border-slate-200 p-2" key={`${channel}-${idx}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-medium text-slate-700">{channel}</span>
                            <span className={status === "SUCCESS" || status === "MOCK_SUCCESS" ? "chip-success" : status === "FAILED" ? "chip-danger" : "chip"}>
                              {status}
                            </span>
                          </div>
                          {externalId ? <p className="mt-1 text-xs text-slate-500">External ID: {externalId}</p> : null}
                          {createdAt ? <p className="text-xs text-slate-500">Updated: {new Date(createdAt).toLocaleString()}</p> : null}
                          {errorReason ? <p className="text-xs text-rose-600">Reason: {errorReason}</p> : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              <details className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-600">
                  View Technical Details
                </summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded bg-white p-2 text-xs">{JSON.stringify(distQ.data ?? [], null, 2)}</pre>
              </details>
            </div>
          )}
        </div>
      </div>

      <div className="card text-sm">
        <h2 className="section-title">What Happens Next</h2>
        <p className="mt-2 text-slate-700">{nextStepMessage}</p>
      </div>

      <div className="card">
        <h2 className="mb-3 section-title">Activity Timeline</h2>
        <div className="space-y-2">
          {timeline.length === 0 ? <p className="text-sm text-slate-500">No audit events yet.</p> : null}
          {timeline.map((e, idx) => (
            <div key={`${e.created_at}-${idx}`} className="rounded border border-slate-200 p-3 text-sm">
              <div className="flex justify-between">
                <span className="font-medium">{e.event_type}</span>
                <span className="text-slate-500">{new Date(e.created_at).toLocaleString()}</span>
              </div>
              <div className="mt-1 text-slate-500">Actor: {e.actor_ref ?? "system"}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
