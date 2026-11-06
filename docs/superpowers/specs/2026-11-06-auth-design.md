# Authentication design — email + password accounts

Date: 2026-11-06 · Status: approved decisions (login method, protected areas) · Scope: API + web

## Decisions (from the user)

- **Method:** our own email + password accounts in Postgres. No third-party identity provider.
- **Protected:** starting, cancelling and verifying analyses, and the claims workbench. Browsing
  cases, evidence, compare, method and status stay public.

## Goals and non-goals

Real sign-in, sign-out and account management with sensible defaults, without storing anything
reversible. Non-goals: password-reset email (no mail service exists), OAuth, per-user ownership of
runs (needs a schema change to jobs; recorded as a follow-up), multi-factor auth.

## Model

`users(id uuid pk, email text unique (stored lowercased), password_hash text, role text, is_active bool, created_at, last_login_at)`
`sessions(id uuid pk, user_id fk, token_hash text unique, created_at, expires_at, revoked_at null, user_agent text null)`
Roles (three): `user` (default for new accounts: can run analyses and use claims), `dev` (everything a user can do,
plus developer areas: System status, API docs link, engine/worker health and job internals), `admin` (dev + manage users
and roles). Rank: user < dev < admin. **The first registered account becomes `admin`.** New migration `0006`.
No separate read-only role: browsing is public.

## Security rules

- Passwords: `hashlib.scrypt` (n=2**15, r=8, p=1, 16-byte random salt, 32-byte key), stored as
  `scrypt$n$r$p$salt_b64$hash_b64`; verify with `hmac.compare_digest`; rehash on login if parameters
  are stale. Policy: 10–128 characters, must not equal the email, not in a small built-in list of
  common passwords. Never log or return a hash or password.
- Sessions: opaque 32-byte `secrets.token_urlsafe` token; only its SHA-256 is stored. Cookie
  `gt_session`: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` when `AUTH_COOKIE_SECURE=true`,
  max-age 7 days. Logout revokes the row (real revocation) and clears the cookie. Changing a
  password revokes all other sessions of that user.
- CSRF: cookie auth plus (a) `SameSite=Lax`, (b) every unsafe method (POST/PUT/PATCH/DELETE) that
  carries the session cookie must send an `Origin` (or `Referer`) in the configured CORS allow-list,
  else 403 `csrf_origin_rejected`. CORS gains `allow_credentials=True` (exact origins only; `*` stays refused).
- Login abuse: in-memory sliding window, 5 failed attempts per (email, client IP) per 15 minutes
  then 429 `too_many_attempts` with `Retry-After`; identical error and timing for unknown email and
  wrong password (`invalid_credentials`); a dummy scrypt on unknown email to keep timing flat.
- Registration can be closed with `AUTH_ALLOW_REGISTRATION=false` (then only an admin can create users).
- Auth is enforced when `AUTH_REQUIRED=true`. Default in code is `false` so existing tooling keeps
  working; `docker-compose.yml` and `.env.example` set it to `true`. When disabled, the API logs a
  warning at startup and `GET /auth/me` reports `auth_required=false`.
- No store configured (`DATABASE_URL` unset): auth endpoints answer 503 `store_not_configured`, and
  with `AUTH_REQUIRED=true` protected endpoints answer 503 (never silently allow).

## API contract

| Method + path | Auth | Request → Response |
| --- | --- | --- |
| `POST /auth/register` | open (if allowed) | `{email, password}` → 201 `UserView`; sets session cookie |
| `POST /auth/login` | open | `{email, password}` → 200 `UserView`; sets cookie |
| `POST /auth/logout` | any | → 204; revokes session; clears cookie (idempotent) |
| `GET /auth/me` | any | → `{auth_required: bool, registration_open: bool, user: UserView\|null}` |
| `POST /auth/change-password` | signed in | `{current_password, new_password}` → 204 |
| `GET /auth/users` | admin | → `UserView[]` |
| `PATCH /auth/users/{id}` | admin | `{role?: 'user'|'dev'|'admin', is_active?}` → `UserView`; cannot demote/deactivate the last active admin |

`UserView = {id, email, role, is_active, created_at, last_login_at}`.
Errors use the existing `ApiErrorBody` shape with codes: `invalid_credentials`, `email_taken`,
`weak_password`, `too_many_attempts`, `unauthenticated` (401), `forbidden` (403),
`csrf_origin_rejected`, `registration_closed`.
Protected (require role ≥ user, i.e. any signed-in account, when `AUTH_REQUIRED`): `POST /jobs`, `POST /jobs/{id}/cancel`,
`POST /cases/{id}/verify`, `POST /claims/analyze`. Everything else is unchanged and public.

## Web

`AuthProvider` loads `/auth/me` (credentials included) on start. Header shows **Sign in** or a user
menu (initial, email, role Chip, Account, How it works, System status for dev/admin, Admin for admin, Sign out). Method and Status are no longer in the main navigation. Pages: `/login`, `/register`,
`/account` (profile, change password, sign out), `/admin/users` (admin only: role and active
toggles). A `RequireAuth` gate on `/cases/[id]/run` and `/claims` shows a clear "Sign in to run
analyses" card with a link to `/login?next=…`; after login the user returns to `next` (same-origin
paths only, validated). All authenticated fetches use `credentials: 'include'`. Forms validate
client-side (and always trust the server), show a password strength meter, never store the password
or any token in JS-readable storage, and announce errors accessibly. Light/dark, 375 px, keyboard
operable.

## Testing

Backend: hashing round-trip and rehash, policy, session lifecycle (login, me, logout revokes,
expired, revoked), first-user-admin, role gates (401/403), CSRF origin check, rate limit, timing-safe
unknown email path, admin guard on last admin, `AUTH_REQUIRED=false` leaves protected endpoints open.
Web: pure validators (email, password policy, safe `next` path), strength scoring, auth gate rendering
for each state, API error-code to message mapping.
