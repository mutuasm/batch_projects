<p align="center">
  <a href="https://batchprojects.com">
    <img src="frontend/public/images/bp-logo-new.png" alt="BatchProjects Logo" width="80" height="80">
  </a>
</p>

<h1 align="center">BatchProjects</h1>

<p align="center">
  <b>Enterprise-grade project management, built natively into ERPNext.</b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL v3"></a>
  <a href="https://frappeframework.com"><img src="https://img.shields.io/badge/Frappe-v16-0089FF.svg" alt="Frappe v16"></a>
  <a href="https://github.com/BatchNepal/batch_projects/stargazers"><img src="https://img.shields.io/github/stars/BatchNepal/batch_projects?style=flat" alt="GitHub Stars"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
</p>

---

<p align="center">
  <img src="frontend/public/images/bp-hero.png" alt="BatchProjects Board View" width="100%">
</p>

## Overview

Meet BatchProjects, an open-source project management app for your team built natively for ERPNext.

Experience the freedom of managing your projects in a fast, modern, and collaborative interface while keeping all your financials, timesheets, and accounting inside ERPNext. No more exporting, no more manual syncing, and no more context switching between multiple tools.

---

## Key Features

### 🚀 Modern Delivery Experience *(Efficiency in mind)*

* **Board, Views & Tasks:** Drag-and-drop Kanban boards, Listview, Gantt Chart, backlogs, sprint cycles, and Projects templates feature. Shareable boards, saved view states, and real-time multi-user sync for live collaboration. Support for both opt-in Agile/Scrum (sprints, story points) and structured Waterfall/Kanban workflows.
* **Infinitely Customizable Records:** Create per-project custom fields, custom statuses, and role-based access rules without touching the underlying Frappe schemas.
* **Timesheets & Costing:** Log time against tasks to generate timesheets and monitor project margins and utilization in real time.
* **Automations and Workflows:** Trigger webhooks, push notifications, and custom workflows based on task events. Visual rule builder for automating task events, with webhook triggers and push notifications.
* **Dashboards & Reportings:** Scheduled or realtime reports and customize dashboard widgets to track project progress, profitability, and utilization.
* **Scalable and Performant by Design:** Horizontally scalable on standard Frappe workers, with list queries pushed down to SQL so large task volumes stay responsive.
* **Enterprise Integrations:** Seamlessly connect with other enterprise tools and services for a unified workflow.
* **Interactive Views:** Switch seamlessly between Kanban Boards, Backlogs, Sprints, and Gantt charts with saved view states.
* **Fast Frontend:** Built on Vue 3 and Pinia for near-instant rendering and snappy interaction.
* **Real-Time & Collaboration:** WebSocket-based multi-user sync for live updates across all connected clients.
* **Projects Templates:** Create and reuse project templates with pre-defined tasks, workflows, and custom fields for faster project setup. Leverage templates to standardize processes and ensure consistency across projects.
* **Fully Self-Hosted:** Runs inside your own bench with no licence check and no data leaving your infrastructure. An optional Go side-car can take over durable automation timers and the realtime broadcast plane; unconfigured, the app degrades cleanly to Frappe's own scheduler.

### 💼 Native ERP Financial Engine

* **First-Class ERP Links:** Attach tasks directly to Sales Orders, Purchase Orders, Expense Claims, and Accounting Dimensions.
* **Real-Time Margin Tracking:** Log time against tasks and roll it up automatically into project profitability and budget vs. actual reports.
* **Native Timesheets:** Billable hours sync straight into ERPNext Payroll and Sales Invoices with zero export/import steps.
* **One Source of Truth:** Delivery teams work in a high-speed UI while accounting teams get precise financial visibility in ERPNext.
* **Customizable Costing:** Track labor, materials, and overhead costs per project with flexible accounting dimensions.
* **Automated Billing:** Generate invoices based on logged time and linked Sales Orders, reducing manual billing errors.
* **Budget Monitoring:** Monitor project budgets in real time, with alerts for overruns and underutilization.
* **Direct ERPNext Integration:** Leverage ERPNext's robust accounting and inventory management features for comprehensive project oversight.

---

## Licensing & Architecture

BatchProjects is a single, fully open edition. **Every feature is enabled on
every install** — there are no paid tiers, no licence keys, no seat caps and no
feature gates. Kanban boards, backlogs, sprints, Gantt, automations, webhooks,
dashboards, intake forms, portfolio, goals, audit log and ERPNext billing
write-back are all part of the AGPL-3.0 app.

Previous releases used an open-core model in which a proprietary `bp-gateway`
companion service unlocked premium features and asserted a licence tier. As of
**v2.0.0 that model is gone**: the tier ladder, seat enforcement and the
gateway's licensing/identity layer have been removed from the app, and
authorization is enforced entirely by BatchProjects' own project-scoped
permission model inside Frappe.

---

## Use Cases

* **Agencies & Consultancies:** Track project execution alongside Sales Orders, ensuring billable hours hit client invoices accurately.
* **Construction & Engineering:** Tie task progress to Purchase Orders and subcontractor expenses for precise budget monitoring.
* **Manufacturing & Operations:** Manage delivery phases tied to ERPNext production schedules and procurement.
* **Software Development Teams:** Use Agile/Scrum or Waterfall workflows with real-time collaboration and automated reporting.
* **Professional Services:** Monitor project profitability, resource utilization, and automate client billing directly from ERPNext.
* **Education & Research:** Manage research projects, grant budgets, and academic collaborations with integrated financial tracking.
* **Nonprofits & NGOs:** Track program delivery, donor-funded projects, and grant compliance with real-time financial visibility.

---

## Quick Start (Core App)

BatchProjects runs as a standard Frappe app on **Frappe v16 / ERPNext v16**
(Python 3.14+, Node 24+ for frontend development).

```bash
# Navigate to your bench directory
cd ~/frappe-bench

# Get the app
bench get-app https://github.com/BatchNepal/batch_projects --branch version-16

# Install on your site
bench --site your-site.local install-app batch_projects

# Run migrations
bench --site your-site.local migrate
```

That's the entire install — no Node, no build step, no external service, and
nothing to license. The `version-16` branch tracks ERPNext v16; see
[`deploy/README.md`](deploy/README.md) for the full version-compatibility
story and how branch naming maps to ERPNext versions going forward.

For local frontend development, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Built with

[Frappe Framework](https://frappeframework.com) · [ERPNext](https://erpnext.com) · [Vue 3](https://vuejs.org) · [Pinia](https://pinia.vuejs.org) · Python

## Replacing ERPNext's stock Projects module

On ERPNext v16, installing BatchProjects makes it the **default Projects
experience**:

* The stock `Project` and `Task` desk list views redirect into the
  BatchProjects SPA, so the BP project list is the default project list.
* BatchProjects gets its own first-class v16 workspace sidebar.
* ERPNext's own `Projects` sidebar is re-pointed at BatchProjects on install
  and re-asserted after every `bench migrate`.

ERPNext's native financial surfaces — Timesheet, Activity Type/Cost, Projects
Settings and every Projects report — are deliberately left alone; costing and
billing stay in ERPNext, which is the whole point of the integration.

Need the raw ERPNext list for an import, a bulk edit or Report Builder? Append
`?desk=1` (e.g. `/desk/project?desk=1`) and the stock view loads for the rest
of the browser session.

See [`deploy/README.md`](deploy/README.md) for the deployment guide.

## License

BatchProjects — the Frappe app and the Vue frontend, everything in this
repo — is licensed under the **GNU Affero General Public License v3.0**
(AGPL-3.0-only). See [`LICENSE`](LICENSE).

The practical implication of AGPL: if you modify this app and run it as a
network service for others (e.g. offer it as SaaS), you must make your
modified source available to those users. Just self-hosting it for your own
company, unmodified or modified, carries no such obligation beyond attribution.

Everything needed to run BatchProjects is in this repository under that one
license, and nothing about the app is gated behind a licence any more.

One optional integration point remains: the app can hand durable automation
timers and realtime fan-out to an external side-car when `bp_bridge_url` is
configured in `site_config.json`. It is entirely optional, gates no features,
and the app runs fully standalone without it.

## Contributing

PRs welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for the branch model,
dev setup, and CI requirements. Security issues: see
[`SECURITY.md`](SECURITY.md), please don't file those as public issues.

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md).
