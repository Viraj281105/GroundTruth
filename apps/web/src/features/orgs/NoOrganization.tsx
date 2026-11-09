import React from 'react';
import { Card } from '../../components/ds/Card';
import { LinkButton } from '../../components/ds/Button';
import { SignOutButton } from './SignOutButton';
import { CreateOrgForm } from './CreateOrgForm';

/** Shown to a signed-in user who belongs to no organization: create one now, or ask an owner to add them. */
export function NoOrganization() {
  return (
    <main id="main-content" className="gt-container" style={{ paddingBlock: 'var(--space-16)', maxWidth: '40rem', display: 'grid', gap: 'var(--space-5)' }}>
      <Card>
        <h1 style={{ fontSize: 'var(--text-2xl)', margin: '0 0 var(--space-2)' }}>You are not in an organization yet</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 'var(--leading-relaxed)', margin: 0 }}>
          In GroundTruth, your work lives in an <strong>organization</strong>: a shared space for your team&apos;s projects and evidence. You have two ways forward.
        </p>
        <ol style={{ color: 'var(--text-secondary)', lineHeight: 'var(--leading-relaxed)', paddingLeft: 'var(--space-5)' }}>
          <li>Create your own organization below. You become its owner and can add colleagues later.</li>
          <li>Or ask the owner or an admin of your organization to add you as a member, then choose &ldquo;Check again&rdquo;.</li>
        </ol>
      </Card>
      <Card>
        <section aria-labelledby="create-org-heading">
          <h2 id="create-org-heading" style={{ fontSize: 'var(--text-xl)', margin: '0 0 var(--space-1)' }}>
            Create an organization
          </h2>
          <p style={{ color: 'var(--text-secondary)', margin: '0 0 var(--space-4)', fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)' }}>
            Choose a name and say what kind of organization you are. This decides which overview and tools you see first. You will become its owner.
          </p>
          <CreateOrgForm />
        </section>
      </Card>
      <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <LinkButton href="/app" variant="secondary">
          Check again
        </LinkButton>
        <SignOutButton />
        <LinkButton href="/method" variant="ghost">
          How GroundTruth works
        </LinkButton>
      </div>
    </main>
  );
}
