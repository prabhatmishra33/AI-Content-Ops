"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { generateIdempotencyKey } from "@/lib/idempotency";
import { Spinner } from "@/components/spinner";

export default function PoliciesPage() {
  const [version, setVersion] = useState("v-ui-next");
  const [p0, setP0] = useState("0.95");
  const [p1, setP1] = useState("0.90");
  const [p2, setP2] = useState("0.80");
  const [impactConfidenceMin, setImpactConfidenceMin] = useState("0.60");
  const [newsEscalationEnabled, setNewsEscalationEnabled] = useState(true);
  const [holdAuto, setHoldAuto] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const activeQ = useQuery({
    queryKey: ["active-policy"],
    queryFn: () => apiRequest<Record<string, unknown>>("/policies/active")
  });

  useEffect(() => {
    const d = activeQ.data;
    if (!d) return;
    if (typeof d.threshold_p0 === "number") setP0(String(d.threshold_p0));
    if (typeof d.threshold_p1 === "number") setP1(String(d.threshold_p1));
    if (typeof d.threshold_p2 === "number") setP2(String(d.threshold_p2));
    if (typeof d.impact_confidence_min === "number") setImpactConfidenceMin(String(d.impact_confidence_min));
    if (typeof d.news_trending_escalation_enabled === "boolean") setNewsEscalationEnabled(d.news_trending_escalation_enabled);
    if (typeof d.hold_auto_create_gate1 === "boolean") setHoldAuto(d.hold_auto_create_gate1);
  }, [activeQ.data]);

  const activate = async () => {
    setErr(null);
    setMsg(null);
    setSaving(true);
    try {
      await apiRequest("/policies/activate", {
        method: "POST",
        idempotencyKey: generateIdempotencyKey("policy"),
        body: {
          version,
          threshold_p0: Number(p0),
          threshold_p1: Number(p1),
          threshold_p2: Number(p2),
          impact_confidence_min: Number(impactConfidenceMin),
          news_trending_escalation_enabled: newsEscalationEnabled,
          hold_auto_create_gate1: holdAuto
        }
      });
      setMsg("Policy activated");
      await activeQ.refetch();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to activate policy");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">Content Rules</h1>
        <p className="mt-1 text-sm text-blue-100">Set scoring thresholds that control review urgency and routing.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card text-sm">
          <h2 className="mb-2 section-title">Current Rules</h2>
          {activeQ.isLoading ? (
            <div className="flex h-24 items-center justify-center rounded bg-slate-100">
              <Spinner size="sm" />
            </div>
          ) : (
            <pre className="rounded bg-slate-100 p-2">{JSON.stringify(activeQ.data ?? {}, null, 2)}</pre>
          )}
        </div>

        <div className="card space-y-3">
          <h2 className="section-title">Apply New Rules</h2>
          <div>
            <label className="label">Rule Version</label>
            <input className="input mt-1" value={version} onChange={(e) => setVersion(e.target.value)} />
            <button className="btn-secondary mt-2" onClick={() => setVersion(`v-ui-${new Date().toISOString().slice(0, 19)}`)} type="button">
              Use current timestamp
            </button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="label">Highest Urgency (P0)</label>
              <input className="input mt-1" value={p0} onChange={(e) => setP0(e.target.value)} />
            </div>
            <div>
              <label className="label">High Urgency (P1)</label>
              <input className="input mt-1" value={p1} onChange={(e) => setP1(e.target.value)} />
            </div>
            <div>
              <label className="label">Normal Urgency (P2)</label>
              <input className="input mt-1" value={p2} onChange={(e) => setP2(e.target.value)} />
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <p className="font-semibold text-slate-700">Base Threshold Rules</p>
            <p className="mt-1">These are the default score cutoffs used for routing: P0, P1, P2, else HOLD.</p>
          </div>
          <div className="pt-1">
            <h3 className="text-sm font-semibold text-slate-800">Exceptional Rules (Overrides)</h3>
            <p className="mt-1 text-xs text-slate-500">These conditions can override base thresholds for safer review routing.</p>
          </div>
          <div>
            <label className="label">Impact Confidence Minimum</label>
            <input className="input mt-1" value={impactConfidenceMin} onChange={(e) => setImpactConfidenceMin(e.target.value)} />
            <p className="mt-1 text-xs text-slate-500">If AI confidence is below this value, HOLD items are escalated for human review.</p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input checked={newsEscalationEnabled} onChange={(e) => setNewsEscalationEnabled(e.target.checked)} type="checkbox" />
            Escalate one priority level for trending/breaking news context
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input checked={holdAuto} onChange={(e) => setHoldAuto(e.target.checked)} type="checkbox" />
            Automatically send HOLD items to first review stage
          </label>
          {msg ? <span className="chip-success">{msg}</span> : null}
          {err ? <span className="chip-danger">{err}</span> : null}
          <button className="btn-primary" disabled={saving} onClick={activate}>
            {saving ? (
              <span className="inline-flex items-center gap-2">
                <Spinner size="sm" className="border-white/40 border-t-white" />
                Applying...
              </span>
            ) : (
              "Apply Rules"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
