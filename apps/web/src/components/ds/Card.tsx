import React from 'react';
import styles from './Card.module.css';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** `raised` is the default surface; `sunken` is for nested/inset content; `interactive` adds hover lift. */
  tone?: 'raised' | 'sunken' | 'interactive';
  padded?: boolean;
}

export function Card({ tone = 'raised', padded = true, className = '', ...rest }: CardProps) {
  return <div className={`${styles.card} ${styles[tone]} ${padded ? styles.padded : ''} ${className}`} {...rest} />;
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className={styles.stat}>
      <div className={styles.statLabel}>{label}</div>
      <div className={`${styles.statValue} num`}>{value}</div>
      {hint && <div className={styles.statHint}>{hint}</div>}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className={styles.empty} role="status">
      <h3>{title}</h3>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ width = '100%', height = '1rem', radius }: { width?: string; height?: string; radius?: string }) {
  return <span className={styles.skeleton} style={{ width, height, borderRadius: radius }} aria-hidden="true" />;
}

type DivProps = React.HTMLAttributes<HTMLDivElement>;
const join = (a: string, b?: string) => (b ? `${a} ${b}` : a);

/** Compound parts for cards that need a header/content split (use with `<Card padded={false}>`). */
export function CardHeader({ className, ...rest }: DivProps) {
  return <div className={join(styles.header, className)} {...rest} />;
}
export function CardTitle({ className, ...rest }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={join(styles.title, className)} {...rest} />;
}
export function CardDescription({ className, ...rest }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={join(styles.description, className)} {...rest} />;
}
export function CardContent({ className, ...rest }: DivProps) {
  return <div className={join(styles.content, className)} {...rest} />;
}
export function CardFooter({ className, ...rest }: DivProps) {
  return <div className={join(styles.footer, className)} {...rest} />;
}
