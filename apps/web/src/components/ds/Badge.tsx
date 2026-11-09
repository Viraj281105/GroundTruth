import React from 'react';
import styles from './Badge.module.css';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: 'neutral' | 'positive' | 'caution' | 'info' | 'simulated' | 'inconclusive' | 'error';
  variant?: 'subtle' | 'outline' | 'solid';
  size?: 'sm' | 'md';
  icon?: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  tone = 'neutral',
  variant = 'subtle',
  size = 'md',
  icon,
  className = '',
  ...props
}) => {
  return (
    <span
      className={`${styles.badge} ${styles[tone]} ${styles[variant]} ${styles[size]} ${className}`}
      {...props}
    >
      {icon && <span className={styles.icon}>{icon}</span>}
      <span>{children}</span>
    </span>
  );
};
