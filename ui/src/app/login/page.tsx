"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiRequest } from "@/lib/api";
import type { AuthLoginResponse } from "@/lib/types";
import { useSessionStore } from "@/store/session-store";
import { Spinner } from "@/components/spinner";

export default function LoginPage() {
  const router = useRouter();
  const login = useSessionStore((s) => s.login);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<AuthLoginResponse>("/auth/login", {
        method: "POST",
        body: { username, password }
      });
      login(data.access_token, { username: data.username, role: data.role });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto mt-14 grid max-w-4xl gap-5 md:grid-cols-[1.1fr_0.9fr]">
      <div className="hero">
        <h1 className="text-2xl font-semibold tracking-tight">AI Content Operations Platform</h1>
        <p className="mt-2 text-sm text-blue-100">
          Moderate, prioritize, transform, and publish user-generated video with human-in-the-loop governance.
        </p>
        <div className="mt-6 grid grid-cols-2 gap-3 text-xs text-blue-100">
          <div className="rounded-xl border border-blue-300/25 bg-white/10 p-3">Multi-gate moderation workflow</div>
          <div className="rounded-xl border border-blue-300/25 bg-white/10 p-3">Impact score-based routing</div>
          <div className="rounded-xl border border-blue-300/25 bg-white/10 p-3">YouTube + connector distribution</div>
          <div className="rounded-xl border border-blue-300/25 bg-white/10 p-3">Rewards and full auditability</div>
        </div>
      </div>
      <div className="card">
        <h1 className="mb-1 text-xl font-semibold">Sign In</h1>
        <p className="mb-4 text-sm text-slate-500">Use role credentials to access uploader, moderator, or admin workflows.</p>
        <form className="space-y-3.5" onSubmit={onSubmit}>
          <div>
            <label className="label">Username</label>
            <input className="input mt-1" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button className="btn-primary w-full" disabled={loading} type="submit">
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <Spinner size="sm" className="border-white/40 border-t-white" />
                Logging in...
              </span>
            ) : (
              "Login"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
