'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds';
import { MEMBER_ROLE_LABELS } from '../../components/shell/navigation';
import { createApiClient, type Schemas } from '../../lib/api-client';
import { apiErrorMessage, detailOf } from '../projects/model';
import styles from '../projects/projects.module.css';
import { assignableRoles, canManageSettings, memberControls, type Role } from './model';

type Member = Schemas['MemberView'];

/** Members list with add / change role / remove. Controls the caller's role cannot use are not rendered. */
export function MembersTable({ orgSlug, actorRole, actorUserId, initialMembers }: { orgSlug: string; actorRole: Role; actorUserId: string | null; initialMembers: Member[] }) {
  const [members, setMembers] = useState<Member[]>(initialMembers);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const roles = assignableRoles(actorRole);
  const api = createApiClient();

  async function run(fn: () => Promise<{ response: Response; error?: unknown }>, after: () => void) {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      if (!r.response.ok) setError(apiErrorMessage(r.response.status, detailOf(r.error)));
      else after();
    } catch {
      setError(apiErrorMessage(0));
    } finally {
      setBusy(false);
    }
  }

  const changeRole = (m: Member, role: Role) =>
    run(
      () => api.PATCH('/orgs/{slug}/members/{user_id}', { params: { path: { slug: orgSlug, user_id: m.user_id } }, body: { role } }),
      () => setMembers((ms) => ms.map((x) => (x.user_id === m.user_id ? { ...x, role } : x))),
    );
  const remove = (m: Member) =>
    run(
      () => api.DELETE('/orgs/{slug}/members/{user_id}', { params: { path: { slug: orgSlug, user_id: m.user_id } } }),
      () => setMembers((ms) => ms.filter((x) => x.user_id !== m.user_id)),
    );

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const email = String(data.get('email') ?? '').trim();
    const role = String(data.get('role') ?? 'member') as Role;
    if (!email) return setError('Enter the email of an existing GroundTruth account.');
    await run(
      () => api.POST('/orgs/{slug}/members', { params: { path: { slug: orgSlug } }, body: { email, role } }),
      () => {
        form.reset();
        // The API returns no list; reload it so the new row carries its real id and date.
        void api.GET('/orgs/{slug}/members', { params: { path: { slug: orgSlug } } }).then((r) => r.data && setMembers(r.data));
      },
    );
  }

  return (
    <div className={styles.section}>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className={styles.srOnly}>Organization members</caption>
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              {canManageSettings(actorRole) && <th scope="col">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {members.map((m) => {
              const c = memberControls(actorRole, m.role, m.user_id === actorUserId);
              return (
                <tr key={m.user_id}>
                  <td>{m.email}</td>
                  <td>
                    {c.canChangeRole ? (
                      <select aria-label={`Role for ${m.email}`} value={m.role} disabled={busy} onChange={(e) => changeRole(m, e.target.value as Role)}>
                        {roles.map((r) => (
                          <option key={r} value={r}>{MEMBER_ROLE_LABELS[r]}</option>
                        ))}
                        {!roles.includes(m.role) && <option value={m.role}>{MEMBER_ROLE_LABELS[m.role]}</option>}
                      </select>
                    ) : (
                      MEMBER_ROLE_LABELS[m.role]
                    )}
                  </td>
                  {canManageSettings(actorRole) && (
                    <td>
                      {c.canRemove && (
                        <Button variant="danger" size="sm" disabled={busy} onClick={() => remove(m)}>
                          Remove
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {canManageSettings(actorRole) && (
        <form className={styles.inline} onSubmit={add}>
          <div className={styles.field}>
            <label htmlFor="mem-email">Email of an existing account</label>
            <input id="mem-email" name="email" type="email" required />
          </div>
          <div className={styles.field}>
            <label htmlFor="mem-role">Role</label>
            <select id="mem-role" name="role" defaultValue="member">
              {roles.map((r) => (
                <option key={r} value={r}>{MEMBER_ROLE_LABELS[r]}</option>
              ))}
            </select>
          </div>
          <Button type="submit" loading={busy}>Add member</Button>
        </form>
      )}
      {error && <p role="alert" className={styles.error}>{error}</p>}
    </div>
  );
}
