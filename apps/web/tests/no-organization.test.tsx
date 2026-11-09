import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: () => undefined, replace: () => undefined }) }));

import Page from '../src/app/(app)/app/no-organization/page';

describe('/app/no-organization', () => {
  it('tells a member-less user plainly that they are not in an organization yet', () => {
    const html = renderToStaticMarkup(<Page />);
    expect(html).toContain('You are not in an organization yet');
    expect(html).toContain('ask the owner or an admin');
    expect(html).toContain('href="/app"');
    expect(html).toContain('Sign out');
  });

  it('provides a form to create an organization', () => {
    const html = renderToStaticMarkup(<Page />);
    expect(html).toContain('Create an organization');
    expect(html).toContain('Organization name');
    expect(html).toContain('Organization type');
  });
});
