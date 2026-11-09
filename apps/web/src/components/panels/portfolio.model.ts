import { dimensionView, type DimensionStatusView } from './dimension.model';
import type { PortfolioRow, PortfolioView } from './types';

export interface PortfolioRowModel {
  id: string;
  slug: string;
  name: string;
  accessLevel: string;
  level: number;
  levelName: string;
  simulated: boolean;
  degraded: boolean;
  degradedLabel: string | null;
  headline: { trajectory: DimensionStatusView; risk: DimensionStatusView; evidenceQuality: DimensionStatusView } | null;
  topRecommendation: string | null;
  verdict: string | null;
  confidence: string | null;
  /** Only ever present together with the reporting organization. */
  funding: { text: string; reportedBy: string } | null;
}

function toRow(r: PortfolioRow): PortfolioRowModel {
  const f = r.reported_funding;
  const funding = f && f.reported_by ? { text: `${new Intl.NumberFormat('en-US').format(f.amount)}${f.currency ? ` ${f.currency}` : ''}`, reportedBy: f.reported_by } : null;
  const degraded = r.degraded === true;
  const ds = r.dimension_statuses;
  return {
    id: r.project.id,
    slug: r.project.slug,
    name: r.project.name,
    accessLevel: r.access_level,
    level: r.assessment_level,
    levelName: r.level_name,
    simulated: r.data_mode === 'simulated',
    degraded,
    degradedLabel: degraded ? `Assessment unavailable${r.degraded_reason ? `: ${r.degraded_reason}` : ''}` : null,
    headline:
      degraded || !ds
        ? null
        : {
            trajectory: dimensionView({ status: ds.trajectory, status_kind: 'trend_status' }),
            risk: dimensionView({ status: ds.risk, status_kind: 'trend_status' }),
            evidenceQuality: dimensionView({ status: ds.evidence_quality, status_kind: 'quality_rating' }),
          },
    topRecommendation: r.top_recommendation?.text ?? null,
    verdict: r.attribution_verdict ?? null,
    confidence: r.evidence_confidence ?? null,
    funding,
  };
}

/** Real and simulated projects stay in separate lists. No totals or scores are computed. */
export function portfolioRows(p: PortfolioView): { real: PortfolioRowModel[]; simulated: PortfolioRowModel[] } {
  return { real: (p.projects ?? []).map(toRow), simulated: (p.simulated ?? []).map(toRow) };
}
