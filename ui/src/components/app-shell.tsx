"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/store/session-store";
import { Spinner } from "@/components/spinner";

type NavItem = { href: string; label: string; labelByRole?: Partial<Record<"uploader" | "moderator" | "admin", string>>; roles: Array<"uploader" | "moderator" | "admin"> };

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Home", roles: ["uploader", "moderator", "admin"] },
  { href: "/videos/upload", label: "Submit Video", roles: ["uploader", "admin"] },
  { href: "/videos/history", label: "My Videos", labelByRole: { admin: "Uploaded Videos", moderator: "Uploaded Videos" }, roles: ["uploader", "admin"] },
  { href: "/reviews/queue", label: "Review Inbox", roles: ["moderator", "admin"] },
  { href: "/profile/wallet", label: "Rewards", roles: ["uploader", "admin"] },
  { href: "/ops/policies", label: "Rules", roles: ["admin"] },
  { href: "/ops/distribution", label: "Publishing", roles: ["admin"] },
  { href: "/ops/dlq", label: "Issue Recovery", roles: ["admin"] }
];

const ROUTE_ROLE_RULES: Array<{ prefix: string; roles: Array<"uploader" | "moderator" | "admin"> }> = [
  { prefix: "/videos/upload", roles: ["uploader", "admin"] },
  { prefix: "/videos/history", roles: ["uploader", "admin"] },
  { prefix: "/reviews", roles: ["moderator", "admin"] },
  { prefix: "/ops", roles: ["admin"] },
  { prefix: "/profile/wallet", roles: ["uploader", "admin"] }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const LOADER_DELAY_MS = 180;
  const LOADER_MIN_VISIBLE_MS = 260;
  const pathname = usePathname();
  const router = useRouter();
  const { user, hydrated, hydrate, logout } = useSessionStore();
  const [navLoading, setNavLoading] = useState(false);
  const [navTarget, setNavTarget] = useState<string | null>(null);
  const showLoaderTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideLoaderTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shownAtRef = useRef<number | null>(null);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (hydrated && !user && pathname !== "/login") router.replace("/login");
  }, [hydrated, user, pathname, router]);

  useEffect(() => {
    if (!hydrated || !user || pathname === "/login") return;
    const match = ROUTE_ROLE_RULES.find((r) => pathname.startsWith(r.prefix));
    if (match && !match.roles.includes(user.role)) {
      router.replace("/dashboard");
    }
  }, [hydrated, user, pathname, router]);

  useEffect(() => {
    if (showLoaderTimerRef.current) {
      clearTimeout(showLoaderTimerRef.current);
      showLoaderTimerRef.current = null;
    }

    if (!navLoading) {
      setNavTarget(null);
      return;
    }

    const shownAt = shownAtRef.current ?? Date.now();
    const elapsed = Date.now() - shownAt;
    const waitMs = Math.max(0, LOADER_MIN_VISIBLE_MS - elapsed);

    hideLoaderTimerRef.current = setTimeout(() => {
      setNavLoading(false);
      setNavTarget(null);
      shownAtRef.current = null;
      hideLoaderTimerRef.current = null;
    }, waitMs);
  }, [pathname, navLoading, LOADER_MIN_VISIBLE_MS]);

  useEffect(() => {
    return () => {
      if (showLoaderTimerRef.current) clearTimeout(showLoaderTimerRef.current);
      if (hideLoaderTimerRef.current) clearTimeout(hideLoaderTimerRef.current);
    };
  }, []);

  if (!hydrated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <span className="inline-flex items-center gap-2 text-sm text-slate-600">
          <Spinner size="sm" />
          Loading session...
        </span>
      </div>
    );
  }
  if (!user && pathname !== "/login") return null;
  if (pathname === "/login") return <>{children}</>;
  const activeUser = user!;

  return (
    <div className="min-h-screen">
      {navLoading ? (
        <>
          <div className="fixed inset-0 z-40 bg-slate-900/20 backdrop-blur-[1px]" />
          <div className="pointer-events-none fixed inset-x-0 top-0 z-50 h-1 overflow-hidden bg-slate-200">
            <div className="h-full w-1/3 animate-pulse rounded-r-full bg-gradient-to-r from-cyan-500 via-blue-500 to-emerald-500" />
          </div>
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="card w-full max-w-sm border-slate-200 bg-white/95 text-center shadow-xl">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-cyan-100 to-blue-100">
                <Spinner size="lg" />
              </div>
              <p className="text-base font-semibold text-slate-800">Opening section...</p>
              <p className="mt-1 text-sm text-slate-500">
                {navTarget ? `Loading ${NAV_ITEMS.find((n) => n.href === navTarget)?.label ?? "content"}` : "Loading content"}
              </p>
            </div>
          </div>
        </>
      ) : null}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div>
            <div className="text-base font-semibold tracking-tight">AI Content Operations</div>
            <p className="text-xs text-slate-500">Review, approve, and publish video content</p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="chip">{activeUser.role}</span>
            <span className="font-medium">{activeUser.username}</span>
            <button
              className="btn-secondary"
              onClick={() => {
                logout();
                router.push("/login");
              }}
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-4 px-4 py-5 md:grid-cols-[240px_1fr]">
        <aside className="card h-fit">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Navigation</div>
          <nav className="space-y-1.5">
            {NAV_ITEMS.filter((n) => n.roles.includes(activeUser.role)).map((n) => (
              <Link
                key={n.href}
                className={`block rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  pathname.startsWith(n.href)
                    ? "bg-gradient-to-r from-cyan-100 to-blue-100 text-slate-900 shadow-sm"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
                href={n.href}
                onClick={() => {
                  if (pathname.startsWith(n.href)) return;
                  setNavTarget(n.href);
                  if (showLoaderTimerRef.current) clearTimeout(showLoaderTimerRef.current);
                  if (hideLoaderTimerRef.current) clearTimeout(hideLoaderTimerRef.current);
                  shownAtRef.current = null;
                  showLoaderTimerRef.current = setTimeout(() => {
                    setNavLoading(true);
                    shownAtRef.current = Date.now();
                    showLoaderTimerRef.current = null;
                  }, LOADER_DELAY_MS);
                }}
              >
                {n.labelByRole?.[activeUser.role] ?? n.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main>{children}</main>
      </div>
    </div>
  );
}
