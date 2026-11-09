'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown } from 'lucide-react';
import { createApiClient, type Schemas } from '../../lib/api-client';
import { useToast } from '../ds/Overlay';
import { PerspectiveBadge } from './PerspectiveBadge';
import { MEMBER_ROLE_LABELS, PERSPECTIVE_LABELS } from './navigation';
import styles from './OrgShell.module.css';

type Org = Schemas['OrgView'];

/** Lists the organizations from /auth/me. Choosing one sets it active on the API, then opens its dashboard. */
export function OrgSwitcher({ orgs, active }: { orgs: Org[]; active: Org }) {
  const router = useRouter();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  async function choose(slug: string) {
    if (slug === active.slug) return setOpen(false);
    setBusy(slug);
    try {
      const res = await createApiClient().POST('/orgs/active', { body: { slug } });
      if (res.error) throw new Error(String(res.response.status));
      setOpen(false);
      router.push(`/app/${slug}/dashboard`);
      router.refresh();
    } catch {
      toast('Could not switch organization. Try again.', 'error');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={styles.orgsw} ref={wrap}>
      <button ref={trigger} type="button" className={styles.orgbtn} aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((v) => !v)} title={active.name}>
        <span className={styles.orgmark} aria-hidden="true">
          {active.name.slice(0, 1).toUpperCase()}
        </span>
        <span className={styles.orgtxt}>
          <b>{active.name}</b>
          <PerspectiveBadge orgType={active.type} />
        </span>
        <ChevronDown size={16} aria-hidden="true" className={styles.orgchev} />
      </button>
      {open && (
        <div className={styles.orgmenu} id={menuId} role="group" aria-label="Organizations">
          {orgs.map((o) => (
            <button key={o.id} type="button" aria-current={o.slug === active.slug ? 'true' : undefined} disabled={busy !== null} onClick={() => void choose(o.slug)}>
              <span>
                {o.name}
                <small>
                  {PERSPECTIVE_LABELS[o.type]} · {MEMBER_ROLE_LABELS[o.role]}
                </small>
              </span>
              {busy === o.slug && <span className={styles.busy}>Switching</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
