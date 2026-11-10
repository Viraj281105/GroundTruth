/** The technical-dossier download, without React, so its outcomes can be tested. */

export type DossierOutcome = { ok: true; filename: string } | { ok: false; message: string };

export interface DossierDeps {
  apiBaseUrl: string;
  projectId: string;
  /** Human-readable stem for the saved file; the project's slug. Falls back to the id. */
  projectSlug?: string | null;
  fetch: typeof globalThis.fetch;
  save: (blob: Blob, filename: string) => void;
  /**
   * Called after the file is saved. Creating a dossier seals it in the audit ledger, so the page
   * must reload what it shows about the ledger: without this the "Report sealed" record stayed
   * invisible until the user reloaded the page by hand.
   */
  onSealed: () => void;
}

export function dossierFilename(projectSlug: string | null | undefined, projectId: string): string {
  const stem = (projectSlug ?? '').replace(/[^a-z0-9-]+/gi, '-').replace(/^-+|-+$/g, '');
  return `${stem || projectId}-dossier.zip`;
}

export async function downloadDossier(deps: DossierDeps): Promise<DossierOutcome> {
  let res: Response;
  try {
    res = await deps.fetch(`${deps.apiBaseUrl}/projects/${encodeURIComponent(deps.projectId)}/export/dossier`, { credentials: 'include' });
  } catch {
    return { ok: false, message: 'The GroundTruth API could not be reached.' };
  }
  if (!res.ok) {
    return { ok: false, message: res.status === 403 ? 'Your access level does not allow the dossier.' : `The dossier could not be created (HTTP ${res.status}).` };
  }
  const filename = dossierFilename(deps.projectSlug, deps.projectId);
  deps.save(await res.blob(), filename);
  deps.onSealed();
  return { ok: true, filename };
}
