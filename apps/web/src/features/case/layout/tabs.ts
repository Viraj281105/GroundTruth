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

/** The tab whose href is the longest prefix of the pathname; Overview when nothing deeper matches. */
export function activeTabHref(links: TabLink[], pathname: string): string {
  const clean = pathname.replace(/\/+$/, '') || '/';
  let best = links[0]?.href ?? '';
  for (const l of links) {
    if ((clean === l.href || clean.startsWith(`${l.href}/`)) && l.href.length >= best.length) best = l.href;
  }
  return best;
}
