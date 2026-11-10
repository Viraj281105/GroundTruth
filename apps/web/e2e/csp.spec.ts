import { expect, test, type Page } from '@playwright/test';
import { ORG, signInViaApi, skipTour } from './helpers';

/**
 * Every page renders under the Content-Security-Policy (#51).
 *
 * The policy (security-headers.mjs) is strict, so the risk is a page that silently breaks: a map
 * whose tiles are refused, a script that never runs. Each page here is loaded from a real
 * `next build` + `next start` and must answer without a server error, carry the policy, show
 * content, and raise no `securitypolicyviolation` event and no CSP console error.
 */

const NGO = ORG.ngo;
const PROJECT = 'kariba-redd';

const PUBLIC_PAGES = ['/', '/login', '/register', '/method'];
const SIGNED_IN_PAGES = [
  '/app',
  `/app/${NGO}/dashboard`,
  `/app/${NGO}/portfolio`,
  `/app/${NGO}/projects`,
  `/app/${NGO}/projects/new`,
  `/app/${NGO}/settings/audit`,
  `/app/${NGO}/settings/members`,
  `/app/${NGO}/settings/sharing`,
  ...['overview', 'verification', 'evidence', 'observation', 'climate', 'reports', 'activity'].map(
    (tab) => `/app/${NGO}/projects/${PROJECT}/${tab}`,
  ),
  '/app/no-organization',
  '/account',
  '/admin/users',
  '/claims',
  '/compare',
  '/status',
];

async function watchForViolations(page: Page): Promise<string[]> {
  const found: string[] = [];
  page.on('console', (message) => {
    if (/content security policy|refused to (load|execute|connect|apply|create)/i.test(message.text())) {
      found.push(`console: ${message.text()}`);
    }
  });
  await page.exposeFunction('__reportCsp', (line: string) => found.push(line));
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      (window as unknown as { __reportCsp: (s: string) => void }).__reportCsp(
        `${event.violatedDirective} blocked ${event.blockedURI || '(inline)'} on ${location.pathname}`,
      );
    });
  });
  return found;
}

async function expectRendersCleanly(page: Page, path: string, violations: string[]): Promise<void> {
  const response = await page.goto(path);
  expect(response, `${path} answered`).not.toBeNull();
  expect(response!.status(), `${path} status`).toBeLessThan(500);
  // The policy is on the page itself, not only on the first document of a redirect chain.
  expect((await response!.allHeaders())['content-security-policy'], `${path} CSP header`).toContain(
    "frame-ancestors 'none'",
  );
  await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => undefined);
  await expect(page.locator('body')).not.toBeEmpty();
  expect(await page.locator('body').innerText(), `${path} shows content`).not.toEqual('');
  expect(violations, `${path} CSP violations`).toEqual([]);
}

test.describe('every page renders under the Content-Security-Policy', () => {
  for (const path of PUBLIC_PAGES) {
    test(`public ${path}`, async ({ page }) => {
      const violations = await watchForViolations(page);
      await expectRendersCleanly(page, path, violations);
    });
  }

  for (const path of SIGNED_IN_PAGES) {
    test(`signed in ${path}`, async ({ page }) => {
      await skipTour(page);
      const violations = await watchForViolations(page);
      await signInViaApi(page.context(), 'ngo');
      await expectRendersCleanly(page, path, violations);
    });
  }
});
