import React from 'react';
import { EmptyState, LinkButton } from '../../../components/ds';
import { layoutCopy as c } from './copy';

export function CaseNotFound() {
  return (
    <div className="gt-container" style={{ paddingBlock: 'var(--space-12)' }}>
      <EmptyState
        title={c.notFoundTitle}
        body={c.notFoundBody}
        action={
          <LinkButton href="/cases" variant="secondary">
            {c.notFoundAction}
          </LinkButton>
        }
      />
    </div>
  );
}

export function CaseUnreachable({ apiBaseUrl }: { apiBaseUrl: string }) {
  return (
    <div className="gt-container" style={{ paddingBlock: 'var(--space-12)' }}>
      <div role="alert">
        <EmptyState
          title={c.unreachableTitle}
          body={
            <>
              {c.unreachableBody} {c.unreachableHint} <code>{apiBaseUrl}</code>
            </>
          }
          action={
            <LinkButton href="/cases" variant="secondary">
              {c.unreachableAction}
            </LinkButton>
          }
        />
      </div>
    </div>
  );
}
