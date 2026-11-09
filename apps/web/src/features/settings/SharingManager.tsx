'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds';
import { createApiClient, type Schemas } from '../../lib/api-client';
import { apiErrorMessage, detailOf } from '../projects/model';
import { validateGrantSlug } from './model';
import styles from '../projects/projects.module.css';

type Grant = Schemas['GrantView'];
type Level = Schemas['GrantRequest']['level'];
const LEVELS: Level[] = ['view', 'audit', 'contribute'];

/** Grants of one owned project: list, grant to an organization slug, revoke. The API decides what is allowed. */
export function SharingManager({ projectId, projectName, ownerSlug, initialGrants }: { projectId: string; projectName: string; ownerSlug: string; initialGrants: Grant[] }) {
  const [grants, setGrants] = useState<Grant[]>(initialGrants);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const api = createApiClient();

  async function reload() {
    const r = await api.GET('/projects/{project_id}/grants', { params: { path: { project_id: projectId } } });
    if (r.data) setGrants(r.data);
  }

  async function grant(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const org_slug = String(data.get('org_slug') ?? '').trim().toLowerCase();
    const level = String(data.get('level') ?? 'view') as Level;
    const bad = validateGrantSlug(org_slug, ownerSlug);
    if (bad) return setError(bad);
    setBusy(true);
    setError(null);
    try {
      const r = await api.POST('/projects/{project_id}/grants', { params: { path: { project_id: projectId } }, body: { org_slug, level } });
      if (!r.response.ok) setError(apiErrorMessage(r.response.status, detailOf(r.error)));
      else {
        form.reset();
        await reload();
      }
    } catch {
      setError(apiErrorMessage(0));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(g: Grant) {
    setBusy(true);
    setError(null);
    try {
      const r = await api.DELETE('/projects/{project_id}/grants/{org_slug}', { params: { path: { project_id: projectId, org_slug: g.org_slug } } });
      if (!r.response.ok) setError(apiErrorMessage(r.response.status, detailOf(r.error)));
      else setGrants((gs) => gs.filter((x) => x.org_slug !== g.org_slug));
    } catch {
      setError(apiErrorMessage(0));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.section} aria-label={`Sharing for ${projectName}`}>
      <h2>{projectName}</h2>
      {grants.length === 0 ? (
        <p className={styles.muted}>Not shared with any other organization.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
          <caption className={styles.srOnly}>Organizations this project is shared with</caption>
            <thead>
              <tr>
                <th scope="col">Organization</th>
                <th scope="col">Type</th>
                <th scope="col">Level</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {grants.map((g) => (
                <tr key={g.org_slug}>
                  <td>
                    {g.org_name} <span className={styles.muted}>({g.org_slug})</span>
                  </td>
                  <td>{g.org_type}</td>
                  <td>{g.level}</td>
                  <td>
                    <Button variant="danger" size="sm" disabled={busy} onClick={() => revoke(g)}>
                      Revoke
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form className={styles.inline} onSubmit={grant}>
        <div className={styles.field}>
          <label htmlFor={`g-org-${projectId}`}>Organization slug</label>
          <input id={`g-org-${projectId}`} name="org_slug" required />
        </div>
        <div className={styles.field}>
          <label htmlFor={`g-level-${projectId}`}>Level</label>
          <select id={`g-level-${projectId}`} name="level" defaultValue="view">
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>
        <Button type="submit" loading={busy}>Grant access</Button>
      </form>
      {error && <p role="alert" className={styles.error}>{error}</p>}
    </section>
  );
}
