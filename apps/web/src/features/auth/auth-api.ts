import { createApiClient, type ApiClient, type Schemas } from '../../lib/api-client';
import { toAuthUser } from '../../lib/auth';
import type { AuthUser } from '../../lib/auth-core';
import { errorMessage } from './validate';

export type UserView = Schemas['UserView'];

export type AuthResult<T> = { ok: true; data: T } | { ok: false; code: string; message: string; status: number };

function failure(status: number, error: unknown, response?: Response): { ok: false; code: string; message: string; status: number } {
  const detail = (error as { detail?: { code?: unknown; message?: unknown } } | undefined)?.detail;
  let code = typeof detail?.code === 'string' ? detail.code : status === 0 ? 'network' : status === 401 ? 'unauthenticated' : status === 403 ? 'forbidden' : 'unknown';
  const serverMessage = typeof detail?.message === 'string' ? detail.message : '';
  if (code === 'unknown' && /last (active )?admin/i.test(serverMessage)) code = 'last_admin';
  if (/last (active )?admin/i.test(serverMessage)) code = 'last_admin';
  const retry = Number(response?.headers.get('Retry-After'));
  return { ok: false, status, code, message: errorMessage(code, Number.isFinite(retry) ? retry : null) };
}

async function call<T>(run: () => Promise<{ data?: T; error?: unknown; response: Response }>): Promise<AuthResult<T>> {
  try {
    const { data, error, response } = await run();
    if (response.ok) return { ok: true, data: data as T };
    return failure(response.status, error, response);
  } catch {
    return failure(0, undefined);
  }
}

export interface Credentials {
  email: string;
  password: string;
}

export async function login(c: Credentials, client: ApiClient = createApiClient()): Promise<AuthResult<AuthUser>> {
  const r = await call(() => client.POST('/auth/login', { body: c }));
  return mapUser(r);
}

export async function register(c: Credentials, client: ApiClient = createApiClient()): Promise<AuthResult<AuthUser>> {
  const r = await call(() => client.POST('/auth/register', { body: c }));
  return mapUser(r);
}

function mapUser(r: AuthResult<UserView>): AuthResult<AuthUser> {
  if (!r.ok) return r;
  const user = toAuthUser(r.data);
  return user ? { ok: true, data: user } : failure(500, undefined);
}

export async function changePassword(current: string, next: string, client: ApiClient = createApiClient()): Promise<AuthResult<null>> {
  const r = await call(() => client.POST('/auth/change-password', { body: { current_password: current, new_password: next } }));
  return r.ok ? { ok: true, data: null } : r;
}

export async function listUsers(client: ApiClient = createApiClient()): Promise<AuthResult<UserView[]>> {
  return call(() => client.GET('/auth/users'));
}

export async function updateUser(id: string, patch: { role?: UserView['role']; is_active?: boolean }, client: ApiClient = createApiClient()): Promise<AuthResult<UserView>> {
  return call(() => client.PATCH('/auth/users/{user_id}', { params: { path: { user_id: id } }, body: patch }));
}
