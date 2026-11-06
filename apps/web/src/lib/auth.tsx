'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { API_BASE_URL } from './api';
import { parseRole, type AuthUser, type Role } from './auth-core';

export type AuthStatus = 'loading' | 'signed-out' | 'signed-in';

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  /** False when the API has no auth endpoints or is unreachable: the UI then behaves as signed out. */
  available: boolean;
  /** Whether the server requires sign-in for protected actions. */
  required: boolean;
  /** Whether new accounts can be created. */
  registrationOpen: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
  /** Replace the current user after a successful login/registration response. */
  setUser: (user: AuthUser | null) => void;
}

const AuthContext = createContext<AuthContextValue>({
  status: 'signed-out',
  user: null,
  available: false,
  required: false,
  registrationOpen: false,
  refresh: async () => undefined,
  signOut: async () => undefined,
  setUser: () => undefined,
});

/** Narrow an untrusted JSON user into AuthUser, or null. The server is the source of truth. */
export function toAuthUser(value: unknown): AuthUser | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;
  const role: Role | null = parseRole(v.role);
  if (typeof v.id !== 'string' || typeof v.email !== 'string' || !role) return null;
  return { id: v.id, email: v.email, role, is_active: v.is_active !== false };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUserState] = useState<AuthUser | null>(null);
  const [available, setAvailable] = useState(false);
  const [required, setRequired] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/me`, { credentials: 'include', headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`auth/me ${res.status}`);
      const body: unknown = await res.json();
      const b = (body ?? {}) as Record<string, unknown>;
      const me = toAuthUser(b.user);
      setAvailable(true);
      setRequired(b.auth_required === true);
      setRegistrationOpen(b.registration_open === true);
      setUserState(me);
      setStatus(me ? 'signed-in' : 'signed-out');
    } catch {
      // No auth endpoints or backend down: behave as signed out, never as signed in.
      setAvailable(false);
      setUserState(null);
      setStatus('signed-out');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setUser = useCallback((next: AuthUser | null) => {
    setUserState(next);
    setStatus(next ? 'signed-in' : 'signed-out');
  }, []);

  const signOut = useCallback(async () => {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
    } finally {
      // Even if the request failed, drop the local session view; the cookie expires server-side.
      setUser(null);
    }
  }, [setUser]);

  const value = useMemo(() => ({ status, user, available, required, registrationOpen, refresh, signOut, setUser }), [status, user, available, required, registrationOpen, refresh, signOut, setUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
