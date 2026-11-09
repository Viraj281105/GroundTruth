'use client';

import React, { useEffect } from 'react';
import { Button, LinkButton } from '../ds/Button';
import { Skeleton } from '../ds/Card';

/** Shared bodies for the route-level loading.tsx / error.tsx / not-found.tsx files. */

export function RouteLoading({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" aria-label={label} style={{ display: 'grid', gap: 'var(--space-4)', padding: 'var(--space-2) 0' }}>
      <Skeleton width="14rem" height="2rem" />
      <Skeleton width="80%" height="1.25rem" />
      <Skeleton width="60%" height="1.25rem" />
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function RouteError({ error, reset, what = 'this page' }: { error: Error & { digest?: string }; reset: () => void; what?: string }) {
  useEffect(() => {
    // Surfaced to the console for debugging; the page itself shows a friendly message only.
    console.error(error);
  }, [error]);
  return (
    <div role="alert" style={{ display: 'grid', gap: 'var(--space-3)', maxWidth: '36rem', padding: 'var(--space-6) 0' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)', margin: 0 }}>Something went wrong</h1>
      <p style={{ color: 'var(--text-secondary)', margin: 0, lineHeight: 'var(--leading-relaxed)' }}>
        We could not show {what}. Nothing has been changed. You can try again, or go back to your workspace.
      </p>
      {error.digest && <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>Reference: {error.digest}</p>}
      <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <Button onClick={reset}>Try again</Button>
        <LinkButton href="/app" variant="secondary">
          Back to my workspace
        </LinkButton>
      </div>
    </div>
  );
}

export function RouteNotFound({ what = 'page' }: { what?: string }) {
  return (
    <div style={{ display: 'grid', gap: 'var(--space-3)', maxWidth: '36rem', padding: 'var(--space-6) 0' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)', margin: 0 }}>We could not find that {what}</h1>
      <p style={{ color: 'var(--text-secondary)', margin: 0, lineHeight: 'var(--leading-relaxed)' }}>
        It may have been renamed or removed, or you may not have access to it. Check the address, or go back to your workspace.
      </p>
      <div>
        <LinkButton href="/app">Back to my workspace</LinkButton>
      </div>
    </div>
  );
}
