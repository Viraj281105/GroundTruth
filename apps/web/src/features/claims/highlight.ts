/** Pure span highlighting: split text into plain and claim segments. */

export interface TextSpan {
  start: number;
  end: number;
}

export interface Segment {
  text: string;
  /** Index into the input spans, or null for unhighlighted text. */
  claim: number | null;
}

/**
 * Split `text` at the given spans. Invalid spans (out of range, empty) and spans that
 * overlap an earlier one are skipped, so the segments always concatenate back to `text`.
 */
export function segmentText(text: string, spans: readonly TextSpan[]): Segment[] {
  const order = spans
    .map((s, i) => ({ ...s, i }))
    .filter((s) => Number.isInteger(s.start) && Number.isInteger(s.end) && s.start >= 0 && s.end <= text.length && s.end > s.start)
    .sort((a, b) => a.start - b.start || a.i - b.i);
  const out: Segment[] = [];
  let pos = 0;
  for (const s of order) {
    if (s.start < pos) continue;
    if (s.start > pos) out.push({ text: text.slice(pos, s.start), claim: null });
    out.push({ text: text.slice(s.start, s.end), claim: s.i });
    pos = s.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), claim: null });
  return out;
}
