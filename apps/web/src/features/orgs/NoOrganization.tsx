import React from 'react';
import { Card } from '../../components/ds/Card';
import { LinkButton } from '../../components/ds/Button';
import { SignOutButton } from './SignOutButton';
import { CreateOrgForm } from './CreateOrgForm';

/** Shown to a signed-in user who belongs to no organization. Membership is granted by an organization owner, or they can create their own organization. */
export function NoOrganization() {
  return (
    <main id="main-content" className="gt-container" style={{ paddingBlock: 'var(--space-16)', maxWidth: '40rem' }}>
      <Card>
        <h1 style={{ fontSize: 'var(--text-2xl)', margin: '0 0 var(--space-3)' }}>You are not in an organization yet</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 'var(--leading-relaxed)' }}>
          GroundTruth workspaces belong to organizations. Ask the owner or an admin of your organization to add you as a member, then sign in again. Until then there is nothing for you to open here.
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-5)', flexWrap: 'wrap' }}>
          <LinkButton href="/app" variant="secondary">
            Check again
          </LinkButton>
          <SignOutButton />
          <LinkButton href="/method" variant="ghost">
            How GroundTruth works
          </LinkButton>
        </div>

        <div style={{ marginTop: 'var(--space-8)', borderTop: '1px solid var(--border-subtle)', paddingTop: 'var(--space-6)' }}>
          <h2 style={{ fontSize: 'var(--text-xl)', margin: '0 0 var(--space-2)' }}>Create an organization</h2>
          <p style={{ color: 'var(--text-secondary)', margin: '0 0 var(--space-4)', fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)' }}>
            Or create a new organization workspace to start analyzing projects. You will become its owner.
          </p>
          <CreateOrgForm />
        </div>
      </Card>
    </main>
  );
}
