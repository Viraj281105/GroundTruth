import type { Schemas } from '../../lib/api-client';
import type { ClaimSummary } from '../../features/assessments/model';

type Project = Schemas['ProjectView'];
type Inventory = Schemas['EvidenceInventoryView'];
type Assessment = Schemas['AssessmentView'];
type Ledger = Schemas['LedgerView'];
type IngestionStatus = Schemas['IngestionView']['status'];

/**
 * done        - the data shows it happened
 * in_progress - a request is under way (for example a satellite data request waiting or running)
 * current     - the first step still to do (the suggested next action)
 * pending     - still to do, after the current one
 * blocked     - something that exists is failing (for example a ledger check)
 * unavailable - cannot be done for this project (no boundary, no ingestion path)
 * unknown     - the status could not be read; nothing is asserted
 */
export type StepStatus = 'done' | 'in_progress' | 'current' | 'pending' | 'blocked' | 'unavailable' | 'unknown';

export interface LifecycleStep {
  id: number;
  label: string;
  shortLabel: string;
  /** A real project tab, or null for the project list. */
  segment: string | null;
  status: StepStatus;
  /** One plain sentence describing what the data says, never what is assumed. */
  description: string;
}

export interface LifecycleInput {
  project: Pick<Project, 'boundary_sha256'>;
  inventory: Inventory | null;
  assessment: Pick<Assessment, 'level' | 'level_name'> | null;
  claims: ClaimSummary | null;
  /** `records` lets the stepper tell a sealed report from other ledger entries (such as an observation ingestion). */
  ledger: (Pick<Ledger, 'status' | 'record_count' | 'message'> & { records?: { record_kind: string }[] }) | null;
  /** Satellite data requests. Omitted or null when they could not be read; nothing is then asserted about them. */
  ingestions?: { active?: boolean; ingestions: { status: IngestionStatus }[] } | null;
}

export const STATUS_LABEL: Record<StepStatus, string> = {
  done: 'Done',
  in_progress: 'In progress',
  current: 'Next',
  pending: 'Not done yet',
  blocked: 'Blocked',
  unavailable: 'Not available',
  unknown: 'Could not be checked',
};

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/**
 * Eight steps, each mapped to the page where it can be done or checked, each with a status read from real
 * data. A step is "done" only when the API shows it. Pure: no I/O, no defaults.
 */
export function lifecycleSteps(i: LifecycleInput): LifecycleStep[] {
  const hasBoundary = Boolean(i.project.boundary_sha256);
  const inv = i.inventory;
  const steps: Omit<LifecycleStep, 'id'>[] = [];

  steps.push({ label: 'Project created', shortLabel: 'Created', segment: null, status: 'done', description: 'The project is registered in your organization.' });

  steps.push(
    hasBoundary
      ? { label: 'Boundary', shortLabel: 'Boundary', segment: 'overview', status: 'done', description: 'A project boundary is uploaded and checksummed.' }
      : {
          label: 'Boundary',
          shortLabel: 'Boundary',
          segment: 'overview',
          status: 'unavailable',
          description: 'No boundary was uploaded, so there is no map and no satellite data for this project.',
        },
  );

  if (!inv) {
    steps.push({ label: 'Documents', shortLabel: 'Documents', segment: 'evidence', status: 'unknown', description: 'The document count could not be read.' });
  } else if (inv.documents_count > 0) {
    steps.push({
      label: 'Documents',
      shortLabel: 'Documents',
      segment: 'evidence',
      status: 'done',
      description: `${plural(inv.documents_count, 'document')} uploaded. Stored and checksummed; not evidence of any claim until checked.`,
    });
  } else {
    steps.push({ label: 'Documents', shortLabel: 'Documents', segment: 'evidence', status: 'pending', description: 'No documents uploaded yet.' });
  }

  if (!inv) {
    steps.push({ label: 'Satellite data', shortLabel: 'Satellite', segment: 'observation', status: 'unknown', description: 'Stored observations could not be checked.' });
  } else {
    const stored = (inv.indicators ?? []).filter((x) => x.status === 'available');
    if (stored.length > 0) {
      steps.push({
        label: 'Satellite data',
        shortLabel: 'Satellite',
        segment: 'observation',
        status: 'done',
        description: `Stored observations exist for ${stored.map((x) => x.indicator.toUpperCase()).join(', ')}.`,
      });
    } else if (i.ingestions && (i.ingestions.active || i.ingestions.ingestions.some((r) => r.status === 'queued' || r.status === 'running'))) {
      steps.push({
        label: 'Satellite data',
        shortLabel: 'Satellite',
        segment: 'observation',
        status: 'in_progress',
        description: 'A satellite data request is waiting or running. Nothing is stored until it finishes.',
      });
    } else if (!hasBoundary || inv.observation_ingestion?.available === false) {
      steps.push({
        label: 'Satellite data',
        shortLabel: 'Satellite',
        segment: 'observation',
        status: 'unavailable',
        description: inv.observation_ingestion?.message || 'No satellite observations are stored and none can be added to this project here.',
      });
    } else {
      const last = i.ingestions?.ingestions[0]?.status;
      steps.push({
        label: 'Satellite data',
        shortLabel: 'Satellite',
        segment: 'observation',
        status: 'pending',
        description:
          last === 'failed' || last === 'partial'
            ? 'Request satellite data. The last request left no usable stored values, so nothing is stored yet.'
            : 'Request satellite data. No satellite observations are stored yet.',
      });
    }
  }

  if (!inv) {
    steps.push({ label: 'Climate record', shortLabel: 'Climate', segment: 'climate', status: 'unknown', description: 'The climate record could not be checked.' });
  } else if (inv.climate_status === 'available') {
    steps.push({ label: 'Climate record', shortLabel: 'Climate', segment: 'climate', status: 'done', description: 'A climate record is stored for this project.' });
  } else {
    steps.push({
      label: 'Climate record',
      shortLabel: 'Climate',
      segment: 'climate',
      status: hasBoundary ? 'pending' : 'unavailable',
      description: inv.climate_reason || 'No climate record is stored.',
    });
  }

  if (!i.assessment) {
    steps.push({ label: 'Assessment', shortLabel: 'Assessment', segment: 'overview', status: 'unknown', description: 'The assessment could not be read.' });
  } else {
    const lv = i.assessment.level;
    steps.push({
      label: 'Assessment',
      shortLabel: 'Assessment',
      segment: 'overview',
      status: lv >= 1 ? 'done' : 'pending',
      description: `Level ${lv} · ${i.assessment.level_name}. The level is set by the server from the evidence available.`,
    });
  }

  if (!i.claims) {
    steps.push({ label: 'Claims', shortLabel: 'Claims', segment: 'verification', status: 'unknown', description: 'Claims could not be read.' });
  } else if (i.claims.hasClaims) {
    steps.push({
      label: 'Claims',
      shortLabel: 'Claims',
      segment: 'verification',
      status: 'done',
      description: `${plural(i.claims.total, 'claim')} recorded: ${i.claims.supported} supported, ${i.claims.contradicted} contradicted, ${i.claims.unverified} unverified.`,
    });
  } else {
    steps.push({ label: 'Claims', shortLabel: 'Claims', segment: 'verification', status: 'pending', description: 'No claims recorded yet.' });
  }

  if (!i.ledger) {
    steps.push({ label: 'Reports & ledger', shortLabel: 'Reports', segment: 'reports', status: 'unknown', description: 'The audit ledger could not be read.' });
  } else if (i.ledger.status === 'verified') {
    // A verified ledger is not a finished report: observation ingestions are recorded in it too.
    const sealed = (i.ledger.records ?? []).filter((r) => r.record_kind === 'report.sealed').length;
    if (sealed > 0) {
      steps.push({
        label: 'Reports & ledger',
        shortLabel: 'Reports',
        segment: 'reports',
        status: 'done',
        description: `${plural(sealed, 'report')} sealed; the ledger's ${plural(i.ledger.record_count, 'record')} checked out on read.`,
      });
    } else {
      steps.push({
        label: 'Reports & ledger',
        shortLabel: 'Reports',
        segment: 'reports',
        status: 'pending',
        description: `No report has been generated yet. The ledger holds ${plural(i.ledger.record_count, 'record')} (for example data requests), and they checked out on read.`,
      });
    }
  } else if (i.ledger.status === 'failed') {
    steps.push({ label: 'Reports & ledger', shortLabel: 'Reports', segment: 'reports', status: 'blocked', description: 'The ledger check failed. This warrants accredited review.' });
  } else {
    steps.push({
      label: 'Reports & ledger',
      shortLabel: 'Reports',
      segment: 'reports',
      status: 'pending',
      description: i.ledger.status === 'empty' ? 'No report has been recorded in the ledger yet.' : i.ledger.message || 'The ledger could not be verified.',
    });
  }

  let currentSet = false;
  return steps.map((s, idx) => {
    let status = s.status;
    if (status === 'pending' && !currentSet) {
      status = 'current';
      currentSet = true;
    }
    return { ...s, status, id: idx + 1 };
  });
}

export function progressSummary(steps: readonly LifecycleStep[]): { done: number; total: number; next: LifecycleStep | null } {
  return { done: steps.filter((s) => s.status === 'done').length, total: steps.length, next: steps.find((s) => s.status === 'current') ?? null };
}
