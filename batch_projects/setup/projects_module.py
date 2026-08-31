"""
batch_projects/setup/projects_module.py
───────────────────────────────────────
Makes BatchProjects the default Projects module in ERPNext v16.

Three things cooperate to do this; this module is the third.

1. `doctype_list_js` (hooks.py) redirects the stock `Project` and `Task` list
   views into the BatchProjects SPA. That is the one that actually matters —
   it catches every route into the stock lists (workspace cards, awesome-bar,
   pasted `/desk/project` links, ERPNext's own internal links), not just the
   nav.
2. `batch_projects/workspace_sidebar/batchprojects.json` gives BatchProjects
   its own first-class v16 module sidebar.
3. This module re-points ERPNext's *own* `Projects` sidebar at BatchProjects,
   so the nav agrees with where the links actually land.

Why this runs on `after_migrate` and not once at install
────────────────────────────────────────────────────────
ERPNext's `Projects` Workspace Sidebar is a `standard: 1` record, which means
`bench migrate` re-imports it from erpnext's own JSON on every single run and
silently reverts anything we changed. Frappe runs `after_migrate` hooks after
that sync, so re-asserting here is what makes the override survive upgrades.
It is written to be idempotent and safe to run any number of times.

What it deliberately does NOT do
────────────────────────────────
It leaves ERPNext's Timesheet / Activity Type / Activity Cost / Projects
Settings entries and every Projects report alone. Those are the native ERP
financial surfaces BatchProjects integrates with rather than replaces — the
whole point of the app is that costing and billing stay in ERPNext. It also
never deletes rows: entries are re-pointed in place, so removing this app (or
one `bench migrate` after deleting this hook) restores stock behaviour.
"""

import frappe

# ERPNext's Projects sidebar entries we take over, and where they now go.
# Keyed by (link_type, link_to) as ERPNext ships them so we only ever rewrite
# a row we actually recognise — never a customer's own added entry.
_REPOINT = {
    ("DocType", "Project"): {
        "label": "Projects",
        "url": "/workspace/all",
        "icon": "projects",
    },
    ("DocType", "Task"): {
        "label": "My Tasks",
        "url": "/workspace/my-tasks",
        "icon": "list-todo",
    },
    ("Workspace", "Projects"): {
        "label": "Overview",
        "url": "/workspace",
        "icon": "layout-dashboard",
    },
    ("Dashboard", "Project"): {
        "label": "Dashboards",
        "url": "/workspace/dashboards",
        "icon": "chart",
    },
}

_SIDEBAR_NAME = "Projects"


def override_erpnext_projects_module():
    """Re-point ERPNext's `Projects` sidebar at the BatchProjects SPA.

    Idempotent. No-ops cleanly when erpnext isn't installed, when the record
    doesn't exist (older/newer ERPNext that names it differently), or when the
    override is already in place.

    Never raises. This runs from `after_install` and `after_migrate`, where an
    exception would abort the app install or the whole `bench migrate` — an
    absurd price for a navigation tweak. ERPNext restructures these records
    between releases, so a future rename must degrade to "nav not re-pointed",
    never "site cannot migrate". The redirect in
    `public/js/erpnext_projects_redirect.js` is what actually makes
    BatchProjects the default Projects view, and it does not depend on this.
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

    changed = False
    for item in doc.items:
        if item.type != "Link":
            continue
        target = _REPOINT.get((item.link_type, item.link_to))
        if not target:
            continue

        item.link_type = "URL"
        item.url = target["url"]
        item.label = target["label"]
        item.icon = target["icon"]
        # A Dynamic Link field validates against link_type; leaving the old
        # DocType/Workspace name behind on a URL row fails validation on save.
        item.link_to = None
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
        "Re-pointed ERPNext's Projects sidebar at the BatchProjects SPA"
    )
