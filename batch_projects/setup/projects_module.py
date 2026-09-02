"""
batch_projects/setup/projects_module.py
───────────────────────────────────────
Adds the two Jira-style views to ERPNext's own `Projects` sidebar.

Three things cooperate to make Projects read as a Jira-style module; this is
the third.

1. `doctype_js` / `doctype_list_js` (hooks.py) give native Project its
   Jira-shaped navigation: opening a project goes to its task board, with Tree,
   List, Gantt and Backlog one click away. See public/js/project_jira.js.
2. `setup/jira_workspace.py` creates the Kanban Board on Task (grouped by
   status) and the Epic/Story/Task/Bug/Sub-task issue types.
3. This module adds `Task Board` and `Task Tree` entries to ERPNext's sidebar,
   so the nav offers the same two views.

Additive, not a takeover
────────────────────────
An earlier revision REPLACED ERPNext's Project/Task links with `/workspace`
SPA URLs. The SPA is being retired, so that would aim the nav at URLs about to
404 — and rewriting links on a doctype another app owns is the more fragile
choice regardless. Everything ERPNext ships (Project, Task, Timesheet, Activity
Type/Cost, every Projects report, Projects Settings) is left exactly as it is;
those are the real destinations now. No row is ever deleted.

Why this runs on `after_migrate` and not once at install
────────────────────────────────────────────────────────
ERPNext's `Projects` Workspace Sidebar is a `standard: 1` record, which means
`bench migrate` re-imports it from erpnext's own JSON on every single run and
silently drops anything we appended. Frappe runs `after_migrate` hooks after
that sync, so re-asserting here is what makes the additions survive upgrades.
Idempotent and safe to run any number of times.
"""

import frappe

# Extra entries added to ERPNext's own `Projects` sidebar: the two views that
# make it read as a Jira-style module. Everything ERPNext already lists
# (Project, Task, Timesheet, Activity Type/Cost, reports, settings) is left
# exactly as shipped — those are the real destinations now.
#
# This used to REPLACE those links with /workspace SPA URLs. The SPA is being
# retired, so pointing a sidebar at it would aim the nav at URLs that are about
# to 404. Additive is also simply safer against a doctype another app owns.
_EXTRA_ITEMS = [
    {
        "label": "Task Board",
        "type": "Link",
        "link_type": "URL",
        "url": "/desk/task/view/kanban/Projects Board",
        "icon": "grid-2x2-check",
    },
    {
        "label": "Task Tree",
        "type": "Link",
        "link_type": "URL",
        # Task is `is_tree: 1` on parent_task, so this is the native
        # epic -> story -> sub-task hierarchy, not something we render.
        "url": "/desk/task/view/tree",
        "icon": "list-tree",
    },
    {
        "label": "Project WBS",
        "type": "Link",
        "link_type": "URL",
        # Project-level hierarchy. Unlike Task, native Project is NOT a nested
        # set, so there is no tree view for it — this report renders
        # custom_parent_project as an indented breakdown instead.
        "url": "/desk/query-report/Project WBS",
        "icon": "organization",
    },
]

_SIDEBAR_NAME = "Projects"


def override_erpnext_projects_module():
    """Add the Task Board / Task Tree entries to ERPNext's `Projects` sidebar.

    Idempotent. No-ops cleanly when erpnext isn't installed, when the record
    doesn't exist (an ERPNext release that names it differently), or when the
    entries are already present.

    Never raises. This runs from `after_install` and `after_migrate`, where an
    exception would abort the app install or the whole `bench migrate` — an
    absurd price for a navigation tweak. ERPNext restructures these records
    between releases, so a future rename must degrade to "nav entries missing",
    never "site cannot migrate". The Jira navigation in
    `public/js/project_jira.js` is what actually makes the board the default
    way into a project, and it does not depend on this.
    """
    try:
        _override_erpnext_projects_module()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "batch_projects: could not re-point ERPNext's Projects sidebar",
        )


def _override_erpnext_projects_module():
    if "erpnext" not in frappe.get_installed_apps():
        return

    # The Workspace Sidebar doctype is v16+. On anything older there is nothing
    # to re-point and the DocType lookup itself would throw.
    if not frappe.db.exists("DocType", "Workspace Sidebar"):
        return

    if not frappe.db.exists("Workspace Sidebar", _SIDEBAR_NAME):
        return

    try:
        doc = frappe.get_doc("Workspace Sidebar", _SIDEBAR_NAME)
    except frappe.DoesNotExistError:
        return

    have = {(row.label or "").strip() for row in doc.items}
    changed = False
    for item in _EXTRA_ITEMS:
        if item["label"] in have:
            continue
        doc.append("items", dict(item))
        changed = True

    if not changed:
        return

    # WorkspaceSidebar.before_save() calls export_sidebar(), which writes the
    # record back out to `<app>/workspace_sidebar/<title>.json` whenever
    # `app` + `standard` are set and developer_mode is on. This record's app is
    # *erpnext* — so on any developer_mode bench (every contributor's, and
    # every CI bench) saving it would rewrite erpnext's own projects.json and
    # leave the erpnext checkout dirty, which is not ours to do. That export is
    # skipped when `frappe.flags.in_import` is set, so we set it for the
    # duration of the save and restore whatever was there before.
    previous_in_import = frappe.flags.in_import
    frappe.flags.in_import = True
    try:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
    finally:
        frappe.flags.in_import = previous_in_import

    frappe.logger("batch_projects").info(
        "Added Task Board / Task Tree entries to ERPNext's Projects sidebar"
    )
