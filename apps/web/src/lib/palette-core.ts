/** Command palette logic: pure, so it is testable without a browser. */

export interface PaletteCase {
  id: string;
  name: string;
}

export interface PaletteContext {
  cases: PaletteCase[];
  /** Recently viewed case ids, newest first. */
  recent: string[];
}

export interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  group: 'Suggested' | 'Go to' | 'Recent' | 'Cases' | 'Actions';
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
  const caseItems: PaletteItem[] = ctx.cases.map((c) => ({
    id: `case-${c.id}`,
    label: c.name,
    hint: 'Open case',
    group: 'Cases',
    href: `/cases/${c.id}`,
    keywords: c.id,
  }));

  if (!q) {
    const recent: PaletteItem[] = ctx.recent
      .map((id) => ctx.cases.find((c) => c.id === id))
      .filter((c): c is PaletteCase => Boolean(c))
      .map((c) => ({ id: `recent-${c.id}`, label: c.name, hint: 'Recently viewed', group: 'Recent' as const, href: `/cases/${c.id}` }));
    return [...PAGES, ...recent, ...ACTIONS];
  }

  const out: PaletteItem[] = [];
  const compare = parseCompareIntent(query, ctx.cases);
  if (compare) out.push({ id: 'nl-compare', label: `Compare ${query.replace(/^compare\s+/i, '')}`, hint: 'Natural-language command', group: 'Suggested', href: compare });
  out.push(...caseItems.filter((i) => matches(i, q)));
  out.push(...PAGES.filter((i) => matches(i, q)));
  out.push(...ACTIONS.filter((i) => matches(i, q)));
  return out;
}
