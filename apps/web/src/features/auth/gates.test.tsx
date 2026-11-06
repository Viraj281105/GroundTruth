import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RequireAuthView, RequireRoleView } from './RequireAuth';

const child = <p>SECRET-CONTENT</p>;
const html = (el: React.ReactElement) => renderToStaticMarkup(el);

describe('RequireAuthView', () => {
  it('shows a skeleton and never the children while loading', () => {
    const out = html(<RequireAuthView status="loading" required nextPath="/claims" action="run analyses">{child}</RequireAuthView>);
    expect(out).not.toContain('SECRET-CONTENT');
    expect(out).toContain('Checking your session');
  });
  it('shows the sign-in card when signed out and auth is required', () => {
    const out = html(<RequireAuthView status="signed-out" required nextPath="/cases/x/run" action="run analyses">{child}</RequireAuthView>);
    expect(out).not.toContain('SECRET-CONTENT');
    expect(out).toContain('Sign in to run analyses');
    expect(out).toContain('/login?next=%2Fcases%2Fx%2Frun');
    expect(out).toContain('Create account');
  });
  it('renders children when auth is not required or the user is signed in', () => {
    expect(html(<RequireAuthView status="signed-out" required={false} nextPath="/" action="x">{child}</RequireAuthView>)).toContain('SECRET-CONTENT');
    expect(html(<RequireAuthView status="signed-in" required nextPath="/" action="x">{child}</RequireAuthView>)).toContain('SECRET-CONTENT');
  });
});

describe('RequireRoleView', () => {
  const view = (status: 'loading' | 'signed-out' | 'signed-in', role: 'user' | 'dev' | 'admin' | null, minimum: 'dev' | 'admin') =>
    html(<RequireRoleView status={status} role={role} minimum={minimum} nextPath="/status">{child}</RequireRoleView>);
  it('hides content while loading', () => {
    expect(view('loading', null, 'dev')).not.toContain('SECRET-CONTENT');
  });
  it('lets dev and admin into a dev page, and only admin into an admin page', () => {
    expect(view('signed-in', 'dev', 'dev')).toContain('SECRET-CONTENT');
    expect(view('signed-in', 'admin', 'dev')).toContain('SECRET-CONTENT');
    expect(view('signed-in', 'dev', 'admin')).not.toContain('SECRET-CONTENT');
    expect(view('signed-in', 'admin', 'admin')).toContain('SECRET-CONTENT');
  });
  it('explains politely to a plain user', () => {
    const out = view('signed-in', 'user', 'dev');
    expect(out).toContain('This page is for developers');
    expect(out).toContain('granted by an admin');
    expect(out).toContain('href="/"');
  });
  it('invites signed-out visitors to sign in', () => {
    const out = view('signed-out', null, 'dev');
    expect(out).not.toContain('SECRET-CONTENT');
    expect(out).toContain('/login?next=%2Fstatus');
  });
});
