import type { AccessLevel, EvidenceInventoryView } from './types';

export interface InventorySummaryRow {
  indicator: string;
  status: 'available' | 'unavailable';
  reason: string | null;
  nRecords: number;
  years: number[];
  sensors: string[];
  source: string | null;
  dataOrigin: string | null;
  states: Record<string, number>;
}
export interface InventoryItemRow {
  indicator: string;
  year: number;
  nScenes: number;
  sceneIds: string[] | null;
  scenesSha256: string | null;
}

/**
 * Summary rows always; item rows only when the payload carries them. Checksum and scene-id columns
 * are shown only when the payload has the data AND the caller is above `view`: redaction removes
 * fields, so absence is the signal, never a placeholder.
 */
export function inventoryRows(e: EvidenceInventoryView, level: AccessLevel | string) {
  const summary: InventorySummaryRow[] = (e.indicators ?? []).map((i) => ({
    indicator: i.indicator,
    status: i.status,
    reason: i.reason ?? null,
    nRecords: i.n_records ?? 0,
    years: i.years ?? [],
    sensors: i.sensors ?? [],
    source: i.source ?? null,
    dataOrigin: i.data_origin ?? null,
    states: i.states ?? {},
  }));
  const higher = level !== 'view';
  const raw = higher && Array.isArray(e.items) ? e.items : [];
  const items: InventoryItemRow[] = raw.map((i) => ({
    indicator: i.indicator,
    year: i.year,
    nScenes: i.n_scenes,
    sceneIds: Array.isArray(i.scene_ids) ? i.scene_ids : null,
    scenesSha256: i.scenes_sha256 ?? null,
  }));
  return {
    summary,
    items,
    showSceneIds: items.some((i) => i.sceneIds !== null),
    showChecksum: items.some((i) => i.scenesSha256 !== null),
    boundarySha256: higher ? (e.boundary_sha256 ?? null) : null,
  };
}
