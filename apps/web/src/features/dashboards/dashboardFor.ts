import type { ComponentType } from 'react';
import { NgoDashboard } from './NgoDashboard';
import { FunderDashboard } from './FunderDashboard';
import { AuditorDashboard } from './AuditorDashboard';
import { GovernmentDashboard } from './GovernmentDashboard';
import type { DashboardData, OrgType } from './loadDashboardData';

export type DashboardComponent = ComponentType<{ data: DashboardData }>;

/** The dashboard for an org type. `reference` uses the NGO layout (read-only; the loader flags it). */
export function dashboardFor(orgType: OrgType): DashboardComponent {
  switch (orgType) {
    case 'funder':
      return FunderDashboard;
    case 'auditor':
      return AuditorDashboard;
    case 'government':
      return GovernmentDashboard;
    case 'ngo':
    case 'reference':
    default:
      return NgoDashboard;
  }
}
