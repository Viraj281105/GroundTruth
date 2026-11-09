/** Client-side mirror of the server's boundary upload limits. The server stays authoritative. */
export const MAX_BOUNDARY_BYTES = 5 * 1024 * 1024;
export const BOUNDARY_EXTENSIONS = ['.geojson', '.json', '.kml'] as const;

/** Returns a message for the first problem found, or null when the file may be sent. */
export function validateBoundaryFile(file: File | null | undefined): string | null {
  if (!file) return 'Choose a boundary file (.geojson, .json or .kml).';
  const name = file.name.toLowerCase();
  if (!BOUNDARY_EXTENSIONS.some((e) => name.endsWith(e))) return 'The boundary must be a GeoJSON (.geojson, .json) or KML (.kml) file.';
  if (file.size === 0) return 'The boundary file is empty.';
  if (file.size > MAX_BOUNDARY_BYTES) return 'The boundary file is larger than 5 MB.';
  return null;
}

export const FIELD_LIMITS = { name: 200, country: 100, ecosystem: 100, intervention: 100, yearMin: 1970, yearMax: 2100 } as const;

export type ProjectFieldErrors = Partial<Record<'name' | 'country' | 'ecosystem' | 'intervention' | 'year' | 'file', string>>;

/** Treatment start year: an integer within the server's range. */
export function validateYear(raw: string): string | null {
  const t = raw.trim();
  if (!/^\d{4}$/.test(t)) return `Enter a four-digit year between ${FIELD_LIMITS.yearMin} and ${FIELD_LIMITS.yearMax}.`;
  const n = Number(t);
  return n < FIELD_LIMITS.yearMin || n > FIELD_LIMITS.yearMax ? `The year must be between ${FIELD_LIMITS.yearMin} and ${FIELD_LIMITS.yearMax}.` : null;
}

const text = (v: string, label: string, max: number): string | null => {
  const t = v.trim();
  if (!t) return `${label} is required.`;
  return t.length > max ? `${label} must be at most ${max} characters.` : null;
};

/** All client-side field checks; the server stays authoritative. */
export function validateProjectFields(v: { name: string; country: string; ecosystem: string; intervention: string; year: string; file: File | null }): ProjectFieldErrors {
  const out: ProjectFieldErrors = {};
  const set = <K extends keyof ProjectFieldErrors>(k: K, m: string | null) => {
    if (m) out[k] = m;
  };
  set('name', text(v.name, 'Project name', FIELD_LIMITS.name));
  set('country', text(v.country, 'Country', FIELD_LIMITS.country));
  set('ecosystem', text(v.ecosystem, 'Ecosystem', FIELD_LIMITS.ecosystem));
  set('intervention', text(v.intervention, 'Intervention', FIELD_LIMITS.intervention));
  set('year', validateYear(v.year));
  set('file', validateBoundaryFile(v.file));
  return out;
}
