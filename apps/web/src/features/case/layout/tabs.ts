import { CASE_TABS } from './copy';

export interface TabLink {
  href: string;
  label: string;
}

/** Tab links for one case. The case id is encoded so odd ids never break the path. */
export function caseTabLinks(caseId: string): TabLink[] {
  const base = `/cases/${encodeURIComponent(caseId)}`;
  return CASE_TABS.map((t) => ({ href: t.slug ? `${base}/${t.slug}` : base, label: t.label }));
}

/**
 * The tab whose href is the longest prefix of the pathname. Pages that are not tabs (such as
 * `/run`) highlight no tab, so Overview is active only on its own route.
 */
export function activeTabHref(links: TabLink[], pathname: string): string {
  const clean = pathname.replace(/\/+$/, '') || '/';
  let best = '';
  links.forEach((l, i) => {
    // The first link is Overview (the case root): it must not claim every sub-route as its own.
    const matches = clean === l.href || (i > 0 && clean.startsWith(`${l.href}/`));
    if (matches && l.href.length >= best.length) best = l.href;
  });
  return best;
}
