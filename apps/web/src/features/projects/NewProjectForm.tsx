'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '../../components/ds';
import { getApiBaseUrl } from '../../lib/api';
import { apiErrorMessage, detailOf } from './model';
import { FIELD_LIMITS, validateProjectFields, type ProjectFieldErrors } from './validate';
import styles from './projects.module.css';

const ECOSYSTEM_SUGGESTIONS = ['forest', 'forest / woodland', 'mangrove', 'grassland', 'wetland', 'peatland', 'agroforestry'];

/** Boundary upload. Validation here avoids a wasted round trip; the server's 422 messages are shown as sent. */
export function NewProjectForm({ orgSlug }: { orgSlug: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<ProjectFieldErrors>({});
  const [busy, setBusy] = useState(false);

  const a11y = (k: keyof ProjectFieldErrors, extra?: string) => ({
    'aria-invalid': fields[k] ? true : undefined,
    'aria-describedby': [fields[k] ? `np-${k}-err` : null, extra].filter(Boolean).join(' ') || undefined,
  });
  const err = (k: keyof ProjectFieldErrors) => (fields[k] ? <span id={`np-${k}-err`} className={styles.error}>{fields[k]}</span> : null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const s = (k: string) => String(data.get(k) ?? '');
    const file = data.get('boundary');
    const problems = validateProjectFields({
      name: s('name'),
      country: s('country'),
      ecosystem: s('ecosystem'),
      intervention: s('intervention'),
      year: s('treatment_start_year'),
      file: file instanceof File && file.name ? file : null,
    });
    setFields(problems);
    if (Object.keys(problems).length > 0) return setError('Fix the highlighted fields.');
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/orgs/${encodeURIComponent(orgSlug)}/projects`, { method: 'POST', body: data, credentials: 'include' });
      const body: unknown = await res.json().catch(() => null);
      if (!res.ok) {
        setError(apiErrorMessage(res.status, detailOf(body)));
        return;
      }
      const slug = (body as { slug?: string } | null)?.slug;
      router.push(slug ? `/app/${orgSlug}/projects/${slug}/overview` : `/app/${orgSlug}/projects`);
    } catch {
      setError(apiErrorMessage(0));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={submit} noValidate>
      <div className={styles.field}>
        <label htmlFor="np-name">Project name</label>
        <input id="np-name" name="name" required maxLength={FIELD_LIMITS.name} {...a11y('name')} />
        {err('name')}
      </div>
      <div className={styles.field}>
        <label htmlFor="np-country">Country</label>
        <input id="np-country" name="country" required maxLength={FIELD_LIMITS.country} {...a11y('country')} />
        {err('country')}
      </div>
      <div className={styles.field}>
        <label htmlFor="np-eco">Ecosystem</label>
        <input id="np-eco" name="ecosystem" list="np-eco-list" required maxLength={FIELD_LIMITS.ecosystem} {...a11y('ecosystem')} />
        <datalist id="np-eco-list">
          {ECOSYSTEM_SUGGESTIONS.map((e) => (
            <option key={e} value={e} />
          ))}
        </datalist>
        {err('ecosystem')}
      </div>
      <div className={styles.field}>
        <label htmlFor="np-int">Intervention</label>
        <input id="np-int" name="intervention" required maxLength={FIELD_LIMITS.intervention} placeholder="e.g. restoration, avoided deforestation" {...a11y('intervention')} />
        {err('intervention')}
      </div>
      <div className={styles.field}>
        <label htmlFor="np-year">Treatment start year</label>
        <input id="np-year" name="treatment_start_year" type="number" min={FIELD_LIMITS.yearMin} max={FIELD_LIMITS.yearMax} step={1} required {...a11y('year')} />
        {err('year')}
      </div>
      <div className={styles.field}>
        <label htmlFor="np-file">Boundary file</label>
        <input id="np-file" name="boundary" type="file" accept=".geojson,.json,.kml" required {...a11y('file', 'np-file-hint')} />
        <span id="np-file-hint" className={styles.hint}>GeoJSON or KML, up to 5 MB. The server validates the geometry.</span>
        {err('file')}
      </div>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <div className={styles.actions}>
        <Button type="submit" loading={busy}>Create project</Button>
      </div>
    </form>
  );
}
