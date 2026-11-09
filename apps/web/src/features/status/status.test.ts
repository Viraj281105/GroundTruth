import { describe, expect, it } from 'vitest';
import { capabilityRows, isUnreachable } from './status';
import { STATUS_COPY } from './copy';
import type { HealthResponse } from '../../lib/types';

const health = (over: Partial<HealthResponse>): HealthResponse => ({
  status: 'ok',
  version: '1',
  engine_version: '2',
  contract_version: '3',
  earth_observation_implemented: false,
  genai_narration_implemented: false,
  cases_available: 3,
  engine_capabilities: {},
  evidence_sources_total: 0,
  evidence_sources_operational: 0,
  evidence_sources_usable_for_production: 0,
  ...over,
});

describe('capabilityRows', () => {
  it('reports exactly what the API returned and the two flags', () => {
    const rows = capabilityRows(health({ engine_capabilities: { synthetic_control: true, biomass_carbon_conversion: false } }));
    expect(rows.map((r) => [r.key, r.implemented])).toEqual([
      ['synthetic_control', true],
      ['biomass_carbon_conversion', false],
      ['earth_observation', false],
      ['genai_narration', false],
    ]);
  });
  it('detects an unreachable backend', () => {
    expect(isUnreachable(health({ status: 'unreachable' }))).toBe(true);
    expect(isUnreachable(health({}))).toBe(false);
  });
  it('copy avoids prohibited wording', () => {
    expect(JSON.stringify(STATUS_COPY)).not.toMatch(/fraud|scam|illegal|criminal|guilty|definitive|proves? that/i);
  });
});
