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


# ─── SATELLITE LINK RETARGETING ──────────────────────────────────────────────
#
# 39 Link fields across 32 satellite doctypes hold BP Project / BP Task row
# names. Once every parent has a native counterpart those stored values have to
# be rewritten to the native names, or the Links dangle.
#
# The four fields on BP Project / BP Task themselves (project, parent_project,
# parent_task, recurrence_source) are deliberately excluded: those doctypes are
# being retired, and `BP Task.project` is what the migration itself reads to
# resolve a task's project. Rewriting them mid-migration would cut the ground
# out from under it.
#
# Field discovery is done from live meta rather than a hardcoded list, so a
# satellite added later is picked up automatically instead of being silently
# skipped.

_RETIRING_DOCTYPES = ("BP Project", "BP Task")

_ANCHOR = {
    "BP Project": ("erpnext_project", "Project"),
    "BP Task": ("erpnext_task", "Task"),
}


def _satellite_link_fields():
    """[(doctype, fieldname, bp_doctype)] for every Link into a retiring doctype."""
    out = []
    for bp_doctype in _RETIRING_DOCTYPES:
        for row in frappe.get_all(
            "DocField",
            filters={"fieldtype": "Link", "options": bp_doctype},
            fields=["parent", "fieldname"],
            ignore_permissions=True,
        ):
            if row.parent in _RETIRING_DOCTYPES:
                continue  # on the retiring doctype itself — see note above
            out.append((row.parent, row.fieldname, bp_doctype))
    return out


def _name_collisions(bp_doctype):
    """BP row names that are also native row names.

    The rewrite is a JOIN from the stored value back to the BP table, which is
    naturally idempotent *unless* a native name happens to equal a BP name — in
    which case a second run would rewrite an already-rewritten value. Real BP
    names and native `PROJ-####` / `TASK-YYYY-#####` series should never
    collide, but a site that renamed rows could. Cheap to check, expensive to
    discover later.
    """
    anchor_field, native_doctype = _ANCHOR[bp_doctype]
    bp_names = set(frappe.get_all(bp_doctype, pluck="name"))
    if not bp_names:
        return set()
    native_names = set(frappe.get_all(native_doctype, pluck="name"))
    return bp_names & native_names


def retarget_satellite_links():
    """Rewrite satellite Link values from BP row names to native ones.

    Idempotent and never raises — this runs from a patch. Returns per-field
    counts so a partial run is visible rather than guessed at.
    """
    stats = {"updated": 0, "fields": 0, "skipped_collision": [], "failed": 0}

    for bp_doctype in _RETIRING_DOCTYPES:
        collisions = _name_collisions(bp_doctype)
        if collisions:
            # Fail loudly rather than corrupt values: a collision means the
            # JOIN can no longer tell a rewritten value from a stale one.
            stats["skipped_collision"].append(
                {"doctype": bp_doctype, "count": len(collisions)}
            )
            frappe.log_error(
                f"{bp_doctype}: {len(collisions)} name(s) collide with existing "
                f"{_ANCHOR[bp_doctype][1]} names, e.g. {sorted(collisions)[:5]}. "
                "Satellite retargeting skipped for this doctype to avoid "
                "rewriting already-migrated values.",
                "native migration: name collision",
            )

    for doctype, fieldname, bp_doctype in _satellite_link_fields():
        if any(c["doctype"] == bp_doctype for c in stats["skipped_collision"]):
            continue
        anchor_field, _ = _ANCHOR[bp_doctype]
        try:
            # Counted explicitly rather than read off the cursor: frappe's
            # database layer exposes no rowcount, so `frappe.db._cursor` would
            # be reaching past a private boundary for a number we can just ask
            # for.
            pending = frappe.db.sql(
                f"""
                SELECT count(*)
                  FROM `tab{doctype}` sat
                  JOIN `tab{bp_doctype}` bp ON sat.`{fieldname}` = bp.`name`
                 WHERE bp.`{anchor_field}` is not null
                   AND bp.`{anchor_field}` != ''
                """
            )[0][0]
            if pending:
                frappe.db.sql(
                    f"""
                    UPDATE `tab{doctype}` sat
                      JOIN `tab{bp_doctype}` bp ON sat.`{fieldname}` = bp.`name`
                       SET sat.`{fieldname}` = bp.`{anchor_field}`
                     WHERE bp.`{anchor_field}` is not null
                       AND bp.`{anchor_field}` != ''
                    """
                )
            stats["updated"] += pending
            stats["fields"] += 1
        except Exception:
            stats["failed"] += 1
            frappe.log_error(
                frappe.get_traceback(),
                f"native migration: retarget {doctype}.{fieldname}",
            )

    frappe.db.commit()
    frappe.logger("batch_projects").info(f"satellite retarget: {stats}")
    return stats
