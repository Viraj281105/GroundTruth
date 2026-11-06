'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ChevronDown, LogOut, Info, Activity, UserRound, Users } from 'lucide-react';
import { useAuth } from '../../lib/auth';
import { initials, menuLinksFor, ROLE_LABELS } from '../../lib/auth-core';
import { Chip } from '../ds/Chip';
import { LinkButton } from '../ds/Button';
import { useToast } from '../ds/Overlay';
import styles from './UserMenu.module.css';

const ICONS: Record<string, React.ReactNode> = {
  '/account': <UserRound size={16} />,
  '/method': <Info size={16} />,
  '/status': <Activity size={16} />,
  '/admin/users': <Users size={16} />,
};

/** Account menu. Method and Status live here (not in the main nav); what shows depends on the role. */
export function UserMenu() {
  const { status, user, signOut } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (status === 'loading') return <span className={styles.skeleton} aria-hidden="true" />;

  const links = menuLinksFor(user?.role);

  return (
    <div className={styles.wrap} ref={wrap}>
      {user ? (
        <button type="button" className={styles.trigger} onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open} aria-label="Account menu">
          <span className={styles.avatar}>{initials(user.email)}</span>
          <ChevronDown size={14} aria-hidden="true" className={open ? styles.flip : ''} />
        </button>
      ) : (
        <span className={styles.signedOut}>
          <LinkButton href="/login" size="sm" variant="secondary">
            Sign in
          </LinkButton>
          <button type="button" className={styles.more} onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open} aria-label="More">
            <ChevronDown size={14} aria-hidden="true" />
          </button>
        </span>
      )}

      {open && (
        <div className={styles.menu} role="menu">
          {user && (
            <div className={styles.who}>
              <div className={styles.email}>{user.email}</div>
              <Chip tone={user.role === 'admin' ? 'caution' : user.role === 'dev' ? 'accent' : 'neutral'}>{ROLE_LABELS[user.role]}</Chip>
            </div>
          )}
          {links.map((l) => (
            <Link key={l.href} href={l.href} role="menuitem" className={styles.item} onClick={() => setOpen(false)}>
              {ICONS[l.href]}
              {l.label}
            </Link>
          ))}
          {user ? (
            <button
              type="button"
              role="menuitem"
              className={`${styles.item} ${styles.danger}`}
              onClick={async () => {
                setOpen(false);
                await signOut();
                toast('Signed out');
                router.push('/');
              }}
            >
              <LogOut size={16} />
              Sign out
            </button>
          ) : (
            <Link href="/register" role="menuitem" className={styles.item} onClick={() => setOpen(false)}>
              <UserRound size={16} />
              Create an account
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
