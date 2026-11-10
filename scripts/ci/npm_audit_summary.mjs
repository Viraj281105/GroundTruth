#!/usr/bin/env node
// Make `npm audit` results visible without failing the build (#51, decision D4).
//
//   node scripts/ci/npm_audit_summary.mjs <npm-audit.json> [accepted-npm-advisories.json]
//
// Writes a Markdown table to $GITHUB_STEP_SUMMARY (or stdout when it is unset) and one
// `::warning::` annotation per vulnerable package. An advisory listed in the accepted file is
// labelled "accepted"; anything else is labelled NEW, so a newly published advisory stands out
// in the run summary. Always exits 0: the scan is advisory until after the competition, as
// recorded in SECURITY.md.

import { appendFileSync, existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const [auditPath, acceptedPath = path.join(here, 'accepted-npm-advisories.json')] = process.argv.slice(2);

function readJson(file, fallback) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

/** One row per vulnerable package that has advisories of its own (not only via another). */
export function summarise(audit, accepted) {
  const known = accepted?.packages ?? {};
  const rows = [];
  for (const [name, vuln] of Object.entries(audit?.vulnerabilities ?? {})) {
    const ids = (vuln.via ?? [])
      .filter((v) => typeof v !== 'string')
      .map((v) => String(v.url ?? v.source ?? '').split('/').pop())
      .filter(Boolean);
    if (ids.length === 0) continue;
    const acceptedIds = new Set(known[name]?.advisories ?? []);
    const fresh = ids.filter((id) => !acceptedIds.has(id));
    rows.push({ name, severity: vuln.severity, ids, fresh, fix: vuln.fixAvailable });
  }
  const order = { critical: 0, high: 1, moderate: 2, low: 3, info: 4 };
  rows.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9) || a.name.localeCompare(b.name));
  return rows;
}

function fixText(fix) {
  if (fix === true) return '`npm audit fix`';
  if (fix && typeof fix === 'object') return `${fix.name}@${fix.version}${fix.isSemVerMajor ? ' (major)' : ''}`;
  return 'none';
}

export function markdown(rows) {
  const fresh = rows.reduce((n, r) => n + r.fresh.length, 0);
  const lines = [
    '### npm audit (production dependencies, advisory)',
    '',
    rows.length === 0
      ? 'No known vulnerabilities.'
      : `${rows.length} vulnerable package(s); ${fresh === 0 ? 'no NEW advisories' : `**${fresh} NEW advisory(ies)**`}. ` +
        'Accepted ones are recorded in `scripts/ci/accepted-npm-advisories.json` and SECURITY.md.',
    '',
  ];
  if (rows.length > 0) {
    lines.push('| Package | Severity | Advisories | Status | Fix |', '| --- | --- | --- | --- | --- |');
    for (const r of rows) {
      const status = r.fresh.length === 0 ? 'accepted' : `**NEW**: ${r.fresh.join(', ')}`;
      lines.push(`| ${r.name} | ${r.severity} | ${r.ids.length} | ${status} | ${fixText(r.fix)} |`);
    }
  }
  return lines.join('\n') + '\n';
}

function main() {
  if (!auditPath || !existsSync(auditPath)) {
    console.log(`::warning::npm audit produced no report (${auditPath ?? 'no path given'})`);
    return;
  }
  const rows = summarise(readJson(auditPath, {}), readJson(acceptedPath, {}));
  const text = markdown(rows);
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, text + '\n');
  else process.stdout.write(text);
  for (const r of rows) {
    const label = r.fresh.length === 0 ? 'accepted' : `NEW ${r.fresh.join(', ')}`;
    console.log(`::warning title=npm audit: ${r.name}::${r.severity}, ${r.ids.length} advisory(ies), ${label}; fix: ${fixText(r.fix)}`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
