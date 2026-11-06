import { describe, expect, it } from 'vitest';
import { createApiClient } from '../../lib/api-client';
import { analyzeClaims } from './client';

const json = (status: number, body: unknown) => async () =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('analyzeClaims', () => {
  it('returns data on success', async () => {
    const body = { claims: [], comparisons: [], disclaimer: 'x' };
    const r = await analyzeClaims('t', null, createApiClient({ baseUrl: 'http://x', fetch: json(200, body) }));
    expect(r).toEqual({ kind: 'ok', data: body });
  });
  it('reports a rejected request', async () => {
    const r = await analyzeClaims('t', 'nope', createApiClient({ baseUrl: 'http://x', fetch: json(404, { detail: 'Unknown case' }) }));
    expect(r).toEqual({ kind: 'rejected', status: 404, message: 'Unknown case' });
  });
  it('reports an unreachable backend', async () => {
    const fail = async () => {
      throw new TypeError('down');
    };
    expect(await analyzeClaims('t', null, createApiClient({ baseUrl: 'http://x', fetch: fail }))).toEqual({ kind: 'unreachable' });
  });
});
