# Deploying Projects

Projects is a single, fully open edition — every feature is enabled on
every install. There is nothing to license and no paid tier, so a deployment
is just a Frappe app install.

1. **Projects** — the Frappe application and Vue interface. Installed
   with a standard `bench get-app`, and works anywhere Frappe does:
   self-hosted (Docker or bare bench) or on Frappe Cloud. See the
   [root README](../README.md#quick-start). Starting from nothing?
   [`docker-compose.selfhost.yml`](docker-compose.selfhost.yml) provisions
   ERPNext and Projects together.
2. **An optional automation side-car** — Projects can hand durable
   automation timers and realtime fan-out to a small external service. It is
   entirely optional, gates no features, and the app runs fully standalone
   without it. See [Optional side-car](#optional-side-car) below.

## Compatibility

| Relationship | Mechanism | How it's enforced |
|---|---|---|
| **Projects ⨯ ERPNext/Frappe core** | A dedicated git branch per ERPNext release line — `version-16` targets ERPNext v16 (Python 3.14+, Node 24+); `version-15` remains for the v15 line. | Selected at install time (`bench get-app --branch version-16`). |

Select the `version-NN` branch matching your ERPNext installation. The app
also declares its supported range in `pyproject.toml`
(`frappe`/`erpnext` `>=16.0.0,<17.0.0`), which `bench` enforces on install.

## Deployment scenarios

| Environment | How |
|---|---|
| Self-hosted, Docker | `bench get-app` inside the bench container |
| Self-hosted, bare bench | `bench get-app`, no containerization |
| Frappe Cloud | Standard Frappe Cloud application install |

## Replacing ERPNext's Projects module

Installing Projects on ERPNext v16 makes it the default Projects
experience — the stock `Project` and `Task` desk lists redirect into the
Projects SPA, Projects gets its own workspace sidebar, and
ERPNext's `Projects` sidebar is re-pointed at it (re-asserted after every
`bench migrate`, since that record is owned by erpnext and re-imported on
each sync).

ERPNext's own Timesheet, Activity Type/Cost, Projects Settings and Projects
reports are deliberately left untouched — costing and billing stay in
ERPNext.

To reach the stock ERPNext list for an import, a bulk edit or Report
Builder, append `?desk=1` (e.g. `/desk/project?desk=1`); the preference
persists for the rest of the browser session.

## Optional side-car

These are the only `site_config.json` keys Projects reads for the
optional external service. All are unset by default, and every one of them
fails closed — absent config means the feature simply runs in-process or not
at all, never that a check is skipped.

| Key | Read by | Effect when unset |
|---|---|---|
| `bp_bridge_url` | `bridge.py` | Durable timer registration and realtime fan-out no-op; automations still evaluate in-process. |
| `bp_bridge_internal_url` | `bridge.py` | Falls back to `bp_bridge_url`. Only needed when the backend process and the browser reach the service at different addresses. |
| `bp_scheduler_ingest_token` | `bridge.py` | Required alongside `bp_bridge_url`; without both, registration no-ops. |
| `bp_gateway_shared_secret` | `api/credentials.py` | `get_credential_secret` refuses every request. This is an HMAC boundary protecting decrypted integration credentials — not a licence check. |
| `bp_bridge_bootstrap_secret` | `api/session.py` | `mint_bridge_token` refuses to mint. |
| `bp_automation_engine` | `entitlements.py` | Defaults to the in-process Python matcher, which is the only engine shipped. |

`api/gateway.py` exposes a System-Manager-only `configure` endpoint that
writes `bp_bridge_url`, `bp_scheduler_ingest_token`,
`bp_gateway_shared_secret` and `bp_bridge_bootstrap_secret`, so a side-car
installer can finish setup without shell access (notably on Frappe Cloud).
