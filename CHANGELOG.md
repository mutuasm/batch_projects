# Changelog

All notable changes to BatchProjects are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pre-1.0 versions are not listed — the schema was not stable.

---

## [1.0.0] — 2026-05-20

First release with a canonical, stable schema. Install fresh; no migration
path from pre-1.0 exists by design (no production data to migrate).

### Breaking changes

- **Renamed `BP Issue` → `BP Task`** (and all child tables)
  - `BP Issue Assignee` → `BP Task Assignee`
  - `BP Issue Link` → `BP Task Link`
  - `BP Issue Reference` → `BP Task Reference`
- **Field renames on `BP Task`**
  - `issue_key` → `task_key`
  - `issue_type` → `task_type`
  - `parent_issue` → `parent_task`
  - `linked_issue` / `linked_issue_key` / `linked_issue_title` / `linked_issue_status` → `linked_task` / `linked_task_key` / `linked_task_title` / `linked_task_status`
- **Field renames on `BP Activity`**
  - `issue` → `task`
  - `issue_key` → `task_key`
- **API endpoint renames** (all in `batch_projects.api.board`)
  - `create_issue` → `create_task`
  - `update_issue` → `update_task`
  - `get_issue` → `get_task`
  - `delete_issue` → `delete_task`
  - `query_issues` → `query_tasks`
  - `search_issues` → `search_tasks`
  - `update_issue_status` → `update_task_status`
  - `reorder_issues` → `reorder_tasks`
  - `add_issue_link` → `add_task_link`
  - `remove_issue_link` → `remove_task_link`
  - `move_issue_to_sprint` → `move_task_to_sprint`
- **Realtime event names** changed from `issue.*` to `task.*`
  - `issue.created` → `task.created`
  - `issue.updated` → `task.updated`
  - `issue.deleted` → `task.deleted`
  - `issue.status_changed` → `task.status_changed`
  - `issue.assigned` → `task.assigned`
  - `issue.unassigned` → `task.unassigned`
- **Frontend component renames**
  - `IssueDetail.vue` → `TaskDetail.vue`
  - `IssueCard.vue` → `TaskCard.vue`
  - `CreateIssue.vue` → `CreateTask.vue`
  - `IssueAttachments.vue` → `TaskAttachments.vue`
  - `IssueContextMenu.vue` → `TaskContextMenu.vue`

### Bug fixes

- **Task key race condition**: fixed duplicate key generation under concurrent
  inserts using MariaDB `LAST_INSERT_ID(expr)` connection-local atomicity.
  Removes the window where two tasks created simultaneously could get the same
  key (e.g. `PROJ-7` assigned to both).
- **`schema_version` increment**: operator-precedence bug caused `or 0 + 1`
  to evaluate as `or (0+1)`, always returning 1 for null values instead of
  incrementing. Fixed to `(or 0) + 1`.
- **`CreateProject.vue` casing**: was `Createproject.vue` — broke silently on
  case-sensitive Linux filesystems. Renamed with `git mv` to preserve history.
- **`TaskDetail.vue` missing imports**: `nextTick` and `toast` were used but
  not imported. Fixed.
- **Migration patch idempotency**: `migrate_to_workflow_states` omitted
  `issue_types` from the `frappe.get_all` fields list, causing it to
  unconditionally overwrite existing issue types on every run.

### Security

- **15 unauthenticated Team API endpoints** now require `_check_team_permission`
  or `_require_system_user`. Previously any unauthenticated request could read
  and mutate team data.
- **`create_project`, `search_tasks`, `get_dashboard`** audited and gated with
  `_require_system_user()` so website users cannot reach them.
- **Realtime broadcasts** scoped to project members + System Managers instead
  of broadcasting to all connected users. Prevents data leakage across
  projects.

### Behavior changes

- **Status validation now throws** instead of silently auto-correcting to an
  arbitrary state. Clients will receive an explicit error for invalid statuses.
- **Concurrent edit detection**: removed `ignore_version=True` from
  `update_task`. Concurrent edits to the same task now surface
  `TimestampMismatchError` instead of silently overwriting the earlier save.
- **Realtime recipient list cached** at 60 s TTL (via Redis) to avoid two DB
  queries per event emit. Bust with `invalidate_recipients(project)` after
  membership changes.

---

## [2.0.0] — 2026-08-31

Retargets BatchProjects to **Frappe/ERPNext v16**, removes the paid-plan and
gateway licensing model entirely, and makes BatchProjects the default Projects
module in ERPNext.

### Breaking changes

- **All paid tiers, licence keys and seat caps are removed.** Every feature is
  enabled on every install. The `starter/team/business/enterprise` ladder, the
  `feature → minimum tier` catalog, `X-BP-Tier` / `X-BP-Max-Users` header
  resolution and the 24h tier cache are gone from `entitlements.py`.
  - `require_feature()` / `is_feature_enabled()` remain as always-allow shims
    so historical call sites keep working; they never raise. ~70 call sites
    were removed outright.
  - `assert_seat_available()`, `assert_seats_available()`, `is_seated()`,
    `current_max_users()`, `current_tier()`, `current_packs()` and
    `before_member_insert()` are **removed**. Project/team membership is
    unlimited.
  - `get_entitlements()` keeps its response shape (the SPA bootstraps off it)
    but reports every feature enabled, `max_users: 0` (unlimited) and null
    licence/expiry fields.
- **The gateway licensing and identity layer is removed.**
  - `gateway_guard.py` is deleted, along with the `auth_hooks` identity
    handoff and `verify_gateway_request()` (removed from 16 modules).
  - `gateway_min_version` is removed from `hooks.py`.
  - The ReBAC push-down is removed: `_rebac_scope()` and its branches in
    `permissions.py` / `notification_permissions.py`, the write-side sync in
    `events.py` / `task_lifecycle.py` / `task_invariants.py`, and the
    `sync_rebac_state` rebuild endpoint. **Authorization is now enforced
    solely by BatchProjects' own project-scoped SQL permission model** — the
    same model every unverified request already fell back to.
  - `automation_engine()` always resolves to the in-process Python matcher.
- **Frontend:** the pricing page, plan catalog (`plans.json`), checkout,
  subscription and billing-portal API helpers are removed.
  `/workspace/pricing` now redirects to `/workspace`. The entitlements store's
  `can()` always returns true and `showUpgradePrompt()` is a no-op.

### Added

- **BatchProjects is the default ERPNext Projects module.**
  - `doctype_list_js` redirects the stock `Project` and `Task` desk list views
    into the SPA, so the BP project list is the default project list. Append
    `?desk=1` to load the stock ERPNext list for imports, bulk edits or Report
    Builder; the choice persists for the browser session.
  - A first-class v16 `Workspace Sidebar` record
    (`batch_projects/workspace_sidebar/batchprojects.json`) with Plan / Work /
    Insight / People / Records / Settings sections.
  - `setup/projects_module.py` re-points ERPNext's own `Projects` sidebar at
    the SPA, wired to `after_migrate` because that record is `standard: 1` and
    is re-imported (reverting the override) on every `bench migrate`. It
    suppresses `WorkspaceSidebar.export_sidebar()` via `frappe.flags.in_import`
    so it never rewrites erpnext's own JSON on a developer_mode bench.
  - ERPNext's Timesheet, Activity Type/Cost, Projects Settings and reports are
    deliberately left untouched — costing and billing stay in ERPNext.

### Changed

- **Test base class migrated to `frappe.tests.IntegrationTestCase`** (40 files,
  121 classes), off the deprecated `frappe.tests.utils.FrappeTestCase`. This is
  required on v16, not cosmetic: v16's test runner dispatches `FrappeTestCase`
  into the `old-frappe-test-class-category`, whose compat preparation runs
  `compat_preload_test_records_upfront()` — an eager walk of every test module's
  dependency doctypes. That walk raises `DoesNotExistError` for any doctype
  belonging to an app that isn't installed (here `Payment Gateway`, from the
  `payments` app), aborting the run *after* the tests themselves pass.
  `IntegrationTestCase` lands in the plain `integration` category and generates
  records only for module-declared `EXTRA_TEST_RECORD_DEPENDENCIES`, of which
  this app declares none.
- `test_ignore` renamed to `IGNORE_TEST_RECORD_DEPENDENCIES` in the two
  doctype-folder test modules (old name warns on v16, removed in v17).
- **CI now installs the `payments` app** (test environment only — not an app
  dependency, and nothing here imports it). ERPNext's `Payment Gateway Account`
  links to `Payment Gateway`, which lives in `payments`; frappe's test-record
  dependency walker resolves that link and aborts the run with
  `DoesNotExistError` when the app is absent. ERPNext's own CI installs it for
  the same reason. Pruning the dependency instead was not viable: `Payment
  Gateway Account` converges from 7 of BP Project's 11 direct links (all via
  `Subscription Plan`), so the ignore list would have had to drop Company,
  Customer, Project, Sales Order, Quotation, Opportunity and Lead — precisely
  the records those tests need.
- `frappe`/`erpnext` dependency pins moved to `>=16.0.0,<17.0.0`.
- `requires-python` raised to `>=3.14` (Frappe v16 requires 3.14–3.15);
  frontend `engines.node` set to `>=24`.
- CI: Python 3.14, Node 24, `FRAPPE_BRANCH`/`ERPNEXT_BRANCH` `version-16`;
  integration branch `develop-15` → `develop-16`. MariaDB stays on 10.6 —
  v16's documented floor, and 11.x breaks the job's `mysqladmin` health check.
- Branch model retargeted to the v16 line throughout the docs.

- `deploy/gateway-setup.md` is **removed**. It documented licence keys, a
  60-day trial, a license server and server-side revocation — none of which
  exist any more. `deploy/README.md` now documents the six `site_config.json`
  keys the code actually reads for the optional side-car, all fail-closed.

### Notes

- The app's **display name is now "Projects"** (`app_title`, apps-screen entry,
  SPA chrome and docs). The Frappe app name stays `batch_projects`, as do the
  module name, the `BP ` doctype prefixes and every API path — there is no
  `bench rename-app`, so renaming the package would leave existing installs
  with no migration path. The `Workspace Sidebar` record also keeps its
  `BatchProjects` title: that doctype autonames from `title` (`field:title`)
  and erpnext already owns `name="Projects"`. Entries above this release keep
  the old name deliberately — they record what shipped at the time.

- Existing `/app/<doctype>/<name>` deep links continue to work: v16 moved the
  desk to `/desk` but ships an `/app/(.*)` → `/desk/\1` redirect.
- The committed SPA bundle under `batch_projects/public/frontend/` is rebuilt
  in this release; CI's `frontend-dist-drift` job enforces that it matches a
  fresh `yarn build` of `frontend/src`.
- The optional automation side-car (`bridge.py`) is retained for durable
  automation timers and realtime fan-out. It gates no features and no-ops when
  `bp_bridge_url` is unset.

## [Unreleased]

- Sprint Mode toggle (project-level setting)
- `api/board.py` decomposition into focused modules
- `TaskDetail.vue` composable extraction
- Workflow templates per vertical (software, services, construction)
