import type { Schemas } from '../../lib/api-client';
import type { ChipTone } from '../../components/ds/Chip';
import { apiErrorMessage } from './model';

export type IngestionList = Schemas['IngestionListView'];
export type IngestionView = Schemas['IngestionView'];
export type IngestionLimits = Schemas['IngestionLimitsView'];
export type IngestionRequest = Schemas['IngestionRequest'];
export type IngestionResult = Schemas['IngestionResultView'];
export type IngestionYear = Schemas['IngestionYearView'];
export type IngestionParams = Schemas['IngestionParamsView'];
export type IngestionStatus = IngestionView['status'];
export type YearState = IngestionYear['state'];

/* ---------------------------------------------------------------- statuses */

export const isActive = (status: IngestionStatus): boolean => status === 'queued' || status === 'running';
export const isFinal = (status: IngestionStatus): boolean => !isActive(status);
/** Requests whose details (per-year table, provenance) are worth showing. */
export const hasDetails = (status: IngestionStatus): boolean => status === 'succeeded' || status === 'partial' || status === 'failed';

export interface StatusInfo {
  label: string;
  tone: ChipTone;
  explanation: string;
}

export function statusInfo(status: IngestionStatus): StatusInfo {
  switch (status) {
    case 'queued':
      return { label: 'Waiting', tone: 'neutral', explanation: 'Waiting for the GroundTruth background worker to pick this up. No satellite data has been read yet.' };
    case 'running':
      return { label: 'Running', tone: 'accent', explanation: 'The worker is reading satellite scenes now. Nothing is stored until it finishes.' };
    case 'succeeded':
      return { label: 'Finished', tone: 'accent', explanation: 'Finished. Values were stored for the requested years. Check the table below for each year.' };
    case 'partial':
      return {
        label: 'INCOMPLETE',
        tone: 'caution',
        explanation: 'INCOMPLETE. Some years have no value, or a value for only part of the project area. Empty years are left empty, never estimated.',
      };
    case 'failed':
      return { label: 'Failed', tone: 'danger', explanation: 'This request did not finish, so no new satellite values were stored.' };
    case 'cancelled':
      return { label: 'Cancelled', tone: 'neutral', explanation: 'This request was cancelled before it started. Nothing was collected.' };
  }
}

export function yearStateInfo(state: YearState): { label: string; tone: ChipTone } {
  switch (state) {
    case 'observed':
      return { label: 'Usable value', tone: 'accent' };
    case 'partial_coverage':
      return { label: 'Part of the area only', tone: 'caution' };
    case 'no_usable_data':
      return { label: 'No value (left empty)', tone: 'danger' };
  }
}

/** Plain text for a failed request: what the server said, then its code. Nothing is invented. */
export function failureMessage(r: Pick<IngestionView, 'status_detail' | 'error_code'>): string {
  const parts = [r.status_detail?.trim() || 'The request did not finish.'];
  if (r.error_code) parts.push(`(Error code: ${r.error_code}.)`);
  return parts.join(' ');
}

/* ------------------------------------------------------------- formatting */

export function formatElapsed(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return 'unknown time';
  if (seconds < 60) return 'under a minute';
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  if (h < 48) return rest ? `${h} h ${rest} min` : `${h} h`;
  return `${Math.floor(h / 24)} days`;
}

/** Fixed UTC text so server and browser render the same string. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export const formatValue = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(3));
export const formatPct = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) ? '—' : `${v.toFixed(1)}%`);
export const shortSha = (h: string | null | undefined, keep = 8): string => (h ? h.slice(0, keep) : '—');

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function formatMonthDay(md: string): string {
  const m = /^(\d{2})-(\d{2})$/.exec(md);
  if (!m) return md;
  const mi = Number(m[1]) - 1;
  return mi >= 0 && mi < 12 ? `${Number(m[2])} ${MONTHS[mi]}` : md;
}

export const yearRange = (a: number, b: number): string => (a === b ? String(a) : `${a}–${b}`);

export function paramsSummary(p: IngestionParams): string {
  const inds = (p.indicators ?? []).map((i) => i.toUpperCase()).join(', ');
  return [
    `Years ${yearRange(p.start_year, p.end_year)}`,
    `season ${formatMonthDay(p.window_start)} to ${formatMonthDay(p.window_end)}`,
    `scenes up to ${p.max_cloud_cover}% cloudy`,
    `${p.resolution_m} m grid`,
    `up to ${p.max_scenes_per_year} ${p.max_scenes_per_year === 1 ? 'scene' : 'scenes'} per year`,
    inds || null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/* ----------------------------------------------------------------- result */

export const VEGETATION_NOTE =
  'These numbers measure how green the vegetation looks from space. They do not measure tree survival, carbon or biodiversity.';
export const CHANGE_NOTE = 'A change over time is something that was observed. It does not show that the project caused it.';

const joinYears = (ys: number[]): string => [...ys].sort((a, b) => a - b).join(', ');

/** Plain sentences describing a result. A year with no value is said to be empty and is never estimated. */
export function summariseResult(result: Pick<IngestionResult, 'years' | 'years_requested'> | null | undefined): string[] {
  if (!result) return [];
  const years = result.years ?? [];
  const requested = result.years_requested ?? [];
  const total = requested.length || years.length;
  if (total === 0) return ['No years were reported for this request.'];
  const usable = years.filter((y) => y.state === 'observed').map((y) => y.year);
  const partial = years.filter((y) => y.state === 'partial_coverage').map((y) => y.year);
  const empty = years.filter((y) => y.state === 'no_usable_data').map((y) => y.year);
  const reported = new Set(years.map((y) => y.year));
  const noValue = [...empty, ...requested.filter((y) => !reported.has(y))];

  const out = [`${usable.length} of ${total} requested ${total === 1 ? 'year has' : 'years have'} a usable value${usable.length ? ` (${joinYears(usable)})` : ''}.`];
  if (partial.length) {
    out.push(`${joinYears(partial)} ${partial.length === 1 ? 'has' : 'have'} a value for only part of the project area, so treat ${partial.length === 1 ? 'it' : 'them'} with caution.`);
  }
  if (noValue.length) {
    out.push(`${joinYears(noValue)} ${noValue.length === 1 ? 'has' : 'have'} no value. ${noValue.length === 1 ? 'It is' : 'They are'} left empty, not estimated.`);
  }
  return out;
}

/** Indicator columns for the details table: NDVI first, then any others the API returned or requested. */
export function valueColumns(years: readonly IngestionYear[], requested: readonly string[]): string[] {
  const seen = new Set<string>(['ndvi']);
  for (const y of years) for (const k of Object.keys(y.values ?? {})) seen.add(k);
  for (const r of requested) seen.add(r);
  const order = ['ndvi', 'evi', 'ndmi', 'nbr'];
  return [...seen].sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99) || a.localeCompare(b));
}

/* ------------------------------------------------------------------- form */

export interface IndicatorInfo {
  id: string;
  label: string;
  description: string;
  always?: boolean;
}

export const INDICATOR_INFO: readonly IndicatorInfo[] = [
  { id: 'ndvi', label: 'NDVI (greenness)', description: 'How green and leafy the vegetation looks. Always included.', always: true },
  { id: 'evi', label: 'EVI (greenness, dense canopy)', description: 'Like NDVI, but less likely to level off over thick vegetation.' },
  { id: 'ndmi', label: 'NDMI (moisture)', description: 'How much water the leaves seem to hold. Dry spells show as lower values.' },
  { id: 'nbr', label: 'NBR (burn or stress)', description: 'Helps show burned or badly stressed vegetation.' },
];

export interface SeasonPreset {
  id: 'june' | 'janmar' | 'custom';
  label: string;
  start: string;
  end: string;
}

export const SEASON_PRESETS: readonly SeasonPreset[] = [
  { id: 'june', label: 'June (dry season in southern Africa)', start: '06-01', end: '06-30' },
  { id: 'janmar', label: 'January to March (rainy season in southern Africa)', start: '01-01', end: '03-31' },
  { id: 'custom', label: 'Choose my own dates', start: '06-01', end: '06-30' },
];

export const SEASON_HINT =
  'Satellites cannot see through cloud. Cloudy seasons, such as the rainy season, leave fewer usable scenes, and some years may come back empty.';

export interface ObservationForm {
  startYear: string;
  endYear: string;
  season: SeasonPreset['id'];
  windowStart: string;
  windowEnd: string;
  maxCloud: string;
  resolution: string;
  scenesPerYear: string;
  indicators: string[];
}

export function defaultForm(limits: IngestionLimits): ObservationForm {
  const span = Math.max(1, Math.min(6, limits.max_years));
  const startYear = Math.max(limits.first_year, limits.last_year - (span - 1));
  const years = limits.last_year - startYear + 1;
  const scenes = Math.max(1, Math.min(3, Math.floor(limits.max_total_scenes / Math.max(1, years))));
  const resolution = Math.min(limits.max_resolution_m, Math.max(limits.min_resolution_m, 100));
  const defaults = limits.default_indicators ?? [];
  return {
    startYear: String(startYear),
    endYear: String(limits.last_year),
    season: 'june',
    windowStart: '06-01',
    windowEnd: '06-30',
    maxCloud: '25',
    resolution: String(resolution),
    scenesPerYear: String(scenes),
    indicators: defaults.includes('ndvi') ? defaults : ['ndvi', ...defaults],
  };
}

export type FormField = 'startYear' | 'endYear' | 'years' | 'windowStart' | 'windowEnd' | 'maxCloud' | 'resolution' | 'scenesPerYear' | 'indicators';
export type FormErrors = Partial<Record<FormField, string>>;

const INT = /^-?\d+$/;
const toInt = (s: string): number | null => (INT.test(s.trim()) ? Number(s.trim()) : null);

/** MM-DD that names a real calendar day (29 Feb allowed). */
export function isMonthDay(s: string): boolean {
  const m = /^(\d{2})-(\d{2})$/.exec(s.trim());
  if (!m) return false;
  const mo = Number(m[1]);
  const d = Number(m[2]);
  if (mo < 1 || mo > 12 || d < 1) return false;
  return d <= new Date(Date.UTC(2000, mo, 0)).getUTCDate();
}

export interface Validation {
  errors: FormErrors;
  request: IngestionRequest | null;
}

/** Mirrors the server limits so most mistakes are caught before sending. The server still re-validates everything. */
export function validateForm(f: ObservationForm, limits: IngestionLimits): Validation {
  const errors: FormErrors = {};
  const start = toInt(f.startYear);
  const end = toInt(f.endYear);
  if (start === null || start < limits.first_year || start > limits.last_year) errors.startYear = `Choose a first year between ${limits.first_year} and ${limits.last_year}.`;
  if (end === null || end < limits.first_year || end > limits.last_year) errors.endYear = `Choose a last year between ${limits.first_year} and ${limits.last_year}.`;
  let years = 0;
  if (start !== null && end !== null && !errors.startYear && !errors.endYear) {
    if (end < start) errors.endYear = 'The last year cannot be before the first year.';
    else {
      years = end - start + 1;
      if (years > limits.max_years) errors.years = `You can ask for at most ${limits.max_years} years at a time. You chose ${years}.`;
    }
  }

  const ws = f.windowStart.trim();
  const we = f.windowEnd.trim();
  if (!isMonthDay(ws)) errors.windowStart = 'Write the season start as month-day, for example 06-01.';
  if (!isMonthDay(we)) errors.windowEnd = 'Write the season end as month-day, for example 06-30.';
  if (!errors.windowStart && !errors.windowEnd && ws > we) errors.windowEnd = 'The season must end after it starts, within the same calendar year.';

  const cloud = f.maxCloud.trim() === '' ? NaN : Number(f.maxCloud);
  if (!Number.isFinite(cloud) || cloud < 0 || cloud > 80) errors.maxCloud = 'Choose a cloud limit between 0 and 80 percent.';

  const res = toInt(f.resolution);
  if (res === null || res < limits.min_resolution_m || res > limits.max_resolution_m) errors.resolution = `Choose a grid size between ${limits.min_resolution_m} and ${limits.max_resolution_m} metres.`;

  const per = toInt(f.scenesPerYear);
  if (per === null || per < 1) errors.scenesPerYear = 'Ask for at least 1 scene per year.';
  else if (years > 0 && per * years > limits.max_total_scenes) {
    errors.scenesPerYear = `${per} scenes a year over ${years} years is ${per * years} scenes. The limit is ${limits.max_total_scenes} in total. Ask for fewer scenes or fewer years.`;
  }

  const allowed = new Set(limits.indicators);
  const indicators = [...new Set(['ndvi', ...f.indicators])].filter((i) => allowed.has(i));
  if (indicators.length === 0) errors.indicators = 'Choose at least one indicator.';

  if (Object.keys(errors).length > 0) return { errors, request: null };
  return {
    errors,
    request: {
      start_year: start as number,
      end_year: end as number,
      window_start: ws,
      window_end: we,
      max_cloud_cover: cloud,
      indicators,
      resolution_m: res as number,
      max_scenes_per_year: per as number,
    },
  };
}

/* ----------------------------------------------------------------- errors */

export interface IngestionError {
  message: string;
  hint: string | null;
}

/** Reads the API's {detail:{code,message,hint}}; otherwise falls back to a plain sentence for the status. */
export function ingestionError(status: number, body: unknown): IngestionError {
  const d = (body as { detail?: unknown } | null | undefined)?.detail;
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const o = d as { message?: unknown; hint?: unknown };
    if (typeof o.message === 'string' && o.message) return { message: o.message, hint: typeof o.hint === 'string' && o.hint ? o.hint : null };
  }
  switch (status) {
    case 409:
      return { message: 'A satellite request for this project is already waiting or running.', hint: 'Wait for it to finish, then ask again.' };
    case 503:
      return { message: 'Satellite requests are switched off on this server.', hint: null };
    case 403:
      return { message: 'Your role does not allow requesting satellite data for this project.', hint: null };
    default:
      return { message: apiErrorMessage(status, typeof d === 'string' ? d : null), hint: null };
  }
}
