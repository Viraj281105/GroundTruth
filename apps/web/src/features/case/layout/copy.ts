/** English UI copy for the case layout. */
export const layoutCopy = {
  breadcrumbRoot: 'Cases',
  breadcrumbLabel: 'Breadcrumb',
  tabsLabel: 'Case sections',
  runAnalysis: 'Run analysis',
  demoChip: 'Demo mode: fixture data',
  notFoundTitle: 'We could not find this case',
  notFoundBody: 'There is no case with this identifier. It may have been renamed, or the link may be mistyped.',
  notFoundAction: 'Back to all cases',
  unreachableTitle: 'The analysis service is not reachable',
  unreachableBody:
    'This page needs the GroundTruth API and cannot show a case without it. Nothing on screen is a stand-in for real results.',
  unreachableHint: 'Check that the API is running at the address below, then reload the page.',
  unreachableAction: 'Back to all cases',
} as const;

export interface CaseTab {
  slug: '' | 'evidence' | 'robustness' | 'method' | 'report';
  label: string;
}

export const CASE_TABS: readonly CaseTab[] = [
  { slug: '', label: 'Overview' },
  { slug: 'evidence', label: 'Evidence' },
  { slug: 'robustness', label: 'Robustness' },
  { slug: 'method', label: 'Method' },
  { slug: 'report', label: 'Report' },
];
