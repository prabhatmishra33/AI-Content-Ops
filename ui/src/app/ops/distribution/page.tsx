"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { generateIdempotencyKey } from "@/lib/idempotency";
import { Spinner } from "@/components/spinner";

export default function DistributionOpsPage() {
  const [accountRef, setAccountRef] = useState("default");
  const [videoId, setVideoId] = useState("");
  const [externalId, setExternalId] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [polling, setPolling] = useState(false);

  const quotaQ = useQuery({
    queryKey: ["yt-quota"],
    queryFn: () => apiRequest<Record<string, unknown>>("/distribution/youtube/quota")
  });

  const integrationQ = useQuery({
    queryKey: ["yt-integration", accountRef],
    queryFn: () => apiRequest<Record<string, unknown>>(`/distribution/youtube/integration/status?account_ref=${encodeURIComponent(accountRef)}`)
  });

  const getOauthUrl = async () => {
    setError(null);
    setConnecting(true);
    try {
      const res = await apiRequest<{ auth_url: string }>(
        `/distribution/youtube/oauth/url?account_ref=${encodeURIComponent(accountRef)}`
      );
      window.open(res.auth_url, "_blank");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connection failed");
    } finally {
      setConnecting(false);
    }
  };

  const publish = async () => {
    setError(null);
    setResult(null);
    setPublishing(true);
    try {
      const res = await apiRequest<Record<string, unknown>>(
        `/distribution/youtube/publish/${encodeURIComponent(videoId)}?account_ref=${encodeURIComponent(accountRef)}`,
        { method: "POST", idempotencyKey: generateIdempotencyKey(`yt-publish-${videoId}`) }
      );
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  };

  const pollStatus = async () => {
    setError(null);
    setResult(null);
    setPolling(true);
    try {
      const res = await apiRequest<Record<string, unknown>>(
        `/distribution/youtube/status/${encodeURIComponent(externalId)}?account_ref=${encodeURIComponent(accountRef)}`
      );
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Poll failed");
    } finally {
      setPolling(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">Publishing Center</h1>
        <p className="mt-1 text-sm text-blue-100">Manage channel connection, publish updates, and check publishing progress.</p>
      </div>
      <div className="card grid gap-3 md:grid-cols-3">
        <div>
          <label className="label">YouTube Account Ref</label>
          <input className="input mt-1" value={accountRef} onChange={(e) => setAccountRef(e.target.value)} />
        </div>
        <div>
          <button className="btn-primary mt-6" disabled={connecting} onClick={getOauthUrl}>
            {connecting ? (
              <span className="inline-flex items-center gap-2">
                <Spinner size="sm" className="border-white/40 border-t-white" />
                Connecting...
              </span>
            ) : (
              "Connect Channel"
            )}
          </button>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card text-sm">
          <h2 className="mb-2 section-title">Connection Status</h2>
          {integrationQ.isLoading ? (
            <div className="flex h-24 items-center justify-center rounded bg-slate-100">
              <Spinner size="sm" />
            </div>
          ) : (
            <pre className="rounded bg-slate-100 p-2">{JSON.stringify(integrationQ.data ?? {}, null, 2)}</pre>
          )}
        </div>
        <div className="card text-sm">
          <h2 className="mb-2 section-title">Usage Limits</h2>
          {quotaQ.isLoading ? (
            <div className="flex h-24 items-center justify-center rounded bg-slate-100">
              <Spinner size="sm" />
            </div>
          ) : (
            <pre className="rounded bg-slate-100 p-2">{JSON.stringify(quotaQ.data ?? {}, null, 2)}</pre>
          )}
        </div>
      </div>
      <div className="card space-y-3">
        <h2 className="section-title">Manual Publish</h2>
        <div>
          <label className="label">Video ID</label>
          <input className="input mt-1" value={videoId} onChange={(e) => setVideoId(e.target.value)} />
        </div>
        <button className="btn-primary" disabled={publishing} onClick={publish}>
          {publishing ? (
            <span className="inline-flex items-center gap-2">
              <Spinner size="sm" className="border-white/40 border-t-white" />
              Publishing...
            </span>
          ) : (
            "Publish to YouTube"
          )}
        </button>
      </div>
      <div className="card space-y-3">
        <h2 className="section-title">Check Published Video Status</h2>
        <div>
          <label className="label">Published Video ID</label>
          <input className="input mt-1" value={externalId} onChange={(e) => setExternalId(e.target.value)} />
        </div>
        <button className="btn-secondary" disabled={polling} onClick={pollStatus}>
          {polling ? (
            <span className="inline-flex items-center gap-2">
              <Spinner size="sm" />
              Checking...
            </span>
          ) : (
            "Check Status"
          )}
        </button>
      </div>
      {error ? <div className="card"><span className="chip-danger">{error}</span></div> : null}
      {result ? (
        <div className="card text-sm">
          <h2 className="mb-2 section-title">Result</h2>
          <pre className="rounded bg-slate-100 p-2">{JSON.stringify(result, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}
