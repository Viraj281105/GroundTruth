import React from 'react';
import Link from 'next/link';
import styles from './Tabs.module.css';

export interface TabItem {
  href: string;
  label: string;
}

/**
 * Route-based tab bar: every tab is a real link (deep-linkable, back-button friendly).
 * Scrolls horizontally on narrow screens instead of wrapping.
 */
export function TabBar({ items, activeHref, label }: { items: TabItem[]; activeHref: string; label: string }) {
  return (
    <nav className={styles.bar} aria-label={label}>
      {items.map((item) => {
        const active = item.href === activeHref;
        return (
          <Link key={item.href} href={item.href} className={`${styles.tab} ${active ? styles.active : ''}`} aria-current={active ? 'page' : undefined}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Hover/focus tooltip for short explanations. The trigger stays focusable; content is described by aria. */
export function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const id = React.useId();
  return (
    <span className={styles.tipWrap}>
      <span aria-describedby={id} tabIndex={0} className={styles.tipTrigger}>
        {children}
      </span>
      <span role="tooltip" id={id} className={styles.tip}>
        {text}
      </span>
    </span>
  );
}
