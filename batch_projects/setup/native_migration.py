"""
batch_projects/setup/native_migration.py
────────────────────────────────────────
Stage 3b: copy existing `BP Project` / `BP Task` rows into ERPNext's native
`Project` / `Task`, recording the mapping so the migration is idempotent and so
the 34 satellite doctypes can be retargeted afterwards.

Ordering matters and is not negotiable: the satellites (BP Sprint.project,
BP Task Assignee.parent, BP Milestone.project, …) hold BP row names in Link
fields. Retargeting those Links to `Project`/`Task` before the native rows
exist would fail link validation on every satellite row. So data first, schema
retarget second.

The mapping anchors are ordinary Link fields on our own doctypes —
`BP Project.erpnext_project` (which already existed for the old bridge) and
`BP Task.erpnext_task` (added for this). A row that already points at a live
native row is skipped, so this is safe to re-run.

Three value translations are needed, because the BP and native vocabularies
genuinely differ rather than merely being spelled differently.

Project status
    BP uses Active / Archived / On Hold; native uses Open / Completed /
    Cancelled — no overlap at all. Native carries the "is this project live"
    axis separately in its own `is_active` field, so the pair is expressible
    without inventing anything: On Hold becomes Open + is_active No.

Task status
    BP task status is free text: each project defines its own workflow states
    in `BP Project.workflow_states`. Native `Task.status` is a closed Select
    and cannot hold arbitrary names. But BP states already carry a category
    (see api/board.py — `unstarted`/`started`/`completed`/`cancelled`), which
    is exactly Jira's status-category model, so the translation is principled
    rather than guesswork. The project's own state *name* is preserved in
    `custom_status_label`, so nothing is silently lost: native status drives
    the board, reporting and progress; the label is what a human reads.

    What IS lost: per-project board columns. A single shared Frappe Kanban
    Board groups on one Select field, so lanes are the native seven for every
    project. That capability does not survive the move to desk views.

Task priority
    BP uses Jira's five (Highest…Lowest); native has four (Low/Medium/High/
    Urgent). Highest maps to Urgent; Lowest collapses into Low, which is the
    only lossy step here and affects ordering only, not behaviour.

Child tables are deliberately NOT copied here. `custom_assignees`,
`custom_links`, `custom_references`, `custom_members` and
`custom_custom_field_links` are rows in satellite doctypes, and those are
retargeted as a set once every parent has a native counterpart — copying half
of them mid-migration would leave two partial sources.
"""

import frappe

from batch_projects.setup.native_fields import CUSTOM_FIELDS, NATIVE_FIELD_MAP

# BP workflow-state category -> native Task.status. The four categories are
# validated in api/board.py; anything unrecognised is already coerced to
# "unstarted" there, so this table is total.
_CATEGORY_TO_TASK_STATUS = {
    "unstarted": "Open",
    "started": "Working",
    "completed": "Completed",
    "cancelled": "Cancelled",
}

# BP Project.status -> (native Project.status, native Project.is_active)
_PROJECT_STATUS = {
    "Active": ("Open", "Yes"),
    "On Hold": ("Open", "No"),
    "Archived": ("Completed", "No"),
}

_TASK_PRIORITY = {
    "Highest": "Urgent",
    "High": "High",
    "Medium": "Medium",
    "Low": "Low",
    "Lowest": "Low",
}

_TABLE_TYPES = {"Table", "Table MultiSelect"}


def _scalar_custom_fields(doctype):
    """custom_* fieldnames to copy directly, excluding child tables."""
    return [
        row["fieldname"]
        for row in CUSTOM_FIELDS.get(doctype, [])
        if row.get("fieldtype") not in _TABLE_TYPES
    ]


def _copy_values(bp_doc, native_doc, doctype):
    """Copy BP values across, honouring NATIVE_FIELD_MAP first."""
    for bp_field, native_field in NATIVE_FIELD_MAP.get(doctype, {}).items():
        if not native_field:
            continue  # meaningless under the native model (e.g. erpnext_project)
        value = bp_doc.get(bp_field)
        if value not in (None, ""):
            native_doc.set(native_field, value)

    for fieldname in _scalar_custom_fields(doctype):
        bp_field = fieldname[len("custom_") :]
        value = bp_doc.get(bp_field)
        if value not in (None, ""):
            native_doc.set(fieldname, value)


def _workflow_categories(bp_project_name):
    """{state name: category} for a BP project, via the app's own normalizer."""
    from batch_projects.api.board import _normalize_workflow_states

    raw = frappe.db.get_value("BP Project", bp_project_name, "workflow_states")
    return {
        str(s.get("name")): str(s.get("category") or "unstarted").lower()
        for s in _normalize_workflow_states(raw)
    }


def _existing_target(bp_doctype, bp_name, anchor_field, native_doctype):
    """The native row this BP row already maps to, if it is still there."""
    target = frappe.db.get_value(bp_doctype, bp_name, anchor_field)
    if target and frappe.db.exists(native_doctype, target):
        return target
    return None


def migrate_project(bp_name):
    """Return the native Project for a BP Project, creating it if needed."""
    existing = _existing_target("BP Project", bp_name, "erpnext_project", "Project")
    if existing:
        return existing

    bp = frappe.get_doc("BP Project", bp_name)
    status, is_active = _PROJECT_STATUS.get(bp.get("status"), ("Open", "Yes"))

    native = frappe.new_doc("Project")
    # project_name and company are mandatory on native Project.
    native.project_name = bp.get("project_name") or bp_name
    native.company = bp.get("company") or frappe.defaults.get_global_default("company")
    native.status = status
    native.is_active = is_active
    _copy_values(bp, native, "Project")
    native.insert(ignore_permissions=True)

    frappe.db.set_value(
        "BP Project", bp_name, "erpnext_project", native.name, update_modified=False
    )
    return native.name


def migrate_task(bp_name, project_map=None):
    """Return the native Task for a BP Task, creating it if needed."""
    existing = _existing_target("BP Task", bp_name, "erpnext_task", "Task")
    if existing:
        return existing

    bp = frappe.get_doc("BP Task", bp_name)

    native_project = None
    if bp.get("project"):
        native_project = (project_map or {}).get(bp.project) or migrate_project(bp.project)

    categories = _workflow_categories(bp.project) if bp.get("project") else {}
    category = categories.get(str(bp.get("status")), "unstarted")

    native = frappe.new_doc("Task")
    native.subject = bp.get("title") or bp_name  # subject is mandatory
    native.status = _CATEGORY_TO_TASK_STATUS.get(category, "Open")
    if bp.get("priority"):
        native.priority = _TASK_PRIORITY.get(bp.priority, "Medium")
    if native_project:
        native.project = native_project
    _copy_values(bp, native, "Task")
    # The project's own state name, which native's closed Select cannot hold.
    native.custom_status_label = bp.get("status") or None
    native.insert(ignore_permissions=True)

    frappe.db.set_value(
        "BP Task", bp_name, "erpnext_task", native.name, update_modified=False
    )
    return native.name


def run_native_migration():
    """Migrate every BP Project and BP Task. Idempotent; never raises.

    Per-row isolation is deliberate: this runs from a patch, and one malformed
    row must not abort a whole `bench migrate` and leave the site half-moved.
    Failures are logged and counted, so a re-run picks up exactly what did not
    land.
    """
    stats = {"projects": 0, "tasks": 0, "failed": 0}
    project_map = {}

    for name in frappe.get_all("BP Project", pluck="name"):
        try:
            project_map[name] = migrate_project(name)
            stats["projects"] += 1
        except Exception:
            stats["failed"] += 1
            frappe.log_error(frappe.get_traceback(), f"native migration: BP Project {name}")

    for name in frappe.get_all("BP Task", pluck="name"):
        try:
            migrate_task(name, project_map)
            stats["tasks"] += 1
        except Exception:
            stats["failed"] += 1
            frappe.log_error(frappe.get_traceback(), f"native migration: BP Task {name}")

    frappe.db.commit()
    frappe.logger("batch_projects").info(f"native migration: {stats}")
    return stats
