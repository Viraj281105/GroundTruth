/** Pure client-side validation. The server is always the authority; these only give early, kind feedback. */

export const MIN_PASSWORD = 10;
export const MAX_PASSWORD = 128;

/** Mirrors COMMON_PASSWORDS in the API's platform/auth/passwords.py. */
const COMMON = new Set([
  'password', 'password1', 'password12', 'password123', 'passw0rd123', '1234567890', '12345678910', '123456789012',
  'qwertyuiop', 'qwerty1234', 'qwerty12345', '1q2w3e4r5t', 'iloveyou12', 'letmein123', 'welcome123', 'admin12345',
  'administrator', 'changeme123', 'abcdefghij', 'abc1234567', 'groundtruth', 'groundtruth1', 'groundtruth123',
  '0123456789', '1111111111', '0000000000',
]);

export function isValidEmail(email: string): boolean {
  const e = email.trim();
  return e.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e);
}

export interface PasswordCheck {
  id: 'length' | 'not-email' | 'not-common' | 'varied';
  label: string;
  ok: boolean;
}

/** Live checklist for the register form. */
export function passwordChecks(password: string, email = ''): PasswordCheck[] {
  const lowered = password.toLowerCase();
  return [
    { id: 'length', label: `${MIN_PASSWORD} to ${MAX_PASSWORD} characters`, ok: password.length >= MIN_PASSWORD && password.length <= MAX_PASSWORD },
    { id: 'not-email', label: 'Not your email address', ok: password.length > 0 && lowered !== email.trim().toLowerCase() },
    { id: 'not-common', label: 'Not a common password', ok: password.length > 0 && !COMMON.has(lowered) },
    { id: 'varied', label: 'More than one repeated character', ok: password.length > 0 && new Set(lowered).size > 1 },
  ];
}

/** First policy problem in plain words, or null when the password passes. */
export function passwordProblem(password: string, email = ''): string | null {
  if (password.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`;
  if (password.length > MAX_PASSWORD) return `Use at most ${MAX_PASSWORD} characters.`;
  if (password.toLowerCase() === email.trim().toLowerCase()) return 'The password must not be your email address.';
  const lowered = password.toLowerCase();
  if (COMMON.has(lowered) || new Set(lowered).size === 1) return 'That password is too common. Choose something less guessable.';
  return null;
}

export interface Strength {
  score: 0 | 1 | 2 | 3 | 4;
  label: string;
}

const LABELS = ['Too weak', 'Weak', 'Fair', 'Good', 'Strong'] as const;

/** A rough 0-4 score. It rewards length and variety, and is 0 for anything the policy rejects. */
export function strengthScore(password: string, email = ''): Strength {
  if (!password || passwordProblem(password, email)) return { score: 0, label: LABELS[0] };
  let score = 1;
  if (password.length >= 12) score += 1;
  if (password.length >= 16) score += 1;
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(password)).length;
  if (classes >= 3) score += 1;
  if (new Set(password).size < 5) score = Math.min(score, 1);
  const s = Math.min(score, 4) as Strength['score'];
  return { score: s, label: LABELS[s] };
}

/** Only same-origin relative paths: a single leading '/', no '//', backslashes, schemes, control chars or /login loops. */
export function safeNextPath(next: string | null | undefined, fallback = '/'): string {
  if (!next || typeof next !== 'string') return fallback;
  if (!next.startsWith('/') || next.startsWith('//')) return fallback;
  // eslint-disable-next-line no-control-regex
  if (next.includes('\\') || /[\u0000-\u001f\u007f]/.test(next) || next.includes('://')) return fallback;
  let decoded = next;
  try {
    decoded = decodeURIComponent(next);
  } catch {
    return fallback;
  }
  if (decoded.startsWith('//') || decoded.includes('\\')) return fallback;
  const path = next.split(/[?#]/)[0];
  if (/^\/(login|register)\/?$/.test(path)) return fallback;
  return next;
}

export type AuthErrorCode =
  | 'invalid_credentials'
  | 'email_taken'
  | 'weak_password'
  | 'too_many_attempts'
  | 'unauthenticated'
  | 'forbidden'
  | 'csrf_origin_rejected'
  | 'registration_closed'
  | 'store_not_configured'
  | 'last_admin'
  | 'network';

/** Plain-language message for a server error code. `retryAfterSeconds` comes from the Retry-After header. */
export function errorMessage(code: string | null | undefined, retryAfterSeconds?: number | null): string {
  switch (code) {
    case 'invalid_credentials':
      return 'That email and password do not match. Check them and try again.';
    case 'email_taken':
      return 'An account with that email already exists. Try signing in instead.';
    case 'weak_password':
      return 'That password does not meet the rules. Use 10 or more characters and avoid common passwords.';
    case 'too_many_attempts': {
      if (retryAfterSeconds && retryAfterSeconds > 0) {
        const mins = Math.ceil(retryAfterSeconds / 60);
        const wait = retryAfterSeconds < 60 ? `${Math.ceil(retryAfterSeconds)} seconds` : `${mins} minute${mins === 1 ? '' : 's'}`;
        return `Too many attempts. Please wait about ${wait} and try again.`;
      }
      return 'Too many attempts. Please wait a few minutes and try again.';
    }
    case 'unauthenticated':
      return 'You are not signed in, or your session expired. Sign in again.';
    case 'forbidden':
      return 'You do not have permission to do that.';
    case 'csrf_origin_rejected':
      return 'The request came from an address this server does not trust. Reload the page from the official site.';
    case 'registration_closed':
      return 'New accounts are closed on this server. Ask an administrator to create one for you.';
    case 'store_not_configured':
      return 'Accounts are not set up on this server yet (no database is configured).';
    case 'last_admin':
      return 'There must always be at least one active admin. Make someone else an admin first.';
    case 'network':
      return 'Could not reach the server. Check your connection and try again.';
    default:
      return 'Something went wrong. Please try again.';
  }
}

/** Where sign-in and sign-up land when there is no valid `next`. */
export const POST_LOGIN_HOME = '/app';

/**
 * `next` after login must be a same-origin relative path inside the app (`/app` or `/app/...`).
 * Anything else, including every open-redirect shape `safeNextPath` rejects, falls back to `/app`.
 */
export function safeAppNextPath(next: string | null | undefined): string {
  const safe = safeNextPath(next, '');
  if (!safe) return POST_LOGIN_HOME;
  if (!/^\/app(?:[/?#]|$)/.test(safe)) return POST_LOGIN_HOME;
  // Dot segments (literal or percent-encoded once) could climb out of /app after normalisation.
  let path = safe.split(/[?#]/)[0];
  try {
    path = decodeURIComponent(path);
  } catch {
    return POST_LOGIN_HOME;
  }
  return path.split('/').some((seg) => seg === '.' || seg === '..') ? POST_LOGIN_HOME : safe;
}
