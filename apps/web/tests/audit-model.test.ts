import { describe, expect, it } from 'vitest';
import { actorLabel, collapseRuns, formatWhen, humanizeAction, resourceLabel } from '../src/features/settings/audit-model';

describe('audit log labels', () => {
  it('humanises known and unknown actions', () => {
    expect(humanizeAction('project.create')).toBe('Project created');
    expect(humanizeAction('export.download')).toBe('Report downloaded');
    expect(humanizeAction('org.switch')).toBe('Switched organization');
    expect(humanizeAction('thing.did_something')).toBe('Thing did something');
  });

  it('shows the email when the API names the actor, else a short id marked unknown', () => {
    expect(actorLabel({ actor_user_id: 'u1', actor_email: 'a@x.org' })).toEqual({ text: 'a@x.org', known: true });
    expect(actorLabel({ actor_user_id: '123e4567-e89b-12d3-a456-426614174000', actor_email: null })).toEqual({ text: 'Unknown user (123e4567)', known: false });
    expect(actorLabel({ actor_user_id: null })).toEqual({ text: 'System', known: false });
  });

  it('shortens long resource ids and formats time', () => {
    expect(resourceLabel('project', '123e4567-e89b-12d3-a456-426614174000')).toBe('Project 123e4567…');
    expect(resourceLabel('organization')).toBe('Organization');
    expect(formatWhen('2026-01-02T03:04:05Z')).toBe('2026-01-02 03:04 UTC');
    expect(formatWhen('nonsense')).toBe('nonsense');
  });

  it('collapses consecutive identical events into one counted row', () => {
    const ev = (id: string, action: string) => ({ id, action, actor_user_id: 'u', resource_type: 'organization', resource_id: 'o', outcome: 'success' });
    const rows = collapseRuns([ev('1', 'org.switch'), ev('2', 'org.switch'), ev('3', 'org.switch'), ev('4', 'project.create'), ev('5', 'org.switch')]);
    expect(rows.map((r) => r.count)).toEqual([3, 1, 1]);
    expect(rows[0].event.id).toBe('1');
  });
});
