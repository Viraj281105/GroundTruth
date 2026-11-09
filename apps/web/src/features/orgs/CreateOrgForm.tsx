'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds/Button';
import { createApiClient } from '../../lib/api-client';

export function CreateOrgForm() {
  const [name, setName] = useState('');
  const [type, setType] = useState<'ngo' | 'funder' | 'auditor' | 'government'>('ngo');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError('Enter an organization name.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const client = createApiClient();
      const res = await client.POST('/orgs', {
        body: { name: name.trim(), type },
      });
      if (res.error) {
        const msg = (res.error as { message?: string })?.message || 'Could not create organization.';
        setError(msg);
        setBusy(false);
        return;
      }
      const org = res.data;
      if (org?.slug) {
        window.location.assign(`/app/${encodeURIComponent(org.slug)}/dashboard`);
      } else {
        window.location.assign('/app');
      }
    } catch {
      setError('Could not reach the server. Please try again.');
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: 'grid', gap: 'var(--space-4)' }}>
      {error && (
        <div
          role="alert"
          style={{
            padding: 'var(--space-3)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-sunken)',
            border: '1px solid var(--border-strong)',
            color: 'var(--text-primary)',
            fontSize: 'var(--text-sm)',
          }}
        >
          {error}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <label htmlFor="create-org-name" style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
          Organization name
        </label>
        <input
          id="create-org-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Kariba Conservation Trust"
          required
          style={{
            padding: 'var(--space-2) var(--space-3)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-default)',
            background: 'var(--surface-raised)',
            color: 'var(--text-primary)',
            font: 'inherit',
          }}
        />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <label htmlFor="create-org-type" style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
          Organization type
        </label>
        <select
          id="create-org-type"
          value={type}
          onChange={(e) => setType(e.target.value as typeof type)}
          style={{
            padding: 'var(--space-2) var(--space-3)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-default)',
            background: 'var(--surface-raised)',
            color: 'var(--text-primary)',
            font: 'inherit',
          }}
        >
          <option value="ngo">NGO / Project Developer</option>
          <option value="funder">Funder / Investor</option>
          <option value="auditor">Independent Auditor / VVB</option>
          <option value="government">Government / Regulator</option>
        </select>
      </div>
      <div>
        <Button type="submit" loading={busy}>
          {busy ? 'Creating organization…' : 'Create organization'}
        </Button>
      </div>
    </form>
  );
}

