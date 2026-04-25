"use client";

import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

type StoryContext = {
  video_id: string;
  context_note: string | null;
  pattern_type: string | null;
  confidence: number | null;
  is_recurrence: boolean;
  is_escalation: boolean;
  recurrence_count: number;
  thread_id: string | null;
  available: boolean;
};

const PATTERN_LABELS: Record<string, string> = {
  recurrence: "Recurrence",
  escalation: "Escalating",
  improvement: "Improving",
  related: "Related Story",
  new_story: "New Story Arc",
};

const PATTERN_COLORS: Record<string, string> = {
  recurrence: "bg-amber-100 text-amber-800 border-amber-300",
  escalation: "bg-red-100 text-red-800 border-red-300",
  improvement: "bg-green-100 text-green-800 border-green-300",
  related: "bg-blue-100 text-blue-800 border-blue-300",
  new_story: "bg-gray-100 text-gray-700 border-gray-300",
};

export function ContextPanel({ videoId }: { videoId: string }) {
  const { data, isLoading, isError } = useQuery<StoryContext>({
    queryKey: ["story-context", videoId],
    queryFn: () => apiRequest<StoryContext>(`/patterns/stories/${videoId}/context`),
    retry: false,
    refetchOnWindowFocus: false,
  });

  if (isLoading) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <p className="text-sm text-gray-400 animate-pulse">Analysing story patterns…</p>
      </div>
    );
  }

  if (isError || !data?.available) {
    return (
      <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 p-4">
        <p className="text-xs text-gray-400">Pattern analysis not yet available for this story.</p>
      </div>
    );
  }

  const patternType = data.pattern_type ?? "new_story";
  const badgeClass = PATTERN_COLORS[patternType] ?? PATTERN_COLORS.new_story;
  const badgeLabel = PATTERN_LABELS[patternType] ?? patternType;
  const confidencePct = data.confidence != null ? Math.round(data.confidence * 100) : null;

  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
          Pattern Context
        </span>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${badgeClass}`}
          >
            {badgeLabel}
          </span>
          {confidencePct != null && (
            <span className="text-xs text-gray-500">{confidencePct}% confidence</span>
          )}
        </div>
      </div>

      {/* Context note */}
      {data.context_note && (
        <p className="text-sm text-gray-700 leading-relaxed">{data.context_note}</p>
      )}

      {/* Signal pills */}
      <div className="flex flex-wrap gap-2">
        {data.is_recurrence && (
          <Pill color="amber">
            {data.recurrence_count > 0
              ? `${data.recurrence_count}× recurrence at this location`
              : "Recurrence detected"}
          </Pill>
        )}
        {data.is_escalation && <Pill color="red">Severity escalating</Pill>}
        {data.thread_id && (
          <Pill color="indigo">Part of ongoing thread</Pill>
        )}
      </div>
    </div>
  );
}

function Pill({
  color,
  children,
}: {
  color: "amber" | "red" | "green" | "indigo";
  children: React.ReactNode;
}) {
  const cls = {
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    red: "bg-red-50 text-red-700 border-red-200",
    green: "bg-green-50 text-green-700 border-green-200",
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-200",
  }[color];

  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {children}
    </span>
  );
}
