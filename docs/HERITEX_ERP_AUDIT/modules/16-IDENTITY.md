# 16 — Identity, Authentication, RBAC & Audit

**Module owner:** Identity (platform)
**Rank:** foundational — every other module's security, tenancy and audit trail live here. If Identity is wrong, nothing else is trustworthy.
**Current state:** solid core — JWT with token revocation, bcrypt, tenant scoping, a real RBAC catalog + role templates, audit logs. Field-level RBAC and some hardening are missing.
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns: tenants (multi-tenancy), users, roles/permissions (RBAC), authentication (JWT), audit logging, and the permission catalog that all modules register into. Identity is the enforcement point for Invariant I6.

**In scope:** tenant lifecycle, user lifecycle, auth (register/login/refresh/logout/password), RBAC catalog + role templates + assignment, audit log, token revocation, session control.
**Out of scope (v1):** SSO/OIDC federation (v1.5), MFA (v2 — but token_version already supports forced re-auth), device/API-key management, custom field designer.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Tenant`, `User`, `Role`, `Permission`, `AuditLog` | ✅ 5 tables (`identity/models.py`) |
| Tenant fields | `name, slug, plan, is_active, settings` |
| User fields | `email, hashed_password, full_name, phone, avatar_url, is_active, is_superuser, is_verified, token_version, last_login_at, tenant_id` |
| Role | ✅ with `permissions` M2M, `approval_limit`, `is_system` |
| Permission | ✅ `code, module, action, description` (unique code) |
| Auth endpoints | ✅ register, login, refresh, me, change-password, logout (`identity/router.py`) |
| JWT | ✅ access+refresh, `token_version` revocation check in `get_current_user` (`deps.py`) |
| RBAC | ✅ `require_permissions` / `require_all_permissions` / `require_superuser`; `permission_codes()` |
| Permission catalog + role templates | ✅ `permissions_catalog.py` (13 modules, 8 templates) |
| Tenant scoping | ✅ `crud.py::tenant_scoped`, applied in `deps` |
| Audit log + `record_audit` | ✅ (manual hook in CRUD factory; not signal-based) |
| **Field-level RBAC** | ❌ D4 — no attribute-level policy; any user with `read` sees salary/bank/PAN fields |
| **Rate limiting on auth** | ❌ no per-IP/account throttle on login/register |
| **Refresh token rotation/revocation** | 🟡 refresh issues a new pair; no explicit refresh-token blocklist (relies on token_version) |
| **Email verification / password reset flow** | 🟡 `is_verified` exists; no email flow, no reset endpoint (only admin reset) |
| **Audit on direct ORM writes** | 🟡 audit is called from the CRUD factory; code that bypasses the factory skips audit |
| **2FA/MFA** | ❌ (v2) |

**Headline:** the RBAC/auth core is genuinely good — token_version revocation, a single-source permission catalog, tenant scoping. The gaps are: **field-level security** (D4 — a finance `read` user currently sees salary), **rate limiting** (brute-force exposure), and **email flows** (verification/reset absent).

---

## 3. Domain model

### 3.1 Target entities (extends existing)

```
tenants
  + add: plan_details, data_retention_days, locale, timezone, compliance_flags (DPDP, GST),
          suspended_reason, feature_flags (JSON), created_via

users
  + add: title, department, employee_id (link HR), last_password_change, password_history (JSON),
          failed_login_count, locked_until, email_verified_at, mfa_enabled (bool, v2), consent_updated_at

roles
  + add: description (exists), assignment_scope [tenant|global], inherits_from (optional),
          data_scope [self|department|tenant|all] — drives field/record visibility

permissions
  + add: applies_to_model, field_restrictions (JSON) — the D4 data-policy layer

NEW:
audit_logs  → add index on (tenant_id, entity, entity_id) and (actor_id, created_at)
field_policies     role_id, model, field, access [hidden|readonly|readwrite], reason
password_audit     user_id, changed_at, changed_by, method [self|admin|reset]
sessions           user_id, token_jti, refresh_jti, issued_at, expires_at, ip, user_agent, revoked_at
email_tokens       user_id, purpose [verify|reset], token_hash, expires_at, used_at
```

### 3.2 Field-level RBAC design (D4)
A small `field_policies` table: `(role, model, field, access)`. Serializers consult it before rendering; hidden fields are omitted, readonly fields stripped from update payloads. Defaults: all `readwrite`; HR/salary and bank/PAN fields `hidden` for non-HR roles. This closes the D4 decision from MA §12.

---

## 4. State machines

### 4.1 User
```
invited    --activate-->  active     (set password, verify email)
active     --suspend-->   suspended  guard: admin action + reason
suspended  --restore-->   active
active     --terminate--> terminated (remove sessions, revoke tokens, archive)
```
### 4.2 Login lockout
```
normal    --fail-->   fail_x
fail_x    --fail-->   locked     guard: x >= threshold (e.g. 5) → locked_until = now + 15 min
locked    --wait-->   normal     (time passes)
locked    --unlock-->  normal     (admin action, audited)
```

---

## 5. API surface

Current: register, login, refresh, me, change-password, logout, permissions, users CRUD + reset-password, roles CRUD + catalog, tenants CRUD (admin), audit-logs.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `POST /auth/request-verification` | POST | public | send email (module 12) |
| `POST /auth/verify-email` | POST | public | verify |
| `POST /auth/request-reset` | POST | public | password reset email |
| `POST /auth/reset-password` | POST | public | set new password |
| `POST /auth/rotate-refresh` | POST | auth | explicit refresh rotation |
| `GET /auth/sessions` | POST | self | list active sessions |
| `POST /auth/sessions/{id}/revoke` | POST | self | revoke a session (device) |
| `POST /admin/users/{id}/lock` | POST | `system.user.manage` | lockout override |
| `GET /admin/field-policies` | GET | `system.role.manage` | field policy admin |

---

## 6. Business rules

- **ID-01** — Password policy: ≥8 chars, mixed, no common words; bcrypt with cost ≥ 12; history prevents reuse.
- **ID-02** — Login throttled: N failures → lock with backoff; captcha if suspicious (v1.5). *(Missing.)*
- **ID-03** — Tokens carry `ver` = token_version; any `ver` mismatch rejects (already true).
- **ID-04** — Refresh rotates: issuing a new refresh invalidates the prior pair (v1.5 target; today relies on token_version).
- **ID-05** — Field-level policy applied on read AND update (D4).
- **ID-06** — Audit writes are append-only and include `tenant_id`, `actor`, `entity`, `diff` (already true in `record_audit`).
- **ID-07** — Direct ORM writes that bypass the CRUD factory still must call `record_audit` (enforced by review + a test).
- **ID-08** — Tenants are isolated; a cross-tenant id access returns 404 (already true in `tenant_scoped`).
- **ID-09** — Superadmin is per-instance; tenant admins can't grant global roles.
- **ID-10** — DPDP: user data erasure respects audit/financial holds (delete account, keep records).

---

## 7. Workflows (end-to-end)

### 7.1 Registration → tenant → first admin
1. Public register creates user (default tenant or create tenant via admin).
2. Email verification token sent (module 12) → verify → `is_verified`.
3. Admin assigns roles; role templates seeded from `permissions_catalog`.
4. User logs in → access+refresh → RBAC + field policies applied on every request.

### 7.2 Brute-force / session hygiene
1. Login failures increment `failed_login_count` → lock at threshold (ID-02).
2. User sees active sessions; revokes a lost device.
3. Password change bumps `token_version` → all old tokens dead (already true).

### 7.3 Audit trail
Every CRUD factory call writes `audit_logs`. Custom handlers (fulfil, checkout, payroll) already call `record_audit`. Goal: a test asserts that every state-changing endpoint writes ≥1 audit row.

---

## 8. Accounting impact

None — Identity owns no money. But its correctness is what makes Finance's audit trail believable (a finance audit without reliable identity is worthless).

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Zoho** | SSO, roles, audit | token_version revocation, field policies | Zoho's SSO breadth |
| **SAP B1** | User/roles, audit | Single source permission catalog | SAP's fine-grained object authz |
| **Odoo** | Groups/access rules, multi-company | Cleaner tenant scoping | Odoo's ACL expression breadth |
| **Auth0/Keycloak** | — (we are a backend, not an IdP) | We embed, not federate (v1) | full IdP features |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Auth-risk flag** (unusual login time/IP, impossible travel) | session challenged | read-only; never auto-lock without policy |
| 2 | "Who has finance access?", "recent admin changes" | quick audit answers | read-only, admin-only |

Keep AI light here — security features must be deterministic first (AI as a *signal*, policy as the *enforcement*).

---

## 11. Non-functional & security

- Performance: auth < 100 ms; RBAC check < 5 ms (cached permission sets).
- Security: bcrypt ≥12; JWT HS256 with strong secret (rotate); TLS; encrypted secrets; audit append-only.
- **Rate limiting:** login/register per IP+account (ID-02) — missing today.
- Retention: audit 8 years; sessions 30 days; email tokens 24h.
- DPDP: consent for email/SMS; erasure with holds.

---

## 12. Reporting & analytics

Active users/tenants, role distribution, failed-login heatmap, audit volume by module, locked accounts, permission drift (users with roles vs catalog changes).

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `user.created`, `user.suspended`, `user.locked` | out | Audit, Integrations (notify admin), HR (link employee) |
| `session.revoked` | out | Analytics |
| (in) email verification/reset | → | module 12 (SMTP/WhatsApp) |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (field-level RBAC)** | `field_policies` + serializer enforcement; seed HR/finance masking | ID-05 tests; salary hidden for non-HR |
| **M2 (auth hardening)** | rate limiting, lockout, request-reset/verify email flow, session list/revoke | ID-01/02/04 tests; brute-force test |
| **M3 (audit completeness)** | audit test harness; ensure every transition audited | ID-07 test; zero bypass |
| **M4 (DPDP + hygiene)** | erasure flow, retention, consent fields | ID-10 tests |

Order: **M1 → M2 → M3 → M4**. M1 is the biggest (it changes every serializer).

---

## 15. Test plan

- Field policy: HR role sees salary; sales role doesn't (M1).
- Rate limit: 6th login attempt locked; unlock after time/admin (M2).
- Reset flow: token valid once, expires (M2).
- Every endpoint writes audit (M3).
- Erasure keeps financial records (M4).

---

## 16. Migration & rollout

- Seed field policies + role templates; backfill password hashes from the existing auth (they're already bcrypt).
- Feature-flag field policies per tenant.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Field-level RBAC skipped (D4 open) | salary/PAN leak to sales roles | M1 blocker |
| No rate limit | credential stuffing | M2 blocker |
| Audit bypass via custom handlers | undetectable fraud | M3 test harness |

---

## 18. Definition of Done

- [ ] M1 field-level RBAC (D4 closed)
- [ ] M2 rate limiting, lockout, email verify/reset, sessions
- [ ] M3 audit completeness enforced by test
- [ ] M4 DPDP erasure + retention + consent
- [ ] RBAC catalog complete, role templates seeded
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated