import { describe, expect, it, vi } from 'vitest';
import { dossierFilename, downloadDossier } from '../src/features/projects/dossier-download';
import { selectedSealingRecord } from '../src/features/projects/ledger.model';

const deps = (response: Response | Error) => {
  const save = vi.fn();
  const onSealed = vi.fn();
  const fetch = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response;
  }) as unknown as typeof globalThis.fetch;
  return { save, onSealed, fetch, apiBaseUrl: 'http://api.test', projectId: 'ac747bdd-c5e3', projectSlug: 'sahyadri-foothills-restoration' };
};

/**
 * Found in the user audit: after "Download dossier" the ledger on the same page still showed one
 * record and no "Report sealed" row, although the download had sealed the report. The page was
 * never told to reload. The saved file was also named after the project's UUID.
 */
describe('downloadDossier', () => {
  it('saves the file under the project slug and tells the page the ledger changed', async () => {
    const d = deps(new Response(new Blob(['zip']), { status: 200 }));
    const outcome = await downloadDossier(d);
    expect(outcome).toEqual({ ok: true, filename: 'sahyadri-foothills-restoration-dossier.zip' });
    expect(d.fetch).toHaveBeenCalledWith('http://api.test/projects/ac747bdd-c5e3/export/dossier', { credentials: 'include' });
    expect(d.save).toHaveBeenCalledTimes(1);
    expect(d.save.mock.calls[0][1]).toBe('sahyadri-foothills-restoration-dossier.zip');
    expect(d.onSealed).toHaveBeenCalledTimes(1);
  });

  it('says so when the access level does not allow it, and reloads nothing', async () => {
    const d = deps(new Response(null, { status: 403 }));
    expect(await downloadDossier(d)).toEqual({ ok: false, message: 'Your access level does not allow the dossier.' });
    expect(d.save).not.toHaveBeenCalled();
    expect(d.onSealed).not.toHaveBeenCalled();
  });

  it('reports a server failure with its status and saves nothing', async () => {
    const d = deps(new Response(null, { status: 500 }));
    expect(await downloadDossier(d)).toEqual({ ok: false, message: 'The dossier could not be created (HTTP 500).' });
    expect(d.save).not.toHaveBeenCalled();
    expect(d.onSealed).not.toHaveBeenCalled();
  });

  it('reports an unreachable API', async () => {
    const d = deps(new TypeError('network'));
    expect(await downloadDossier(d)).toEqual({ ok: false, message: 'The GroundTruth API could not be reached.' });
    expect(d.onSealed).not.toHaveBeenCalled();
  });
});

describe('dossierFilename', () => {
  it('uses the slug, and the id only when there is no usable slug', () => {
    expect(dossierFilename('kariba-redd', 'p1')).toBe('kariba-redd-dossier.zip');
    expect(dossierFilename(null, 'p1')).toBe('p1-dossier.zip');
    expect(dossierFilename('../..', 'p1')).toBe('p1-dossier.zip');
  });
});

describe('selectedSealingRecord', () => {
  it('is empty while nothing is sealed, then follows the newest record', () => {
    expect(selectedSealingRecord(null, [])).toBe('');
    // First download: the list goes from empty to one record without the form being remounted.
    expect(selectedSealingRecord(null, ['AUDIT-a'])).toBe('AUDIT-a');
    expect(selectedSealingRecord(null, ['AUDIT-a', 'AUDIT-b'])).toBe('AUDIT-b');
  });

  it('keeps an explicit choice while that record exists', () => {
    expect(selectedSealingRecord('AUDIT-a', ['AUDIT-a', 'AUDIT-b'])).toBe('AUDIT-a');
    expect(selectedSealingRecord('AUDIT-gone', ['AUDIT-a', 'AUDIT-b'])).toBe('AUDIT-b');
  });
});
