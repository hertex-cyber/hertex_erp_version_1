# Role-based menu control — implementation plan

**Status:** implemented / locally verified

**Prepared:** 2026-11-21

**Owner:** Jishnu

**Related docs:** `16-IDENTITY.md`, `16-IDENTITY-AUTH-IMPLEMENTATION-PLAN.md`, `15-SETTINGS.md`

---

## 1. Objective

Replace hardcoded, always-visible navigation with backend-owned role menu access:

- each role has an explicit set of allowed menu modules;
- administrators can inspect and edit menu access for custom roles;
- `/auth/permissions` returns the effective menu set and module feature flags for the signed-in user;
- every navigation surface—sidebar, command palette, settings subnav/cards, dashboard shortcuts, finance shortcuts and assistant shortcuts—uses one shared access helper;
- direct URL access to a denied module shows an access-denied page instead of rendering the module.

Superusers and roles with `*` keep full access. Module feature flags can still hide a module even for an otherwise authorised role.

---

## 2. Current state evidence

- `frontend/src/lib/nav.js:57` defines 126 hardcoded nav entries across 18 groups.
- `frontend/src/components/AppShell.jsx:43` filters the sidebar only by `item.permission`; `AppShell.jsx:193` does the same for the command palette.
- `frontend/src/App.jsx:183` `ProtectedRoute` only checks authentication, not module permission.
- `frontend/src/components/settings/SettingsSubnav.jsx:4`, `frontend/src/pages/settings/SettingsHubPage.jsx:6`, `frontend/src/pages/Dashboard.jsx:319`, `frontend/src/pages/Dashboard.jsx:355`, `frontend/src/pages/FinanceDashboard.jsx:8` and `frontend/src/pages/Assistant.jsx:347` render shortcuts without access checks.
- `backend/app/modules/identity/schemas.py:210` `PermissionSummary` contains permissions and roles only.
- `backend/app/modules/identity/router.py:529` `/auth/permissions` returns permission codes but no menu access or feature flags.
- `backend/app/core/permissions_catalog.py:220` has 11 role templates but no menu access templates.
- `backend/app/modules/settings/registry.py:546` defines `features.module.projects.enabled`, `features.module.pos.enabled`, `features.module.marketing.enabled` and `features.module.support.enabled`, but the frontend never consumes them.
- `backend/app/modules/settings/router.py:229` `/settings/features` requires `settings.setting.read`, so it cannot be the only source for every role's navigation.

---

## 3. Target design

### 3.1 Backend source of truth

Add `backend/app/core/menu_catalog.py` with:

- canonical menu keys: `dashboard`, `assistant`, `crm`, `sales`, `pos`, `inventory`, `warehouse`, `procurement`, `finance`, `hr`, `projects`, `support`, `marketing`, `settings`;
- default role menu access for all 11 built-in role slugs;
- validation helper for menu keys;
- path-to-menu inference used by navigation tests and route guards.

Add `roles.menu_keys` as a JSON column defaulting to an empty list. Built-in role templates seed their defaults; custom roles are editable by administrators.

### 3.2 Authentication payload

Extend `PermissionSummary` with:

- `menus: list[str]` — `["*"]` for full access, otherwise the union of active role menu keys;
- `feature_flags: dict[str, bool]` — effective `features.*` values resolved for the current tenant/user.

Extend `/auth/permissions` to resolve these values server-side. It must remain accessible to every authenticated user.

### 3.3 Role administration

Add `GET /roles/menu/catalog` for the menu catalog.

Extend create/update role payloads with `menu_keys`. Unknown keys are rejected. System roles remain non-editable, as today.

### 3.4 Frontend access model

Extend the Zustand auth store with `menus` and `featureFlags`, plus:

- `canMenu(key)` — true for `*` or an allowed key;
- `hasFeature(key)` — false only when the backend explicitly returns false;
- `canNavigate(descriptor)` — combines `can(permission)`, `canMenu(menu)` and `hasFeature(feature)`.

Annotate every nav item with a derived `menu` key and optional `feature` key. A single `filterNavGroups` helper is used by all navigation surfaces.

Add a route access guard that resolves the closest matching nav descriptor and denies direct navigation when the user lacks menu access, permission or the feature flag.

---

## 4. Implementation steps

1. Add backend menu catalog, role menu templates and migration for `roles.menu_keys`.
2. Seed built-in role menu defaults and expose menu catalog/role menu editing APIs.
3. Extend `/auth/permissions` with effective `menus` and `feature_flags`.
4. Extend frontend auth store and navigation helpers.
5. Apply shared filtering to every navigation surface.
6. Add direct-route access guard and access-denied page.
7. Add backend, frontend source-contract/unit, and Playwright coverage.
8. Run backend tests, frontend tests, frontend build and targeted E2E.

---

## 5. Acceptance criteria

- A `sales` role cannot see or open `finance`, `hr`, `projects`, `settings`, `warehouse`, `marketing` or `support` menus.
- A `warehouse` role can see `inventory`, `warehouse`, `procurement` and `sales` fulfilment but not `finance` or `hr`.
- A `team_member` role sees dashboard, assistant and project menus only.
- A custom role with `menu_keys: ["crm"]` sees only CRM navigation, subject to its permissions.
- Superuser sees everything except modules explicitly disabled by feature flag.
- Disabling `features.module.projects.enabled` hides project menus for every role.
- All secondary settings links, hub cards, dashboard shortcuts, finance shortcuts and assistant shortcuts obey the same access model.
- Direct navigation to a denied route does not render the protected page.
- Backend tests, frontend tests, frontend build and Playwright menu-access test pass.

---

## 6. Workspace scoping hardening

- `GET /users` now defaults every caller to their own workspace, including superadmins; explicit `tenant_scope=all` is required for a global admin list.
- Non-superusers cannot override `tenant_id`; superadmins may filter or create users in an explicit workspace.
- The Team screen sends the current workspace filter, shows a Workspace column and superadmin-only workspace controls, and hides account creation in another tenant from non-superusers.
- Demo credential autofill is shown only in local development or when `VITE_SHOW_DEMO_LOGIN=true`.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Legacy roles have no `menu_keys` | Migration defaults to empty; built-in roles are reseeded; unknown custom roles fall back to permission-derived menus only during transition |
| Menu keys drift between backend and frontend | One backend catalog plus path-based frontend derivation; source-contract test checks coverage |
| Feature flag resolution fails | `/auth/permissions` fails closed only for explicit `false`; missing flags do not hide modules |
| Route guard hides legitimate detail pages | Exact route match first, then longest prefix match; unmatched routes remain accessible |
| Admin locked out by a bad custom role | Superuser bypass is absolute; system roles remain non-editable |
| Direct URL exposes data | Frontend guard is UX only; backend route-level permission dependencies remain authoritative |
