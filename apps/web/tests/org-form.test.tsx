import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: () => undefined, replace: () => undefined, refresh: () => undefined }) }));

import { CreateOrgForm } from '../src/features/orgs/CreateOrgForm';
import { ORG_TYPE_OPTIONS, orgErrorMessage, validateOrgForm } from '../src/features/orgs/org-form';
import { NoOrganization } from '../src/features/orgs/NoOrganization';

describe('org form model', () => {
  it('rejects an empty or too short name and accepts a real one', () => {
    expect(validateOrgForm('', 'ngo').name).toMatch(/Enter a name/);
    expect(validateOrgForm('   ', 'ngo').name).toMatch(/Enter a name/);
    expect(validateOrgForm('A', 'ngo').name).toMatch(/at least 2/);
    expect(validateOrgForm('x'.repeat(201), 'ngo').name).toMatch(/under 200/);
    expect(validateOrgForm('Lake Trust', 'ngo')).toEqual({});
    expect(validateOrgForm('Lake Trust', 'wizard').type).toBeTruthy();
  });

  it('describes every organization type in plain words', () => {
    expect(ORG_TYPE_OPTIONS.map((o) => o.label)).toEqual(['NGO / Project developer', 'Funder / Investor', 'Independent auditor', 'Government']);
    for (const o of ORG_TYPE_OPTIONS) expect(o.plain.length).toBeGreaterThan(30);
  });

  it('turns API failures into friendly messages', () => {
    expect(orgErrorMessage({ detail: { code: 'conflict', message: 'That name is taken.' } }, 409)).toBe('That name is taken.');
    expect(orgErrorMessage(undefined, 409)).toMatch(/already exists/);
    expect(orgErrorMessage({ detail: [{ msg: 'x' }] }, 422)).toMatch(/Check the name/);
    expect(orgErrorMessage(undefined, 503)).toMatch(/server had a problem/);
    expect(orgErrorMessage(undefined)).toMatch(/Could not create/);
  });
});

describe('org form markup', () => {
  it('has a labelled name field, a type group and a submit button', () => {
    const html = renderToStaticMarkup(<CreateOrgForm />);
    expect(html).toMatch(/<label for="[^"]+-name"[^>]*>Organization name/);
    expect(html).toContain('<fieldset');
    expect(html.match(/type="radio"/g)).toHaveLength(4);
    expect(html).toContain('Create organization');
  });

  it('makes creating an organization an obvious primary section, not a collapsed <details>', () => {
    const html = renderToStaticMarkup(<NoOrganization />);
    expect(html).not.toContain('<details');
    expect(html).toContain('Create an organization');
    expect(html).toContain('Organization name');
    expect(html).toContain('Funder / Investor');
  });
});
