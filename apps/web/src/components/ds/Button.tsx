'use client';

import React from 'react';
import Link from 'next/link';
import styles from './Button.module.css';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface CommonProps {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: React.ReactNode;
}

export type ButtonProps = CommonProps & React.ButtonHTMLAttributes<HTMLButtonElement>;
export type LinkButtonProps = CommonProps & { href: string } & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>;

function cls(variant: Variant, size: Size, extra: string) {
  return `${styles.button} ${styles[variant]} ${styles[size]} ${extra}`.trim();
}

export function Button({ variant = 'primary', size = 'md', loading = false, icon, className = '', children, disabled, ...rest }: ButtonProps) {
  return (
    <button className={cls(variant, size, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : icon}
      {children}
    </button>
  );
}

/** A link that looks like a Button, for navigation (keeps real anchor semantics). */
export function LinkButton({ variant = 'primary', size = 'md', icon, className = '', children, href, ...rest }: LinkButtonProps) {
  return (
    <Link href={href} className={cls(variant, size, className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}
