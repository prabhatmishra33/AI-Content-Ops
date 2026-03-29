"use client";

import { create } from "zustand";
import { clearSession, getUser, setSession, type SessionUser } from "@/lib/auth";

type SessionState = {
  token: string | null;
  user: SessionUser | null;
  hydrated: boolean;
  hydrate: () => void;
  login: (token: string, user: SessionUser) => void;
  logout: () => void;
};

export const useSessionStore = create<SessionState>((set) => ({
  token: null,
  user: null,
  hydrated: false,
  hydrate: () => {
    const user = getUser();
    const token = typeof window !== "undefined" ? localStorage.getItem("ai_content_ops_token") : null;
    set({ user, token, hydrated: true });
  },
  login: (token, user) => {
    setSession(token, user);
    set({ token, user });
  },
  logout: () => {
    clearSession();
    set({ token: null, user: null });
  }
}));
