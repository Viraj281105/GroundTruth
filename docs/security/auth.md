# Authentication & Access Control (Operator Manual)

**Package**: `packages/groundtruth/src/groundtruth/platform/auth/` & `tenancy/`  
**Mechanism**: Cookie-based HTTP-Only Sessions, Multi-Tenant Organization Grants, CSRF Origin Validation, Rate Limiting.

GroundTruth 2.0 implements an enterprise authentication and access-control architecture supporting cross-organizational collaboration with rigorous isolation.

```mermaid
sequenceDiagram
    autonumber
    actor Client as Web Browser
    participant API as FastAPI Gateway
    participant Auth as Auth Service
    participant Tenancy as Tenancy Service
    participant DB as PostgreSQL Database

    Client->>API: POST /auth/login { email, password }
    API->>Auth: authenticate_user(email, password)
    Auth->>DB: Query user by email (Argon2id password verification)
    DB-->>Auth: User Record (Valid)
    Auth->>DB: Create Session (UUID, 7-day expiry)
    Auth-->>API: Session Cookie (HttpOnly, Secure, SameSite=Lax)
    API-->>Client: 200 OK (Set-Cookie: gt_session=...)

    Client->>API: GET /projects/proj_9b8a/runs (Cookie: gt_session=...)
    API->>Auth: validate_session(cookie)
    Auth-->>API: User Context (actor_id, organization_id)
    API->>Tenancy: check_grant(user_id, project_id, required="view")
    
    alt Grant Exists & Active
        Tenancy-->>API: Grant Valid (role="view")
        API-->>Client: 200 OK (Run Data)
    else No Grant (Cross-Org Access)
        Tenancy-->>API: Grant Missing
        API-->>Client: 403 Forbidden (cross_organization_denied)
    end
```

![Cross-Organization Access Denied](../product/screens/cross-org-denied.png)

---

## 1. Runtime Authentication Configuration

Configured via environment variables read by `groundtruth.platform.config.Settings`:

| Environment Variable | Default in Code | Meaning & Production Guidance |
| :--- | :--- | :--- |
| `AUTH_REQUIRED` | `true` | Enforces sign-in on all mutating endpoints (`POST /jobs`, `/cases/{id}/verify`, `/projects/*`). In production, this must always be `true`. |
| `AUTH_ALLOW_REGISTRATION` | `false` | When `false`, public sign-up is closed; only signed-in administrators can create new user accounts. |
| `AUTH_COOKIE_SECURE` | `true` | Appends `Secure` attribute to the session cookie. Must be `true` on HTTPS deployments. |
| `AUTH_SESSION_DAYS` | `7` | Duration in days before a session token expires. |
| `CORS_ALLOWED_ORIGINS` | Frontend URL | Strict comma-separated list of allowed browser origins (also serves as the CSRF allow-list). |

---

## 2. Multi-Tenant Role Hierarchy & Project Grants

GroundTruth 2.0 separates platform-level roles from project-level access grants:

```mermaid
graph TD
    subgraph PlatformRoles["1. Platform User Roles"]
        AdminRole["admin: Full system control, user provisioning, global audit inspection"]
        DevRole["dev: Developer privileges, diagnostic tools, OpenAPI snapshots"]
        UserRole["user: Standard tenant user, bound to organization grants"]
    end

    subgraph ProjectGrants["2. Project-Level Grants (Scoped to Organization)"]
        ViewGrant["view Grant<br/>• Read-only access to published evidence bundles<br/>• Executive dashboards & summary reports<br/>• Assigned to: Funders, General Observers"]
        AuditGrant["audit Grant<br/>• Full forensic verification privileges<br/>• Inspect raw satellite chips & donor matching diagnostics<br/>• Trigger sensitivity & placebo runs<br/>• Assigned to: Independent Auditors"]
        ContributeGrant["contribute Grant<br/>• Full administrative and data authoring privileges<br/>• Upload intervention boundaries & ground-truth surveys<br/>• Trigger production analysis jobs<br/>• Assigned to: Project Operators & NGOs"]
    end

    UserRole --> ViewGrant
    UserRole --> AuditGrant
    UserRole --> ContributeGrant
```

---

## 3. Security Controls & Protections

### 3.1 CSRF Defense Architecture
Cross-Site Request Forgery (CSRF) is mitigated via defense-in-depth:
1. **Cookie Configuration**: Session cookies carry `SameSite=Lax`, preventing third-party cross-site request inclusion.
2. **Origin & Referer Validation**: Mutating requests (`POST`, `PUT`, `DELETE`) carrying a session cookie are validated against `CORS_ALLOWED_ORIGINS`. Requests lacking a matching `Origin` or `Referer` header are rejected with `403 Forbidden`.

### 3.2 Password Hashing
User passwords are never stored in plaintext. Passwords are hashed using the **Argon2id** algorithm with per-user cryptographic salts, memory hardness, and multi-threaded time cost parameters.

### 3.3 Rate Limiting
Authentication endpoints are guarded by a token-bucket rate limiter:
- Restricts failed login attempts to 5 per (email, IP) tuple per 15-minute window.
- Exceeding the threshold locks authentication for the window and records an alert in the append-only audit log.
