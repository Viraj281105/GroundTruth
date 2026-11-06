'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Card, Skeleton } from '../../components/ds/Card';
import { Chip } from '../../components/ds/Chip';
import { Reveal } from '../../components/ds/Reveal';
import { useToast } from '../../components/ds/Overlay';
import { useAuth } from '../../lib/auth';
import { ROLE_LABELS, type Role } from '../../lib/auth-core';
import { listUsers, updateUser, type UserView } from './auth-api';
import { FormError } from './Field';
import { RequireRole } from './RequireAuth';
import styles from './auth.module.css';

const ROLES: Role[] = ['user', 'dev', 'admin'];

export function UsersAdmin() {
  return (
    <div className={`${styles.page} ${styles.wide}`}>
      <Reveal>
        <h1 className={styles.title}>Manage users</h1>
        <p className={styles.muted}>Change roles and switch accounts on or off. There must always be at least one active admin.</p>
      </Reveal>
      <RequireRole minimum="admin">
        <UsersTable />
      </RequireRole>
    </div>
  );
}

function UsersTable() {
  const { user: me, refresh } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState<UserView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await listUsers();
    if (r.ok) {
      setUsers(r.data);
      setError(null);
    } else {
      setError(r.message);
      setUsers((u) => u ?? []);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function change(u: UserView, patch: { role?: Role; is_active?: boolean }) {
    setBusyId(u.id);
    setError(null);
    const r = await updateUser(u.id, patch);
    setBusyId(null);
    if (!r.ok) {
      setError(r.message);
      await load(); // put the controls back to what the server says
      return;
    }
    toast(`Updated ${u.email}.`, 'success');
    await load();
    if (u.id === me?.id) await refresh();
  }

  if (!users) return <Skeleton height="12rem" />;

  const controls = (u: UserView) => (
    <>
      <select
        className={styles.select}
        value={u.role}
        disabled={busyId === u.id}
        aria-label={`Role for ${u.email}`}
        onChange={(e) => void change(u, { role: e.target.value as Role })}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABELS[r]}
          </option>
        ))}
      </select>
      <label className={styles.switch}>
        <input type="checkbox" checked={u.is_active} disabled={busyId === u.id} onChange={(e) => void change(u, { is_active: e.target.checked })} />
        {u.is_active ? 'Active' : 'Inactive'}
        <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}> account {u.email}</span>
      </label>
    </>
  );

  return (
    <>
      <FormError message={error} />
      {users.length === 0 ? (
        <Card>
          <p className={styles.muted}>No users to show.</p>
        </Card>
      ) : (
        <>
          <Card padded={false}>
            <table className={styles.table}>
              <caption style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Accounts</caption>
              <thead>
                <tr>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Status</th>
                  <th scope="col">Last sign in</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      {u.email} {u.id === me?.id && <Chip>You</Chip>}
                    </td>
                    <td>
                      <select
                        className={styles.select}
                        value={u.role}
                        disabled={busyId === u.id}
                        aria-label={`Role for ${u.email}`}
                        onChange={(e) => void change(u, { role: e.target.value as Role })}
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABELS[r]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <label className={styles.switch}>
                        <input type="checkbox" checked={u.is_active} disabled={busyId === u.id} aria-label={`Active: ${u.email}`} onChange={(e) => void change(u, { is_active: e.target.checked })} />
                        {u.is_active ? 'Active' : 'Inactive'}
                      </label>
                    </td>
                    <td>{u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'Never'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <div className={styles.cards}>
            {users.map((u) => (
              <Card key={u.id} className={styles.userCard}>
                <strong style={{ overflowWrap: 'anywhere' }}>{u.email}</strong>
                {controls(u)}
              </Card>
            ))}
          </div>
        </>
      )}
    </>
  );
}
