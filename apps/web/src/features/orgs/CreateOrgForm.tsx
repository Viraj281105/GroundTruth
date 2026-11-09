'use client';

import React, { useId, useState } from 'react';
import { Button } from '../../components/ds/Button';
import { createApiClient } from '../../lib/api-client';
import { ORG_NAME_MAX, ORG_TYPE_OPTIONS, orgErrorMessage, validateOrgForm, type NewOrgType, type OrgFormErrors } from './org-form';

const field: React.CSSProperties = {
  padding: 'var(--space-2) var(--space-3)',
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--border-default)',
  background: 'var(--surface-raised)',
  color: 'var(--text-primary)',
  font: 'inherit',
};
const errorText: React.CSSProperties = { color: 'var(--danger-text, var(--text-primary))', fontSize: 'var(--text-sm)', margin: 0 };

export function CreateOrgForm() {
  const ids = useId();
  const nameId = `${ids}-name`;
  const nameErrId = `${ids}-name-err`;
  const typeId = `${ids}-type`;
  const typeHelpId = `${ids}-type-help`;
  const [name, setName] = useState('');
  const [type, setType] = useState<NewOrgType>('ngo');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [errors, setErrors] = useState<OrgFormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const found = validateOrgForm(name, type);
    setErrors(found);
    setFormError(null);
    if (found.name || found.type) {
      if (found.name) document.getElementById(nameId)?.focus();
      return;
    }
    setBusy(true);
    try {
      const res = await createApiClient().POST('/orgs', { body: { name: name.trim(), type } });
      if (res.error || !res.data) {
        setFormError(orgErrorMessage(res.error, res.response?.status));
        setBusy(false);
        return;
      }
      setDone(true);
      window.location.assign(res.data.slug ? `/app/${encodeURIComponent(res.data.slug)}/dashboard` : '/app');
    } catch {
      setFormError('Could not reach the server. Check your connection and try again.');
      setBusy(false);
    }
  }

  const selected = ORG_TYPE_OPTIONS.find((o) => o.value === type);

  return (
    <form onSubmit={submit} noValidate style={{ display: 'grid', gap: 'var(--space-4)' }} aria-busy={busy}>
      {formError && (
        <div role="alert" style={{ padding: 'var(--space-3)', borderRadius: 'var(--radius-md)', background: 'var(--surface-sunken)', border: '1px solid var(--border-strong)', fontSize: 'var(--text-sm)' }}>
          {formError}
        </div>
      )}
      {done && (
        <div role="status" style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
          Organization created. Opening your workspace…
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <label htmlFor={nameId} style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
          Organization name
        </label>
        <input
          id={nameId}
          type="text"
          value={name}
          maxLength={ORG_NAME_MAX}
          autoComplete="organization"
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Lake Shore Conservation Trust"
          aria-required="true"
          aria-invalid={errors.name ? true : undefined}
          aria-describedby={errors.name ? nameErrId : undefined}
          style={field}
        />
        {errors.name && (
          <p id={nameErrId} role="alert" style={errorText}>
            {errors.name}
          </p>
        )}
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: 'var(--space-2)' }}>
        <legend style={{ fontSize: 'var(--text-sm)', fontWeight: 600, padding: 0, marginBottom: 'var(--space-1)' }}>Organization type: what best describes you?</legend>
        {ORG_TYPE_OPTIONS.map((o) => (
          <label key={o.value} style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'flex-start', cursor: 'pointer' }}>
            <input type="radio" name={typeId} value={o.value} checked={type === o.value} onChange={() => setType(o.value)} aria-describedby={typeHelpId} style={{ marginTop: '0.3rem' }} />
            <span>
              <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{o.label}</span>
              <span style={{ display: 'block', color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>{o.plain}</span>
            </span>
          </label>
        ))}
        <span id={typeHelpId} className="sr-only">
          {selected?.plain}
        </span>
        {errors.type && (
          <p role="alert" style={errorText}>
            {errors.type}
          </p>
        )}
      </fieldset>
      <div>
        <Button type="submit" loading={busy}>
          {busy ? 'Creating organization…' : 'Create organization'}
        </Button>
      </div>
    </form>
  );
}
