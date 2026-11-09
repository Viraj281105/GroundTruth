import React from 'react';
import { PERSPECTIVE_LABELS, type OrgType } from './navigation';
import styles from './OrgShell.module.css';

/** Says which perspective the app is showing: it follows the organization type, not the person. */
export function PerspectiveBadge({ orgType }: { orgType: OrgType }) {
  return (
    <span className={styles.persp} data-org-type={orgType}>
      <i aria-hidden="true" />
      {PERSPECTIVE_LABELS[orgType]}
    </span>
  );
}
