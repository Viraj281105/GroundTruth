import { serverApi } from './server-api';
import type { Schemas } from './api-client';

export type MeLoad = { status: 'ok'; me: Schemas['MeResponse'] } | { status: 'signed-out' } | { status: 'unreachable' };

/** Reads /auth/me with the visitor's cookie. 401 or a missing user means signed out; anything else is "unreachable". */
export async function loadMe(): Promise<MeLoad> {
  try {
    const res = await serverApi().GET('/auth/me');
    if (res.response.status === 401) return { status: 'signed-out' };
    if (!res.data) return { status: 'unreachable' };
    return res.data.user ? { status: 'ok', me: res.data } : { status: 'signed-out' };
  } catch {
    return { status: 'unreachable' };
  }
}
