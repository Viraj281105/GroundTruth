/** Pure helpers that turn raw audit rows into plain-language labels. The raw values stay available as title text. */

export const ACTION_LABELS: Record<string, string> = {
  'auth.login': 'Signed in',
  'auth.login_failed': 'Sign-in failed',
  'auth.logout': 'Signed out',
  'auth.register': 'Account created',
  'auth.password_change': 'Password changed',
  'org.create': 'Organization created',
  'org.member_add': 'Member added',
  'org.member_remove': 'Member removed',
  'org.member_role': 'Member role changed',
  'org.switch': 'Switched organization',
  'project.create': 'Project created',
  'project.update': 'Project updated',
  'project.grant': 'Project shared',
  'project.revoke': 'Project sharing removed',
  'run.start': 'Analysis started',
  'run.cancel': 'Analysis cancelled',
  'export.download': 'Report downloaded',
  'authz.denied': 'Access denied',
};

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** "project.create" becomes "Project created". Unknown actions fall back to a readable form of the raw name. */
export function humanizeAction(action: string): string {
  const known = ACTION_LABELS[action];
  if (known) return known;
  return sentence(action.replace(/[._]+/g, ' ').trim()) || 'Unknown action';
}

const OUTCOME_LABELS: Record<string, string> = { success: 'Succeeded', denied: 'Denied', failure: 'Failed', error: 'Failed' };
export const humanizeOutcome = (outcome: string): string => OUTCOME_LABELS[outcome] ?? sentence(outcome);

/** The person behind an event: their email when the API names them, else a short id marked as unknown. */
export function actorLabel(event: { actor_user_id?: string | null; actor_email?: string | null }): { text: string; known: boolean } {
  if (event.actor_email) return { text: event.actor_email, known: true };
  if (event.actor_user_id) return { text: `Unknown user (${event.actor_user_id.slice(0, 8)})`, known: false };
  return { text: 'System', known: false };
}

/** A short resource label: type plus an abbreviated id when the id is a UUID-sized token. */
export function resourceLabel(type: string, id?: string | null): string {
  const base = sentence(type.replace(/[._]+/g, ' '));
  if (!id) return base;
  return `${base} ${id.length > 12 ? `${id.slice(0, 8)}…` : id}`;
}

export function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** Collapses consecutive identical events (same action, actor, resource, outcome) into one row with a count. */
export interface AuditRow<T> {
  event: T;
  count: number;
}
export function collapseRuns<T extends { action: string; actor_user_id?: string | null; resource_type: string; resource_id?: string | null; outcome: string }>(events: T[]): AuditRow<T>[] {
  const out: AuditRow<T>[] = [];
  for (const e of events) {
    const prev = out[out.length - 1];
    const same =
      prev && prev.event.action === e.action && prev.event.actor_user_id === e.actor_user_id && prev.event.resource_type === e.resource_type && prev.event.resource_id === e.resource_id && prev.event.outcome === e.outcome;
    if (same) prev.count += 1;
    else out.push({ event: e, count: 1 });
  }
  return out;
}
