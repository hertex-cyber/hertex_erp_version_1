# Hertex ERP — Auth Module Implementation Plan

**Status:** implemented (P0–P3) · **Owner:** backend + frontend · **Date:** 2026-11-17
**Scope:** identity, authentication, session lifecycle, credential policy, MFA, RBAC hardening.
**Benchmarks:** Zoho One security policies (org-wide/policy-based MFA, password policy, session lifetime, trusted browsers, recovery codes, audit of sign-ins) and SAP Cloud Identity Services / BTP security recommendations (MFA for all users, risk-based/conditional auth, enterprise password policy, password history/lockout, SCIM lifecycle, SSO via SAML/OIDC, `Secure`+`HttpOnly` session cookies, least-privilege admin roles, periodic review of stale users).

---

## 1. Current state (verified from code)

| Area | What exists | Evidence |
|---|---|---|
| Credentials | bcrypt hashing, 8-char minimum, no complexity/breach/name checks | `backend/app/core/security.py:12`, `backend/app/modules/identity/schemas.py:79-109` |
| Login | Email+password, generic error, `last_login_at`, `login` audit | `backend/app/modules/identity/router.py:118-139` |
| Tokens | JWT access (60 min) + refresh (14 d), `token_version` revocation | `backend/app/core/config.py:21-22`, `backend/app/core/security.py:45-70` |
| Refresh | Body-based refresh token, no rotation/reuse detection | `backend/app/modules/identity/router.py:142-150` |
| Logout | Global revocation by incrementing `token_version` only | `backend/app/modules/identity/router.py:218-225` |
| RBAC | 13-module permission catalog, 8 role templates, module+action checks | `backend/app/core/permissions_catalog.py`, `backend/app/core/deps.py:61-80` |
| Audit | `AuditLog` with actor/IP/UA, but IP ignores proxy headers; failed logins not audited | `backend/app/core/audit.py:35-57`, `backend/app/core/deps.py:83-87` |
| Profile | `/auth/me`, `/auth/permissions`, `/auth/change-password` | `backend/app/modules/identity/router.py:153-215` |
| Frontend | Tokens in `localStorage`, Zustand `persist`, bearer interceptor, single-flight refresh | `frontend/src/lib/tokens.js`, `frontend/src/lib/api.js`, `frontend/src/store/auth.js` |
| UI | Login/register only; no MFA, password reset, sessions, or password strength | `frontend/src/pages/Auth.jsx` |

### Gaps against the benchmark

1. No MFA, recovery codes, trusted device, or step-up authentication.
2. No rate limiting, lockout, or failed-login auditing (credential stuffing / brute force).
3. Refresh tokens are reusable forever until global revocation; no rotation, `jti`, device/session record, or per-session revocation.
4. Refresh tokens in `localStorage` are XSS-readable; no `HttpOnly`/`Secure` cookie, no CSRF defence, no origin check.
5. Weak password policy (8 chars only); no reuse/history, no sequential/name checks.
6. No self-service password reset or email verification challenge.
7. No security headers middleware; IP behind a proxy is recorded incorrectly.
8. No least-privilege separation for user/role administration beyond two permission codes; no audit of authorization denials.
9. No session inventory or stale-user review signal (`last_login_at` exists but is unused for governance).

---

## 2. Target design

### 2.1 Data model (new migration)

- `users`: add `mfa_secret` (encrypted-at-rest string, nullable), `mfa_enabled` bool, `mfa_last_step` int, `locked_until` timestamp, `failed_login_count` int, `password_changed_at` timestamp, `password_history` JSON (hashed, last 5).
- New `auth_sessions`: `id`, `tenant_id`, `user_id`, `jti`, `refresh_hash` (SHA-256), `ip_address`, `user_agent`, `device_label`, `expires_at`, `revoked_at`, `last_used_at`, timestamps.
- New `auth_tokens`: one-time tokens for password reset / email verification / MFA challenge; stores `token_hash`, `purpose`, `user_id`, `expires_at`, `used_at`.

### 2.2 Backend phases

**P0 — Credential hardening (do first)**
- Password policy service: ≥12 chars, upper/lower/digit/symbol, no email/name fragments, no sequential/repeated runs, deny-list of common passwords, no reuse of last 5 hashes. Configurable via `Settings`.
- Login: constant-time dummy hash for unknown users, generic `UnauthorizedError`, failed-login audit, 5 failures → 15-minute lockout; per-IP + per-email Redis sliding-window rate limit (falls back to in-process when Redis unavailable).
- Proxy-aware `client_ip()` used by all security audit events.
- Security headers middleware (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS in production).

**P1 — Session & token lifecycle**
- Access token: 15 min, includes `jti`, `sid` (session id), `typ`. Refresh token: 7 days, random `jti`, stored as SHA-256 hash in `auth_sessions`.
- Refresh rotation on every use; reuse of a consumed hash revokes the whole session family and is audited as `session.reuse_detected`.
- Refresh delivered as `HttpOnly; Secure(prod); SameSite=Lax` cookie `hertex_refresh`; JSON body retained only for backwards compatibility/tests.
- CSRF: double-submit `hertex_csrf` cookie + `X-CSRF-Token` header on refresh/logout, plus `Origin` validation.
- Endpoints: `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `DELETE /auth/sessions` (revoke all, keep current optional).

**P2 — MFA**
- TOTP (RFC 6238, stdlib HMAC-SHA1/256, base32 secret, ±1 step window, replay guard) and 8 recovery codes (hashed).
- `POST /auth/mfa/setup` (secret + otpauth:// URI), `POST /auth/mfa/enable`, `POST /auth/mfa/disable`, `POST /auth/mfa/verify`.
- Login returns `mfa_required` + short-lived challenge token when MFA is enabled; verify accepts TOTP or recovery code.
- `REQUIRE_MFA_FOR_ADMINS` setting; tenant-level `settings.require_mfa` reserved for policy rollout. All MFA events audited.

**P3 — Recovery & verification**
- `POST /auth/forgot-password` (always 202, generic response), `POST /auth/reset-password` with single-use hashed token, 30-minute expiry, password policy, revokes all sessions.
- `POST /auth/verify-email` + `POST /auth/resend-verification`; development mode returns the token in the response when no mail transport is configured (never in production).
- `GET /auth/security` returns policy, MFA state, session count, last logins.

**P4 — Governance / deferred**
- SAML 2.0 / OIDC federation, SCIM provisioning, FIDO2/WebAuthn, HIBP k-anonymity breach check, IP/time-window conditional access, risk scores. These need external IdP/config contracts and are deliberately out of scope for this iteration; the data model leaves room for them.

### 2.3 Frontend phases

- Replace `localStorage` tokens with in-memory access token + cookie refresh (`withCredentials`, single-flight refresh, CSRF header). Remove token keys from `persist`.
- Login: two-step MFA challenge, recovery-code option, clear lockout/rate-limit messages, forgot-password link.
- Register: password strength meter + live policy hints.
- New `SecuritySettings` page: change password (policy enforced), MFA enrol/disable + recovery codes, active sessions with revoke buttons, recent sign-ins.
- New `ForgotPassword` / `ResetPassword` pages.
- Route guard (`ProtectedRoute`) unchanged, but bootstrap now calls `/auth/refresh` first; unauthorized responses clear state.

### 2.4 Tests & Definition of Done

Backend pytest coverage: password policy cases, lockout, invalid/valid login audit, refresh rotation + reuse detection, session revoke, MFA enable/challenge/recovery, reset-password single use, RBAC denial. Frontend: `npm run build` succeeds; manual smoke of login → MFA → refresh → logout.

---

## 3. Rollout order

P0 → P1 → P2 → P3, with migrations and tests landing in the same commit as each phase. Existing seeded admin (`admin@hertex.dev`) must continue to work; MFA is opt-in for non-admins by default so the current demo flow is not broken.

---

## 4. Implementation record (2026-11-17)

### Landed

- Migration `ece7476d64c5_auth_hardening` applied: adds `auth_sessions`, `auth_tokens`, and the new `users` security columns; `alembic check` reports no drift.
- Backend credential hardening: configurable password policy, common/sequential/name checks, password history, dummy-hash verification, failed-login counters, 15-minute lockout, per-IP/per-email rate limiting, and proxy-aware audit IP.
- Backend token lifecycle: 15-minute access tokens, 7-day rotating refresh cookies, hashed refresh tokens, session records, reuse detection, per-session revocation, `jti`/`sid` claims, and session-aware `get_current_user`.
- Backend endpoints: `/auth/mfa/setup|enable|disable|verify`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password`, `/auth/sessions`, `/auth/sessions/{id}`, `/auth/security`, plus MFA challenge responses from `/auth/login`.
- Security headers middleware is wired in `app/main.py`; audit payload redacts secrets and recovery codes.
- Frontend: access token kept only in memory; refresh via `HttpOnly` cookie with `X-CSRF-Token`; bootstrap silently refreshes; MFA challenge UI; forgot/reset pages; `/settings/security` page for password, MFA enrolment, and session management.

### Verification

- `backend`: `ruff check app` passes; `pytest` 18 passed / 2 failed. Both failures are pre-existing on commit `43a6fbd` (`test_vendor_invoice_approval_posts_accounts_payable`, `test_whatsapp_webhook_links_inbound_message_to_lead`) and are unrelated to auth.
- `frontend`: `npm run build` passes.
- Live smoke: backend health 200 with security headers; login sets refresh/CSRF cookies; cookie refresh with CSRF header returns a new access token; frontend `/login`, `/forgot-password`, and `/settings/security` served successfully.

### Deferred / residual gaps

- P4 remains deferred: SAML/OIDC federation, SCIM, FIDO2/WebAuthn, HIBP breach check, risk-based/conditional access.
- `REQUIRE_MFA_FOR_ADMINS` is configurable but not yet enforced during login; MFA is opt-in in this iteration.
- Email delivery is not configured; reset tokens are returned as `dev_token` only in `development`/`test`.
- Origin header validation and trusted-browser management are not implemented; CSRF uses double-submit cookies only.
- `mfa_secret` is stored as plain text in the database; move to envelope encryption before production rollout.
