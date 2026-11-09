'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Button } from '../../components/ds/Button';
import { Card, Skeleton } from '../../components/ds/Card';
import { Reveal } from '../../components/ds/Reveal';
import { useToast } from '../../components/ds/Overlay';
import { useAuth } from '../../lib/auth';
import { login, register } from './auth-api';
import { Field, FormError } from './Field';
import { isValidEmail, passwordChecks, passwordProblem, POST_LOGIN_HOME, safeAppNextPath, strengthScore } from './validate';
import styles from './auth.module.css';

export function Unavailable() {
  return (
    <Card className={styles.gateCard}>
      <h2 className={styles.gateTitle}>Accounts are not available on this server</h2>
      <p className={styles.muted}>This GroundTruth API does not offer sign-in, so everything that is open to the public stays open. Nothing here needs an account.</p>
      <div className={styles.row}>
        <Link href="/" className={styles.link}>
          Back to home
        </Link>
      </div>
    </Card>
  );
}

/** Shared guard: skeleton while loading, redirect away when signed in, clear state when auth is absent. */
function useAuthPage() {
  const auth = useAuth();
  const params = useSearchParams();
  const next = safeAppNextPath(params.get('next'));
  useEffect(() => {
    if (auth.status === 'signed-in') goToNext(next);
  }, [auth.status, next]);
  return { auth, next };
}

function Gate({ children }: { children: (ctx: ReturnType<typeof useAuthPage>) => React.ReactNode }) {
  const ctx = useAuthPage();
  if (ctx.auth.status === 'loading' || ctx.auth.status === 'signed-in') return <Skeleton height="16rem" />;
  if (!ctx.auth.available) return <Unavailable />;
  return <>{children(ctx)}</>;
}

/**
 * A signed-out prefetch of /app leaves a cached redirect to /login in the client router, which a soft
 * navigation would replay. Leave with a full navigation so the new session cookie is used.
 */
export function goToNext(next: string): void {
  window.location.assign(next);
}

export function LoginForm() {
  return (
    <Gate>
      {({ auth, next }) => <LoginBody registrationOpen={auth.registrationOpen} next={next} setUser={auth.setUser} />}
    </Gate>
  );
}

function LoginBody({ registrationOpen, next, setUser }: { registrationOpen: boolean; next: string; setUser: ReturnType<typeof useAuth>['setUser'] }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!isValidEmail(email)) return setError('Enter a valid email address.');
    if (!password) return setError('Enter your password.');
    setBusy(true);
    setError(null);
    const r = await login({ email: email.trim(), password });
    setBusy(false);
    if (!r.ok) {
      setPassword('');
      return setError(r.message);
    }
    setUser(r.data);
    goToNext(next);
  }

  return (
    <div className={styles.page}>
      <Reveal>
        <h1 className={styles.title}>Sign in</h1>
        <p className={styles.muted}>Use your GroundTruth account to run analyses and use the claims workbench.</p>
      </Reveal>
      <Card>
        <form className={styles.form} onSubmit={submit} noValidate>
          <FormError message={error} />
          <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" autoFocus />
          <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
          <Button type="submit" loading={busy}>
            {busy ? 'Signing in' : 'Sign in'}
          </Button>
        </form>
      </Card>
      {registrationOpen && (
        <p className={styles.muted}>
          New here?{' '}
          <Link className={styles.link} href={next === POST_LOGIN_HOME ? '/register' : `/register?next=${encodeURIComponent(next)}`}>
            Create an account
          </Link>
        </p>
      )}
    </div>
  );
}

export function RegisterForm() {
  return <Gate>{({ auth, next }) => (auth.registrationOpen ? <RegisterBody next={next} setUser={auth.setUser} /> : <Closed next={next} />)}</Gate>;
}

function Closed({ next }: { next: string }) {
  return (
    <Card className={styles.gateCard}>
      <h2 className={styles.gateTitle}>New accounts are closed</h2>
      <p className={styles.muted}>This server is not accepting new sign-ups. Ask an administrator to create an account for you.</p>
      <div className={styles.row}>
        <Link className={styles.link} href={next === POST_LOGIN_HOME ? '/login' : `/login?next=${encodeURIComponent(next)}`}>
          Sign in instead
        </Link>
      </div>
    </Card>
  );
}

function RegisterBody({ next, setUser }: { next: string; setUser: ReturnType<typeof useAuth>['setUser'] }) {
  const toast = useToast();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const strength = strengthScore(password, email);
  const checks = passwordChecks(password, email);
  const emailErr = touched && !isValidEmail(email) ? 'Enter a valid email address.' : null;
  const confirmErr = touched && confirm !== password ? 'The passwords do not match.' : null;
  const pwErr = touched ? passwordProblem(password, email) : null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setTouched(true);
    if (!isValidEmail(email) || passwordProblem(password, email) || confirm !== password) return;
    setBusy(true);
    setError(null);
    const r = await register({ email: email.trim(), password });
    setBusy(false);
    if (!r.ok) {
      if (r.code !== 'email_taken') setPassword('');
      setConfirm('');
      return setError(r.message);
    }
    setUser(r.data);
    toast('Account created. Welcome to GroundTruth.', 'success');
    goToNext(next);
  }

  return (
    <div className={styles.page}>
      <Reveal>
        <h1 className={styles.title}>Create your account</h1>
        <p className={styles.muted}>An account lets you run analyses and use the claims workbench.</p>
      </Reveal>
      <Card>
        <form className={styles.form} onSubmit={submit} noValidate>
          <FormError message={error} />
          <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" error={emailErr} autoFocus />
          <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="new-password" error={pwErr} describedBy="pw-rules" />
          <div id="pw-rules" aria-live="polite">
            <div className={styles.meter} role="img" aria-label={`Password strength: ${strength.label}`}>
              {[1, 2, 3, 4].map((n) => (
                <span key={n} className={strength.score >= n ? styles[`on${strength.score}`] : undefined} />
              ))}
            </div>
            <p className={styles.hint}>Strength: {strength.label}</p>
            <ul className={styles.checks}>
              {checks.map((c) => (
                <li key={c.id} className={c.ok ? styles.ok : undefined}>
                  {c.ok ? 'Met: ' : 'Needed: '}
                  {c.label}
                </li>
              ))}
            </ul>
          </div>
          <Field label="Confirm password" type="password" value={confirm} onChange={setConfirm} autoComplete="new-password" error={confirmErr} />
          <Button type="submit" loading={busy}>
            {busy ? 'Creating account' : 'Create account'}
          </Button>
        </form>
      </Card>
      <p className={styles.muted}>
        Already have an account?{' '}
        <Link className={styles.link} href={next === POST_LOGIN_HOME ? '/login' : `/login?next=${encodeURIComponent(next)}`}>
          Sign in
        </Link>
      </p>
    </div>
  );
}
