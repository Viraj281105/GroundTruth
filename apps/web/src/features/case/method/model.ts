import { describeMethod } from '../../../lib/method-descriptions';
import { formatHectares } from '../../../lib/formatters';
import type { CaseDetail, Evidence } from '../../../lib/types';

export interface MethodStep {
  method: string;
  title: string;
  summary: string[];
  formula: string[];
  caveat: string | null;
  /** Labels of the evidence items this method produced. */
  produces: string[];
  parameters: string | null;
  codeVersion: string | null;
}

export interface MethodStage {
  stage: string;
  steps: MethodStep[];
}

export interface SourceRow {
  source: string;
  uri: string | null;
  retrievedAt: string | null;
}

export interface SourceCount {
  source: string;
  count: number;
}

export interface StageSummary {
  stage: string;
  methods: number;
  items: number;
}

export interface MethodModel {
  /** Evidence items contributed per distinct source. */
  sourceCounts: SourceCount[];
  design: { label: string; value: string }[];
  stages: MethodStage[];
  sources: SourceRow[];
  assumptions: string[];
}

const STAGE_ORDER = ['ingestion', 'geospatial', 'matching', 'causal', 'uncertainty', 'external'];

/** Study design rows: only fields the API returned for this case. */
export function designRows(d: CaseDetail): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [
    { label: 'Standard', value: d.standard },
    { label: 'Registry id', value: d.registry_id ?? 'Not recorded' },
    { label: 'Ecosystem', value: d.ecosystem },
    { label: 'Outcome indicator', value: d.indicator },
    { label: 'Pre-project period', value: d.pre_period },
    { label: 'Project period', value: d.post_period },
    { label: 'Project area', value: formatHectares(d.area_ha) },
    { label: 'Donor search region', value: d.donor_search_region },
    { label: 'Configured candidate pool (not admitted donors)', value: String(d.donor_pool_size) },
  ];
  if (d.covariates.length > 0) rows.push({ label: 'Matching covariates', value: d.covariates.join(', ') });
  return rows;
}

function stageRank(stage: string): number {
  const i = STAGE_ORDER.indexOf(stage);
  return i === -1 ? STAGE_ORDER.length : i;
}

/** Groups evidence by pipeline stage and distinct method, so each method is explained once. */
export function buildMethodModel(detail: CaseDetail, items: Evidence[] | null, verdictCaveats: string[] = []): MethodModel {
  const byStage = new Map<string, Map<string, MethodStep>>();
  const sources = new Map<string, SourceRow>();
  const assumptions = new Set<string>(verdictCaveats);
  const sourceCounts = new Map<string, number>();

  for (const e of items ?? []) {
    const p = e.provenance;
    const methods = byStage.get(p.stage) ?? new Map<string, MethodStep>();
    let step = methods.get(p.method);
    if (!step) {
      const desc = describeMethod(p.method);
      step = {
        method: p.method,
        title: desc?.title ?? p.method,
        summary: desc?.summary ?? [],
        formula: desc?.formula ?? [],
        caveat: desc?.caveat ?? null,
        produces: [],
        parameters: p.parameters && Object.keys(p.parameters).length > 0 ? JSON.stringify(p.parameters, null, 2) : null,
        codeVersion: p.code_version,
      };
      if (desc?.caveat) assumptions.add(desc.caveat);
      methods.set(p.method, step);
    }
    step.produces.push(e.label);
    sourceCounts.set(p.source, (sourceCounts.get(p.source) ?? 0) + 1);
    byStage.set(p.stage, methods);
    const key = `${p.source}|${p.source_uri ?? ''}`;
    if (!sources.has(key)) sources.set(key, { source: p.source, uri: p.source_uri, retrievedAt: p.retrieved_at });
  }

  const stages = [...byStage.entries()]
    .sort((a, b) => stageRank(a[0]) - stageRank(b[0]))
    .map(([stage, m]) => ({ stage, steps: [...m.values()] }));
  const counts = [...sourceCounts.entries()].map(([source, count]) => ({ source, count })).sort((a, b) => b.count - a.count);
  return { sourceCounts: counts, design: designRows(detail), stages, sources: [...sources.values()], assumptions: [...assumptions] };
}

/** Per-stage method and evidence counts for the ladder, in pipeline order. */
export function stageSummary(stages: MethodStage[]): StageSummary[] {
  return stages.map((st) => ({ stage: st.stage, methods: st.steps.length, items: st.steps.reduce((n, s) => n + s.produces.length, 0) }));
}

/** Short label for a long source id: a URL's host, or the last two dotted segments. */
export function shortSource(source: string): string {
  if (/^https?:\/\//.test(source)) {
    try {
      return new URL(source).hostname;
    } catch {
      return source;
    }
  }
  return source.split('.').filter(Boolean).slice(-2).join('.') || source;
}
