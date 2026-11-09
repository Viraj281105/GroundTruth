import { isNum } from './format';
import type { ClimateView } from './types';

/** The flag is read from the SERVED `drought_classification` only; the panel never derives one from SPI. */
export function flagFromClass(cls: string | null | undefined): ClimateFlag {
  if (!cls) return 'none';
  if (cls.endsWith('_drought')) return 'drought';
  if (cls.endsWith('_wet')) return 'wet';
  return 'none';
}

export type ClimateFlag = 'drought' | 'wet' | 'none';
export interface ClimateRow {
  year: number;
  rainfallMm: number | null;
  spi12: number | null;
  flag: ClimateFlag;
  droughtClass: string;
  validMonths: number;
  complete: boolean;
  /** True when the year lies outside the observed window: shown as context only. */
  context: boolean;
}

/** Annual rows plus the missing months exactly as the payload lists them (sorted). Nothing is filled in. */
export function climateAnnual(
  c: Pick<ClimateView, 'years' | 'missing_months'>,
  observedWindow?: { from: number; to: number } | null,
): { rows: ClimateRow[]; missingMonths: string[] } {
  const rows = (c.years ?? [])
    .map((y): ClimateRow => {
      const spi = isNum(y.spi_12) ? y.spi_12 : null;
      return {
        year: y.year,
        rainfallMm: isNum(y.annual_rainfall_mm) ? y.annual_rainfall_mm : null,
        spi12: spi,
        flag: flagFromClass(y.drought_classification),
        droughtClass: y.drought_classification ?? '',
        validMonths: y.valid_months,
        complete: y.is_complete_year,
        context: !!observedWindow && (y.year < observedWindow.from || y.year > observedWindow.to),
      };
    })
    .sort((a, b) => a.year - b.year);
  return { rows, missingMonths: [...(c.missing_months ?? [])].sort() };
}
