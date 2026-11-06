import type { HealthResponse } from '../../lib/types';
import { STATUS_COPY as C } from './copy';

export interface CapabilityRow {
  key: string;
  label: string;
  implemented: boolean;
}

const humanise = (key: string) => {
  const s = key.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
};

/** Capabilities exactly as the API reports them, plus the two top-level flags. Nothing is added. */
export function capabilityRows(health: HealthResponse): CapabilityRow[] {
  const reported = Object.entries(health.engine_capabilities ?? {}).map(([key, implemented]) => ({
    key,
    label: C.capabilityLabels[key] ?? humanise(key),
    implemented: implemented === true,
  }));
  return [
    ...reported,
    { key: 'earth_observation', label: C.capabilityLabels.earth_observation, implemented: health.earth_observation_implemented },
    { key: 'genai_narration', label: C.capabilityLabels.genai_narration, implemented: health.genai_narration_implemented },
  ];
}

/** The health client returns status 'unreachable' when the endpoint could not be read. */
export const isUnreachable = (health: HealthResponse) => health.status === 'unreachable';
