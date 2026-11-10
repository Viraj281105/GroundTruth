/** Command palette logic: pure, so it is testable without a browser. */

export interface PaletteCase {
  id: string;
  name: string;
}

export interface PaletteContext {
  /** Cases (legacy shell) or, inside an organization, that organization's projects (id = project slug). */
  cases: PaletteCase[];
  /** Recently viewed case ids, newest first. */
  recent: string[];
  /**
   * Slug of the organization the palette is opened in. When set, every entry stays inside
   * `/app/<org>/...`: a project opens under the organization that can see it, and the pre-2.0
   * pages (cases, compare, claims workbench), which have no organization scope, are not offered.
   */
  org?: string;
}

export interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  group: 'Suggested' | 'Go to' | 'Recent' | 'Cases' | 'Projects' | 'Actions';
  href?: string;
  /** `theme:dark`, `lens:auditor`, `tour`, `shortcuts` ... handled by the palette component. */
  action?: string;
  keywords?: string;
}

const PAGES: PaletteItem[] = [
  { id: 'go-home', label: 'Home', group: 'Go to', href: '/', keywords: 'start landing' },
  { id: 'go-cases', label: 'Cases', group: 'Go to', href: '/cases', keywords: 'projects investigations' },
  { id: 'go-compare', label: 'Compare cases', group: 'Go to', href: '/compare', keywords: 'side by side' },
  { id: 'go-claims', label: 'Claims workbench', group: 'Go to', href: '/claims', keywords: 'documents baseline credits' },
  { id: 'go-method', label: 'How it works', group: 'Go to', href: '/method', keywords: 'method glossary help' },
  { id: 'go-status', label: 'System status', group: 'Go to', href: '/status', keywords: 'health engine' },
];

/** Destinations inside an organization. Every one of these exists for every role. */
function orgPages(org: string): PaletteItem[] {
  const at = (path: string) => `/app/${org}/${path}`;
  return [
    { id: 'go-overview', label: 'Overview', group: 'Go to', href: at('dashboard'), keywords: 'dashboard home start' },
    { id: 'go-projects', label: 'Projects', group: 'Go to', href: at('projects'), keywords: 'cases list' },
    { id: 'go-assessments', label: 'Assessments', group: 'Go to', href: at('assessments'), keywords: 'claims verification' },
    { id: 'go-evidence-library', label: 'Evidence Library', group: 'Go to', href: at('evidence-library'), keywords: 'datasets sources registry documents' },
    { id: 'go-reports', label: 'Reports', group: 'Go to', href: at('reports'), keywords: 'dossier download ledger' },
    { id: 'go-method', label: 'How it works', group: 'Go to', href: '/method', keywords: 'method glossary help' },
  ];
}

/** Where a project opens: inside the organization when there is one, else the pre-2.0 case page. */
function projectHref(id: string, org: string | undefined): string {
  return org ? `/app/${org}/projects/${id}/overview` : `/cases/${id}`;
}

const ACTIONS: PaletteItem[] = [
  { id: 'theme-light', label: 'Switch to light theme', group: 'Actions', action: 'theme:light', keywords: 'appearance bright' },
  { id: 'theme-dark', label: 'Switch to dark theme', group: 'Actions', action: 'theme:dark', keywords: 'appearance night' },
  { id: 'theme-system', label: 'Match system theme', group: 'Actions', action: 'theme:system', keywords: 'appearance auto' },
  { id: 'lens-story', label: 'Detail level: Story', group: 'Actions', action: 'lens:story', keywords: 'simple plain' },
  { id: 'lens-explorer', label: 'Detail level: Explorer', group: 'Actions', action: 'lens:explorer', keywords: 'interactive' },
  { id: 'lens-auditor', label: 'Detail level: Auditor', group: 'Actions', action: 'lens:auditor', keywords: 'full diagnostics expert' },
  { id: 'tour', label: 'Take the guided tour', group: 'Actions', action: 'tour', keywords: 'help onboarding intro' },
  { id: 'shortcuts', label: 'Keyboard shortcuts', group: 'Actions', action: 'shortcuts', keywords: 'help keys' },
];

function norm(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9+\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

/** Resolve a fragment like "kariba" or "cardamom" to a case by id/name tokens. */
function findCase(fragment: string, cases: PaletteCase[]): PaletteCase | null {
  const f = norm(fragment);
  if (!f) return null;
  const scored = cases
    .map((c) => {
      const hay = norm(`${c.id} ${c.name}`);
      const exact = hay.split(' ').includes(f) ? 2 : hay.includes(f) ? 1 : 0;
      return { c, exact };
    })
    .filter((x) => x.exact > 0)
    .sort((a, b) => b.exact - a.exact);
  return scored[0]?.c ?? null;
}

/** "compare kariba and mikoko" / "kariba vs mikoko" / "compare a with b" -> /compare URL. */
export function parseCompareIntent(query: string, cases: PaletteCase[]): string | null {
  const q = norm(query).replace(/^compare\s+/, '');
  const parts = q.split(/\s+(?:and|vs|versus|with|&)\s+/);
  if (parts.length !== 2) return null;
  const a = findCase(parts[0], cases);
  const b = findCase(parts[1], cases);
  if (!a || !b || a.id === b.id) return null;
  return `/compare?a=${a.id}&b=${b.id}`;
}

function matches(item: PaletteItem, q: string): boolean {
  return norm(`${item.label} ${item.keywords ?? ''} ${item.hint ?? ''}`).includes(q);
}

export function resolveCommands(query: string, ctx: PaletteContext): PaletteItem[] {
  const q = norm(query);
  const { org } = ctx;
  const pages = org ? orgPages(org) : PAGES;
  const caseItems: PaletteItem[] = ctx.cases.map((c) => ({
    id: `case-${c.id}`,
    label: c.name,
    hint: org ? 'Open project' : 'Open case',
    group: org ? 'Projects' : 'Cases',
    href: projectHref(c.id, org),
    keywords: c.id,
  }));

  if (!q) {
    const recent: PaletteItem[] = ctx.recent
      .map((id) => ctx.cases.find((c) => c.id === id))
      .filter((c): c is PaletteCase => Boolean(c))
      .map((c) => ({ id: `recent-${c.id}`, label: c.name, hint: 'Recently viewed', group: 'Recent' as const, href: projectHref(c.id, org) }));
    // With nothing typed, an organization's own projects are listed too: there are usually few.
    return [...pages, ...recent, ...(org ? caseItems : []), ...ACTIONS];
  }

  const out: PaletteItem[] = [];
  // The compare page is a pre-2.0 page with no organization scope, so it is not suggested inside one.
  const compare = org ? null : parseCompareIntent(query, ctx.cases);
  if (compare) out.push({ id: 'nl-compare', label: `Compare ${query.replace(/^compare\s+/i, '')}`, hint: 'Natural-language command', group: 'Suggested', href: compare });
  out.push(...caseItems.filter((i) => matches(i, q)));
  out.push(...pages.filter((i) => matches(i, q)));
  out.push(...ACTIONS.filter((i) => matches(i, q)));
  return out;
}
