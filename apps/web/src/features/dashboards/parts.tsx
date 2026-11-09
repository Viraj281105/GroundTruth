import React from 'react';
import { Chip } from '../../components/ds/Chip';
import { EmptyState, LinkButton } from '../../components/ds';
import { UnavailablePanel } from '../../components/ds/UnavailablePanel';
import type { Panel, Project, ProjectScope } from './loadDashboardData';
import styles from './dashboards.module.css';

export const API_NEEDED = 'A reachable API and access to this resource. No substitute data is shown.';

/** A titled dashboard region with a stable id so tests and anchors can find it. Supports collapsible progressive disclosure. */
export function Region({
  id,
  title,
  label,
  children,
  wide,
  collapsible = false,
  defaultOpen = false,
  badge,
}: {
  id: string;
  title?: string;
  label?: string;
  children: React.ReactNode;
  wide?: boolean;
  collapsible?: boolean;
  defaultOpen?: boolean;
  badge?: string;
}) {
  const headingText = title ?? label ?? id;
  if (!collapsible) {
    return (
      <section className={`${styles.region} ${wide ? styles.wide : ''}`} data-panel={id} aria-label={headingText}>
        {title ? <h2 className={styles.regionTitle}>{title}</h2> : label && <h2 className="sr-only">{label}</h2>}
        {children}
      </section>
    );
  }

  return (
    <section className={`${styles.region} ${wide ? styles.wide : ''}`} data-panel={id} aria-label={headingText}>
      {title ? <h2 className={styles.regionTitle}>{title}</h2> : label && <h2 className="sr-only">{label}</h2>}
      <details className={styles.regionDetails} open={defaultOpen}>
        <summary className={styles.regionSummary}>
          <div className={styles.regionSummaryLeft}>
            <span className={styles.regionSummaryTitle}>{title ?? label ?? id}</span>
            {badge && <span className={styles.regionBadge}>{badge}</span>}
          </div>
          <span className={styles.regionChevron} aria-hidden="true">▾</span>
        </summary>
        <div className={styles.regionBody}>
          {children}
        </div>
      </details>
    </section>
  );
}

/** Renders `ok` panels with `render`; an unavailable one degrades to an UnavailablePanel and nothing else. */
export function Slot<T>({ panel, title, render }: { panel: Panel<T> | null; title: string; render: (data: T) => React.ReactNode }) {
  if (!panel) return null;
  if (panel.status === 'unavailable') return <UnavailablePanel title={title} reason={panel.reason} evidenceNeeded={API_NEEDED} />;
  return <>{render(panel.data)}</>;
}

/** The persona's decision question, shown as the dashboard's lead heading. */
export function Question({ text }: { text: string }) {
  return (
    <h1 className={styles.question} data-persona-question>
      {text}
    </h1>
  );
}

export function LibraryNotice({ project }: { project: Project }) {
  return (
    <div className={styles.library} data-library-case>
      <Chip>Library case — no boundary or data</Chip>
      <p>
        {project.name} is a scaffolded library case. It has no boundary and no observations, so no assessment, map or evidence panels are shown for it.
      </p>
    </div>
  );
}

/** Links to `?project=<slug>`; plain anchors so the dashboard stays a server component. */
export function ProjectSwitcher({ orgSlug, scope }: { orgSlug: string; scope: ProjectScope }) {
  if (scope.projects.length < 2) return null;
  return (
    <nav className={styles.switcher} aria-label="Project">
      <span>Project</span>
      <ul>
        {scope.projects.map((p) => (
          <li key={p.id}>
            <a href={`/app/${orgSlug}/dashboard?project=${encodeURIComponent(p.slug)}`} aria-current={scope.selected?.id === p.id ? 'true' : undefined}>
              {p.name}
              {p.data_mode === 'simulated' ? ' (simulated)' : ''}
              {!p.boundary_sha256 ? ' (library case)' : ''}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function NoProjects({ orgSlug, readOnly }: { orgSlug: string; readOnly?: boolean }) {
  return (
    <EmptyState
      title="No projects yet"
      body="Projects this organization owns, or that another organization has shared with it, appear here."
      action={readOnly ? undefined : <LinkButton href={`/app/${orgSlug}/projects/new`}>Create a project</LinkButton>}
    />
  );
}
