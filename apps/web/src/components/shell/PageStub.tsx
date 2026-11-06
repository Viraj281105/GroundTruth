import React from 'react';
import { EmptyState } from '../ds/Card';

/** Placeholder body for a route that its owning task has not filled yet. */
export function PageStub({ title, summary }: { title: string; summary: string }) {
  return (
    <div className="gt-container" style={{ paddingBlock: 'var(--space-16)' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)' }}>{title}</h1>
      <EmptyState title="Being built" body={summary} />
    </div>
  );
}
