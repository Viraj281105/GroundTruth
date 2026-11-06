# Authentication (operator notes)

Email + password accounts in the platform database, cookie sessions. Design: `docs/superpowers/specs/2026-11-06-auth-design.md`.

## Settings

| Env var | Default in code | Meaning |
| --- | --- | --- |
| `AUTH_REQUIRED` | `false` | Enforce sign-in on `POST /jobs`, `POST /jobs/{id}/cancel`, `POST /cases/{id}/verify`, `POST /claims/analyze`. `docker-compose.yml` and `.env.example` set it `true`. With `false` the API logs a startup warning and those endpoints are open. |
| `AUTH_ALLOW_REGISTRATION` | `true` | `false` closes `POST /auth/register`, except for a signed-in admin creating accounts. |
| `AUTH_COOKIE_SECURE` | `false` | Set `true` behind HTTPS (adds `Secure` to the cookie). |
| `AUTH_SESSION_DAYS` | `7` | Session and cookie lifetime. |
| `CORS_ALLOWED_ORIGINS` | frontend URL | Also the CSRF origin allow-list. Exact origins only. |

Run migrations (`0006` adds `users`, `sessions`) before starting. With no database, auth endpoints answer 503, and with `AUTH_REQUIRED=true` protected endpoints answer 503 (never allow).

## Roles

`user` (default; can run analyses and use claims) < `dev` (developer areas; no dev-only endpoints yet) < `admin` (manage users via `GET /auth/users`, `PATCH /auth/users/{id}`). The first account registered becomes `admin`. The last active admin cannot be demoted or deactivated. `/auth/users*` are enforced even if `AUTH_REQUIRED=false`.

## Limitations and deviations

- Failed-login rate limiting (5 per email+IP per 15 min) is in memory, per process: several workers multiply the limit, and a restart resets it. The client IP is the direct peer; `X-Forwarded-For` is not trusted, so behind a proxy all users share one IP.
- No password reset or email verification (no mail service).
- Runs have no per-user ownership; any `user` can cancel any job.
- Concurrent first registrations could both become admin (no cross-process lock).
- Inactive accounts get the same `invalid_credentials` answer as wrong passwords.
- `GET /auth/me` answers 200 `auth_required=false` when auth is off and no database exists (instead of 503), so the web app can start.
- The CSRF check rejects an unsafe request that has the session cookie and no `Origin`/`Referer`.
- A signed-in admin can create accounts through `POST /auth/register` when registration is closed.
