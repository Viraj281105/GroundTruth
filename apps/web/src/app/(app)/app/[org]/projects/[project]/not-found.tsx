'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { EmptyState } from '../../../../../../components/ds';

/** Unknown project, or one this account cannot open: the API answers the same way for both, and so does this page. */
export default function ProjectNotFound() {
  const org = /^\/app\/([^/]+)/.exec(usePathname() ?? '')?.[1];
  return (
    <EmptyState
      title="Project not found"
      body="This project does not exist, or your account does not have access to it."
      action={<Link href={org ? `/app/${org}/projects` : '/app'}>Back to projects</Link>}
    />
  );
}
