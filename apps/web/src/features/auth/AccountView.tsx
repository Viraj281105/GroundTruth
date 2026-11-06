'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button, LinkButton } from '../../components/ds/Button';
import { Card, Skeleton } from '../../components/ds/Card';
import { Chip } from '../../components/ds/Chip';
import { Reveal } from '../../components/ds/Reveal';
import { useToast } from '../../components/ds/Overlay';
import { useAuth } from '../../lib/auth';
import { ROLE_LABELS, type Role } from '../../lib/auth-core';
import { changePassword, type UserView } from './auth-api';
import { createApiClient } from '../../lib/api-client';
import { Field, FormError } from './Field';
import { Unavailable } from './AuthForms';
import { passwordProblem } from './validate';
import styles from './auth.module.css';

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  user: 'Browse every case, run new analyses, cancel jobs and use the claims workbench.',
  dev: 'Everything a User can do, plus developer areas such as System status and job internals. Granted by an admin.',
  admin: 'Everything a Developer can do, plus managing accounts: changing roles and deactivating users.',
};

function fmt(iso: string | null | undefined): string {
  if (!iso) return 'Not recorded';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? 'Not recorded' : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function AccountView() {
  const { status, user, available, signOut } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<UserView | null>(null);

  useEffect(() => {
    if (status === 'signed-out' && available) router.replace('/login?next=%2Faccount');
  }, [status, available, router]);

  useEffect(() => {
    if (status !== 'signed-in') return;
    let live = true;
    // /auth/me carries the dates; AuthProvider keeps only the narrow user, so read the full view here.
    createApiClient()
      .GET('/auth/me')
      .then(({ data }) => {
        const u = (data as { user?: UserView | null } | undefined)?.user;
        if (live && u) setProfile(u);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [status]);

  if (status === 'loading') return <div className={styles.page}><Skeleton height="12rem" /></div>;
  if (!available) return <div className={styles.page}><Unavailable /></div>;
  if (!user) return <div className={styles.page}><Skeleton height="12rem" /></div>;

  return (
    <div className={styles.page}>
      <Reveal>
        <h1 className={styles.title}>Your account</h1>
      </Reveal>
      <Card>
        <h2 className={styles.gateTitle}>Profile</h2>
        <dl className={styles.dl}>
          <dt>Email</dt>
          <dd>{user.email}</dd>
          <dt>Role</dt>
          <dd>
            <Chip tone={user.role === 'user' ? 'neutral' : 'accent'}>{ROLE_LABELS[user.role]}</Chip>
          </dd>
          <dt>Member since</dt>
          <dd>{fmt(profile?.created_at)}</dd>
          <dt>Last sign in</dt>
          <dd>{fmt(profile?.last_login_at)}</dd>
        </dl>
      </Card>
      <ChangePasswordCard email={user.email} />
      <Card>
        <h2 className={styles.gateTitle}>What each role can do</h2>
        <ul className={styles.roles}>
          {(['user', 'dev', 'admin'] as Role[]).map((r) => (
            <li key={r}>
              <span>
                <Chip tone={r === user.role ? 'accent' : 'neutral'}>{ROLE_LABELS[r]}</Chip>
                {r === user.role ? ' (your role)' : ''}
              </span>
              {ROLE_DESCRIPTIONS[r]}
            </li>
          ))}
        </ul>
      </Card>
      <div className={styles.row}>
        <Button
          variant="secondary"
          onClick={async () => {
            await signOut();
            router.replace('/');
          }}
        >
          Sign out
        </Button>
        {user.role === 'admin' && <LinkButton href="/admin/users" variant="ghost">Manage users</LinkButton>}
        <Link className={styles.link} href="/">
          Back to home
        </Link>
      </div>
    </div>
  );
}

function ChangePasswordCard({ email }: { email: string }) {
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const nextErr = touched ? passwordProblem(next, email) : null;
  const confirmErr = touched && confirm !== next ? 'The passwords do not match.' : null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setTouched(true);
    if (!current || passwordProblem(next, email) || confirm !== next) return;
    setBusy(true);
    setError(null);
    const r = await changePassword(current, next);
    setBusy(false);
    if (!r.ok) return setError(r.message);
    setCurrent('');
    setNext('');
    setConfirm('');
    setTouched(false);
    toast('Password changed. Other devices were signed out.', 'success');
  }

  return (
    <Card>
      <h2 className={styles.gateTitle}>Change password</h2>
      <form className={styles.form} onSubmit={submit} noValidate>
        <FormError message={error} />
        <Field label="Current password" type="password" value={current} onChange={setCurrent} autoComplete="current-password" />
        <Field label="New password" type="password" value={next} onChange={setNext} autoComplete="new-password" error={nextErr} hint="10 to 128 characters; not your email or a common password." />
        <Field label="Confirm new password" type="password" value={confirm} onChange={setConfirm} autoComplete="new-password" error={confirmErr} />
        <p className={styles.hint}>Changing your password signs you out everywhere else. This device stays signed in.</p>
        <div className={styles.row}>
          <Button type="submit" loading={busy}>
            Change password
          </Button>
        </div>
      </form>
    </Card>
  );
}
