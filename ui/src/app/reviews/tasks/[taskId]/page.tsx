"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiBlob, apiRequest } from "@/lib/api";
import { generateIdempotencyKey } from "@/lib/idempotency";
import type { ReviewTask } from "@/lib/types";
import { Spinner } from "@/components/spinner";
import { LocalizedAudioButton } from "@/components/localized-audio-button";
import { extractSpeakableEntries } from "@/lib/content-audio";

type Decision = "APPROVE" | "REJECT";
type MediaStatus = {
  video_id: string;
  job_state: string;
  audio?: Record<string, unknown>;
  mix?: Record<string, unknown>;
};

export default function ReviewTaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const searchParams = useSearchParams();
  const taskId = params.taskId;
  const returnTo = searchParams.get("from") || "/reviews/queue";
  const [reviewerRef, setReviewerRef] = useState("moderator_1");
  const [decision, setDecision] = useState<Decision>("APPROVE");
  const [notes, setNotes] = useState("approved");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retryingMix, setRetryingMix] = useState(false);
  const [mixedPreviewUrl, setMixedPreviewUrl] = useState<string | null>(null);
  const [mixedPreviewError, setMixedPreviewError] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const tasksQ = useQuery({
    queryKey: ["task-detail-list"],
    queryFn: () => apiRequest<ReviewTask[]>("/reviews/tasks"),
    refetchInterval: 5000
  });

  const task = useMemo(() => (tasksQ.data ?? []).find((t) => t.task_id === taskId), [tasksQ.data, taskId]);

  const aiQ = useQuery({
    queryKey: ["task-ai", task?.video_id],
    queryFn: () => apiRequest<Record<string, unknown>>(`/ai-results/video/${task?.video_id}`),
    enabled: !!task?.video_id,
    retry: false
  });
  const mediaQ = useQuery({
    queryKey: ["task-media", task?.video_id],
    queryFn: () => apiRequest<MediaStatus>(`/media/${task?.video_id}/status`),
    enabled: !!task?.video_id,
    retry: false,
    refetchInterval: 5000
  });

  const aiData = aiQ.data ?? {};
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
  const audioState = String(mediaQ.data?.audio?.state ?? "PENDING");
  const mixState = String(mediaQ.data?.mix?.state ?? "PENDING");
  const workflowState = String(mediaQ.data?.job_state ?? "");
  const mediaMixReadyOrLaterStates = new Set([
    "AI_PHASE_B_DONE",
    "MEDIA_MIX_READY",
    "IN_REVIEW_GATE_2",
    "DISTRIBUTED",
    "REPORT_READY",
    "COMPLETED",
    "REJECTED_GATE_2",
    "FAILED",
  ]);
  const mediaMixPanelMode: "not_started" | "waiting" | "active" =
    workflowState === "AI_CONTENT_PREP_DONE"
      ? "waiting"
      : mediaMixReadyOrLaterStates.has(workflowState)
        ? "active"
        : "not_started";
  const audioPath = String((aiQ.data?.audio_news as Record<string, unknown> | undefined)?.path ?? "");
  const audioFilename = audioPath ? audioPath.split(/[\\/]/).pop() ?? "" : "";
  const aiError = aiQ.error as ApiError | null;
  const mediaError = mediaQ.error as ApiError | null;

  useEffect(() => {
    let isMounted = true;
    let objectUrl: string | null = null;
    const videoId = task?.video_id;

    const loadMixedPreview = async () => {
      if (!videoId || mediaMixPanelMode !== "active" || mixState !== "READY") {
        setMixedPreviewUrl(null);
        setMixedPreviewError(null);
        return;
      }
      setMixedPreviewError(null);
      try {
        const blob = await apiBlob(`/media/${videoId}/preview/stream`);
        objectUrl = URL.createObjectURL(blob);
        if (isMounted) setMixedPreviewUrl(objectUrl);
      } catch (err) {
        if (!isMounted) return;
        setMixedPreviewUrl(null);
        if (err instanceof ApiError && err.status === 404) {
          setMixedPreviewError("Preview in progress");
        } else {
          setMixedPreviewError(err instanceof Error ? err.message : "Preview in progress");
        }
      }
    };

    loadMixedPreview();
    return () => {
      isMounted = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [task?.video_id, mediaMixPanelMode, mixState]);

  useEffect(() => {
    let isMounted = true;
    let objectUrl: string | null = null;

    const loadAudio = async () => {
      if (!audioFilename || audioState !== "READY") {
        setAudioUrl(null);
        setAudioLoading(false);
        return;
      }
      setAudioLoading(true);
      try {
        const blob = await apiBlob(`/audio-news/download?filename=${encodeURIComponent(audioFilename)}`);
        objectUrl = URL.createObjectURL(blob);
        if (isMounted) setAudioUrl(objectUrl);
      } catch {
        if (isMounted) setAudioUrl(null);
      } finally {
        if (isMounted) setAudioLoading(false);
      }
    };

    loadAudio();
    return () => {
      isMounted = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [audioFilename, audioState]);

  const submitDecision = async () => {
    if (!task) return;
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      const data = await apiRequest<{
        task_id: string;
        gate: string;
        decision: string;
        next_actions: string[];
      }>(`/reviews/tasks/${task.task_id}/decision?auto_progress=true&async_mode=true`, {
        method: "POST",
        body: { reviewer_ref: reviewerRef, decision, notes },
        idempotencyKey: generateIdempotencyKey(`decision-${task.task_id}`)
      });
      setSuccess(`Decision submitted for ${data.gate}: ${data.decision}`);
      await tasksQ.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  const retryMediaMix = async () => {
    if (!task?.video_id) return;
    setRetryingMix(true);
    setError(null);
    setSuccess(null);
    try {
      await apiRequest(`/media/${task.video_id}/mix`, { method: "POST" });
      setSuccess("Media mix retry triggered.");
      await mediaQ.refetch();
      await aiQ.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry media mix");
    } finally {
      setRetryingMix(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">Review Decision</h1>
        <p className="mt-1 text-sm text-blue-100">Review content context and submit an approval decision.</p>
        <div className="mt-3 flex items-center gap-2">
          <span className="chip border-blue-200/40 bg-white/15 text-blue-50">Task ID: {taskId}</span>
          <Link className="btn-secondary border-white/40 bg-white/10 text-white hover:bg-white/20" href={returnTo}>
            Back to Queue
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card min-w-0 space-y-2 text-sm">
          <h2 className="section-title">Task Context</h2>
          <p>Review Item: {task?.task_id ?? "-"}</p>
          <p>Video: {task?.video_id ?? "-"}</p>
          <p>Process: {task?.job_id ?? "-"}</p>
          <p>Stage: {task?.gate ?? "-"}</p>
          <p>Status: {task?.status ?? "-"}</p>
          {task?.video_id ? (
            <Link className="text-brand-700 underline" href={`/videos/${task.video_id}?from=${encodeURIComponent(returnTo)}`}>
              Open video timeline
            </Link>
          ) : null}
        </div>
        <div className="card min-w-0 space-y-3">
          <h2 className="section-title">Submit Decision</h2>
          <div>
            <label className="label">Reviewer ID</label>
            <input className="input mt-1" value={reviewerRef} onChange={(e) => setReviewerRef(e.target.value)} />
          </div>
          <div>
            <label className="label">Decision</label>
            <select className="input mt-1" value={decision} onChange={(e) => setDecision(e.target.value as Decision)}>
              <option value="APPROVE">APPROVE</option>
              <option value="REJECT">REJECT</option>
            </select>
          </div>
          <div>
            <label className="label">Notes</label>
            <textarea className="input mt-1 min-h-20" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          {error ? <span className="chip-danger">{error}</span> : null}
          {success ? <span className="chip-success">{success}</span> : null}
          <button className="btn-primary" disabled={submitting} onClick={submitDecision}>
            {submitting ? (
              <span className="inline-flex items-center gap-2">
                <Spinner size="sm" className="border-white/40 border-t-white" />
                Submitting...
              </span>
            ) : (
              "Submit"
            )}
          </button>
        </div>
      </div>

      <div className="card min-w-0 space-y-3 text-sm">
        <h2 className="section-title">Media Readiness</h2>
        {mediaMixPanelMode === "not_started" ? (
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Narration Audio</p>
                <p className="mt-1 font-medium text-slate-800">Not started</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Mixed Preview</p>
                <p className="mt-1 font-medium text-slate-800">Not started</p>
              </div>
            </div>
            <div className="flex h-24 w-full items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-100 text-sm text-slate-500">
              Preview not started
            </div>
          </div>
        ) : mediaMixPanelMode === "waiting" ? (
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Narration Audio</p>
                <p className="mt-1 font-medium text-slate-800">Waiting to start</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Mixed Preview</p>
                <p className="mt-1 font-medium text-slate-800">Waiting to start</p>
              </div>
            </div>
            <div className="flex h-24 w-full items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-100 text-sm text-slate-500">
              Waiting to start
            </div>
          </div>
        ) : mediaQ.isLoading ? (
          <div className="flex h-24 items-center justify-center rounded bg-slate-100">
            <span className="inline-flex items-center gap-2 text-sm text-slate-500">
              <Spinner size="sm" />
              Loading media status...
            </span>
          </div>
        ) : mediaQ.isError ? (
          <div className="rounded-xl border border-slate-200 bg-white p-3">
            <p className="font-medium text-slate-800">
              {mediaError?.status === 404 ? "Preview in progress" : mediaError?.status === 403 ? "Access restricted" : "Media status unavailable"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {mediaError?.status === 404
                ? "Media mix is still being prepared."
                : mediaError?.status === 403
                  ? "You don't have permission to access media status."
                  : "Please retry after a moment."}
            </p>
          </div>
        ) : (
          <>
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Narration Audio</p>
                <p className="mt-1 font-medium text-slate-800">{audioState === "READY" ? "Ready" : "In progress"}</p>
                <div className="mt-2 flex items-center gap-2">
                  <button
                    className="btn-secondary"
                    disabled={!audioUrl || audioLoading}
                    onClick={async () => {
                      if (!audioRef.current) return;
                      await audioRef.current.play();
                      setAudioPlaying(true);
                    }}
                  >
                    {audioLoading ? <span className="inline-flex items-center gap-2"><Spinner size="sm" /> Loading...</span> : "▶ Play"}
                  </button>
                  <button
                    className="btn-secondary"
                    disabled={!audioUrl}
                    onClick={() => {
                      if (!audioRef.current) return;
                      audioRef.current.pause();
                      audioRef.current.currentTime = 0;
                      setAudioPlaying(false);
                    }}
                  >
                    ■ Stop
                  </button>
                  {audioPlaying ? <span className="chip">Playing</span> : null}
                </div>
                <audio
                  ref={audioRef}
                  onEnded={() => setAudioPlaying(false)}
                  onPause={() => setAudioPlaying(false)}
                  onPlay={() => setAudioPlaying(true)}
                  src={audioUrl ?? undefined}
                />
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Mixed Preview</p>
                <p className="mt-1 font-medium text-slate-800">{mixState === "READY" ? "Ready" : "Preview in progress"}</p>
              </div>
            </div>

            {mixedPreviewUrl ? (
              <video className="h-64 w-full rounded-xl border border-slate-200 bg-black shadow-sm" controls preload="metadata" src={mixedPreviewUrl} />
            ) : (
              <div className="flex h-24 w-full items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-100 text-sm text-slate-500">
                Preview in progress
              </div>
            )}
            {mixedPreviewError ? <p className="text-xs text-slate-500">{mixedPreviewError}</p> : null}

            <div>
              <button className="btn-secondary" disabled={retryingMix || !task?.video_id} onClick={retryMediaMix}>
                {retryingMix ? (
                  <span className="inline-flex items-center gap-2">
                    <Spinner size="sm" />
                    Retrying...
                  </span>
                ) : (
                  "Retry Mixed Preview"
                )}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="card min-w-0 text-sm">
        <h2 className="mb-2 section-title">Content Insights</h2>
        {aiQ.isLoading ? (
          <div className="flex h-32 items-center justify-center rounded bg-slate-100">
            <span className="inline-flex items-center gap-2 text-sm text-slate-500">
              <Spinner size="sm" />
              Loading context...
            </span>
          </div>
        ) : aiQ.isError ? (
          <div className="rounded-xl border border-slate-200 bg-white p-3">
            <p className="font-medium text-slate-800">
              {aiError?.status === 404 ? "Insights are being prepared" : aiError?.status === 403 ? "Access restricted" : "Insights unavailable"}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {aiError?.status === 404
                ? "AI analysis is still in progress for this video."
                : aiError?.status === 403
                  ? "You do not have permission to view this section."
                  : "Please retry after a moment."}
            </p>
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
                  Content draft is not generated yet. It appears after Gate 1 approval and AI content preparation.
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
                  Localization output is not generated yet. It appears after localization runs in Phase B.
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
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 text-xs">
                {JSON.stringify(aiQ.data ?? {}, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </div>
    </div>
  );
}
