'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Card, Skeleton } from '../../components/ds/Card';
import { LinkButton } from '../../components/ds/Button';
import { useToast } from '../../components/ds/Overlay';
import { useAuth, type AuthStatus } from '../../lib/auth';
import { hasRole, type Role } from '../../lib/auth-core';
import { SESSION_EXPIRED_EVENT } from '../../lib/session-events';
import styles from './auth.module.css';

export function GateSkeleton() {
  return (
    <div className={styles.gate} role="status" aria-label="Checking your session">
      <Skeleton height="2rem" width="60%" />
      <Skeleton height="6rem" />
    </div>
  );
}

/** Announces an expired session once and re-checks who is signed in. Mount once on a protected page. */
export function SessionExpiryWatcher() {
  const { refresh } = useAuth();
  const toast = useToast();
  useEffect(() => {
    const onExpired = () => {
      toast('Your session expired. Sign in again.', 'error');
      void refresh();
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [refresh, toast]);
  return null;
}

export interface RequireAuthViewProps {
  status: AuthStatus;
  required: boolean;
  /** Where to send the user after signing in, already a same-origin path. */
  nextPath: string;
  /** Short phrase completing "Sign in to ...", e.g. "run analyses". */
  action: string;
  children: React.ReactNode;
}

/** Pure rendering of the gate. Never shows children until the session state is known. */
export function RequireAuthView({ status, required, nextPath, action, children }: RequireAuthViewProps) {
  if (status === 'loading') return <GateSkeleton />;
  if (!required || status === 'signed-in') return <>{children}</>;
  const q = encodeURIComponent(nextPath);
  return (
    <Card className={styles.gateCard}>
      <h2 className={styles.gateTitle}>Sign in to {action}</h2>
      <p className={styles.muted}>Browsing cases and evidence is open to everyone. Running analyses needs an account so the work is accountable.</p>
      <div className={styles.row}>
        <LinkButton href={`/login?next=${q}`}>Sign in</LinkButton>
        <Link href={`/register?next=${q}`} className={styles.link}>
          Create account
        </Link>
      </div>
    </Card>
  );
}

export function RequireAuth({ action, children }: { action: string; children: React.ReactNode }) {
  const { status, required } = useAuth();
  const pathname = usePathname() || '/';
  return (
    <>
      <SessionExpiryWatcher />
      <RequireAuthView status={status} required={required} nextPath={pathname} action={action}>
        {children}
      </RequireAuthView>
    </>
  );
}

export interface RequireRoleViewProps {
  status: AuthStatus;
  role: Role | null;
  minimum: Role;
  nextPath: string;
  children: React.ReactNode;
}

const AUDIENCE: Record<Role, string> = { user: 'signed-in users', dev: 'developers', admin: 'administrators' };

export function RequireRoleView({ status, role, minimum, nextPath, children }: RequireRoleViewProps) {
  if (status === 'loading') return <GateSkeleton />;
  if (hasRole(role, minimum)) return <>{children}</>;
  const q = encodeURIComponent(nextPath);
  const signedOut = status === 'signed-out';
  return (
    <Card className={styles.gateCard}>
      <h2 className={styles.gateTitle}>{signedOut ? 'Sign in to continue' : `This page is for ${AUDIENCE[minimum]}`}</h2>
      <p className={styles.muted}>
        {signedOut
          ? `This page is for ${AUDIENCE[minimum]}. Sign in with an account that has the ${minimum === 'admin' ? 'Admin' : 'Developer'} role.`
          : minimum === 'admin'
            ? 'You do not have permission to view this page (403). Only administrators can manage accounts.'
            : 'The Developer role is granted by an admin. Ask one to upgrade your account if you need this page.'}
      </p>
      <div className={styles.row}>
        {signedOut && <LinkButton href={`/login?next=${q}`}>Sign in</LinkButton>}
        <LinkButton href="/" variant="secondary">
          Back to home
        </LinkButton>
      </div>
    </Card>
  );
}

export function RequireRole({ minimum, children }: { minimum: Role; children: React.ReactNode }) {
  const { status, user } = useAuth();
  const pathname = usePathname() || '/';
  return (
    <RequireRoleView status={status} role={user?.role ?? null} minimum={minimum} nextPath={pathname}>
      {children}
    </RequireRoleView>
  );
}
