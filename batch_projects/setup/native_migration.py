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


def _native_unset(value):
    """Whether a NATIVE field should count as "not filled in yet".

    Numeric zero has to count as unset here. Frappe creates
    Int/Float/Currency/Check columns NOT NULL DEFAULT 0 (see
    frappe/database/schema.py NOT_NULL_TYPES), so a fresh native row reads 0.0
    for every number — and treating that as "already has a value" made the
    backfill skip every numeric field in complete silence. Confirmed on a live
    site: BP budget_amount 5000 and hourly_rate 120 both landed as 0.0 with no
    error anywhere.

    The trade-off is a Check deliberately set to 0 natively, which a BP 1 will
    overwrite. That is the right way round while BP is still the system of
    record; after activation nothing writes BP.
    """
    return value in (None, "", 0, 0.0)


def _nothing_to_copy(value):
    """Whether a BP value is absent. Distinct from _native_unset on purpose.

    A BP zero is a real value, not an absence — but copying it onto a native
    field that is already 0 is a no-op either way, so only None/"" count as
    nothing to copy. Conflating the two questions in one predicate is what made
    the numeric bug hard to see.
    """
    return value in (None, "")


def _fill(native_doc, field, value, authoritative=False):
    """Write `value` onto the native row. Returns True if it changed anything.

    Non-authoritative fields are filled only when the native side is unset, so a
    value somebody set directly on the native row is never clobbered.
    Authoritative fields (the translated enums) are always written: getting the
    status vocabulary right is the entire point of the translation, and leaving
    a stale one defeats it.
    """
    if _nothing_to_copy(value):
        return False
    if not authoritative and not _native_unset(native_doc.get(field)):
        return False
    if native_doc.get(field) == value:
        return False
    native_doc.set(field, value)
    return True


def _backfill(bp_doc, native_doc, doctype):
    """Copy BP values onto an EXISTING native row. Returns True if it changed.

    This exists because the old erp_link bridge already creates a native Project
    when a BP Project is inserted — so on any site that used it, every BP row is
    already mapped and a create-only migration would copy nothing at all,
    silently leaving stub rows behind (confirmed on a live site: bridged
    Projects had custom_key None and an untranslated status). A migration that
    no-ops on the common case is worse than no migration.
    """
    changed = False
    for bp_field, native_field in NATIVE_FIELD_MAP.get(doctype, {}).items():
        if native_field:
            changed |= _fill(native_doc, native_field, bp_doc.get(bp_field))
    for fieldname in _scalar_custom_fields(doctype):
        changed |= _fill(native_doc, fieldname, bp_doc.get(fieldname[len("custom_") :]))
    return changed


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
    bp = frappe.get_doc("BP Project", bp_name)
    status, is_active = _PROJECT_STATUS.get(bp.get("status"), ("Open", "Yes"))

    existing = _existing_target("BP Project", bp_name, "erpnext_project", "Project")
    if existing:
        native = frappe.get_doc("Project", existing)
        changed = _backfill(bp, native, "Project")
        # Translated enums are authoritative — the bridge left these at its own
        # defaults (an Archived BP project showed as Open / is_active Yes).
        changed |= _fill(native, "status", status, authoritative=True)
        changed |= _fill(native, "is_active", is_active, authoritative=True)
        if changed:
            native.save(ignore_permissions=True)
        return existing

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
    bp = frappe.get_doc("BP Task", bp_name)

    existing = _existing_target("BP Task", bp_name, "erpnext_task", "Task")
    if existing:
        native = frappe.get_doc("Task", existing)
        changed = _backfill(bp, native, "Task")
        cats = _workflow_categories(bp.project) if bp.get("project") else {}
        cat = cats.get(str(bp.get("status")), "unstarted")
        changed |= _fill(native, "status", _CATEGORY_TO_TASK_STATUS.get(cat, "Open"),
                         authoritative=True)
        if bp.get("priority"):
            changed |= _fill(native, "priority", _TASK_PRIORITY.get(bp.priority, "Medium"),
                             authoritative=True)
        changed |= _fill(native, "custom_status_label", bp.get("status"), authoritative=True)
        if changed:
            native.save(ignore_permissions=True)
        return existing

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


def _bp_parent_chain_is_cyclic(child, parent_of, limit=64):
    """Whether following parent_task from `child` loops or runs away.

    BP Task is a plain Link, not a nested set, so nothing ever stopped a row
    from pointing at its own descendant. Native Task IS a nested set, and
    feeding a cycle to update_nsm corrupts lft/rgt for the whole tree — a
    failure that shows up later as a tree view that renders wrong, not as an
    exception here. Cheaper to refuse the cycle than to repair the tree.
    """
    seen, node = {child}, parent_of.get(child)
    for _ in range(limit):
        if not node:
            return False
        if node in seen:
            return True
        seen.add(node)
        node = parent_of.get(node)
    return True  # deeper than any real breakdown — treat as runaway


def migrate_task_hierarchy():
    """Reproduce BP Task's parent/child structure on the native side.

    A second pass, deliberately. A child's parent may be migrated after the
    child, so there is no single ordering in which the first pass could resolve
    every link — and BP Task.parent_task holds a BP row name, which is not a
    valid value for native Task.parent_task until both sides exist.

    Two ERPNext constraints shape the order of operations:

      * `Task.validate_parent_is_group` throws unless the parent carries
        `is_group = 1`, so every parent is marked before any child is attached.
      * Task is a NestedSet. `parent_task` is therefore set through
        `doc.save()`, never `db.set_value`: the latter would leave `lft`/`rgt`
        describing the old shape, and the tree view reads those, not
        parent_task. The tree would render a structure the data does not have.

    Without this pass the migration silently flattens every hierarchy — each
    task arrives as a root and the nesting is simply gone.
    """
    stats = {"linked": 0, "groups": 0, "skipped": 0, "cyclic": 0, "failed": 0}

    rows = frappe.get_all(
        "BP Task",
        filters={"parent_task": ["is", "set"]},
        fields=["name", "parent_task", "erpnext_task"],
        ignore_permissions=True,
    )
    if not rows:
        return stats

    parent_of = {r.name: r.parent_task for r in rows}
    native_of = {
        r.name: r.erpnext_task
        for r in frappe.get_all(
            "BP Task",
            filters={"name": ["in", sorted({r.parent_task for r in rows} | set(parent_of))]},
            fields=["name", "erpnext_task"],
            ignore_permissions=True,
        )
    }

    pairs = []
    for row in rows:
        child, parent = row.erpnext_task, native_of.get(row.parent_task)
        if not child or not parent or child == parent:
            # Either side unmigrated, or a row that is its own parent.
            stats["skipped"] += 1
            continue
        if _bp_parent_chain_is_cyclic(row.name, parent_of):
            stats["cyclic"] += 1
            continue
        pairs.append((child, parent))

    # Parents first — a child save would be rejected otherwise.
    for parent in sorted({p for _, p in pairs}):
        if not frappe.db.get_value("Task", parent, "is_group"):
            frappe.db.set_value("Task", parent, "is_group", 1, update_modified=False)
            stats["groups"] += 1

    for child, parent in pairs:
        try:
            doc = frappe.get_doc("Task", child)
            if doc.parent_task == parent:
                continue  # already linked by an earlier run
            doc.parent_task = parent
            doc.save(ignore_permissions=True)  # NestedSet maintains lft/rgt
            stats["linked"] += 1
        except Exception:
            # Most likely one of ERPNext's parent/child date validations. The
            # task itself is already migrated and correct; only its nesting is
            # missing, so this is counted rather than allowed to abort the pass.
            stats["failed"] += 1
            frappe.log_error(
                frappe.get_traceback(),
                f"native migration: hierarchy {child} -> {parent}",
            )

    frappe.db.commit()
    frappe.logger("batch_projects").info(f"native hierarchy: {stats}")
    return stats


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

    # Hierarchy last: every task must exist before parents can be resolved.
    stats["hierarchy"] = migrate_task_hierarchy()

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


# ─── DRY RUN ─────────────────────────────────────────────────────────────────

def dry_run_native_migration():
    """Report what a migration would do, writing nothing.

    Activation is the first irreversible step in this whole effort — it creates
    native rows and rewrites satellite Link values in place. Being able to see
    the blast radius, and specifically the rows that would *fail*, before
    anything is written is worth more than a careful re-read of the code.

    Every check here is a read. Returns a plain dict so it is equally usable
    from `bench execute` and from a test.
    """
    report = {
        "projects": {"total": 0, "already_mapped": 0, "to_create": 0, "blocked": []},
        "tasks": {"total": 0, "already_mapped": 0, "to_create": 0, "unknown_status": []},
        "satellites": {"fields": 0, "rows": 0, "detail": []},
        "collisions": {},
    }

    default_company = frappe.defaults.get_global_default("company")

    for row in frappe.get_all("BP Project", fields=["name", "project_name", "company", "status"]):
        report["projects"]["total"] += 1
        if _existing_target("BP Project", row.name, "erpnext_project", "Project"):
            report["projects"]["already_mapped"] += 1
            continue
        report["projects"]["to_create"] += 1
        # company is mandatory on native Project; without one the insert fails.
        if not (row.company or default_company):
            report["projects"]["blocked"].append(
                {"name": row.name, "reason": "no company and no global default"}
            )
        if row.status and row.status not in _PROJECT_STATUS:
            report["projects"]["blocked"].append(
                {"name": row.name, "reason": f"unmapped status {row.status!r}"}
            )

    category_cache = {}
    for row in frappe.get_all("BP Task", fields=["name", "title", "project", "status"]):
        report["tasks"]["total"] += 1
        if _existing_target("BP Task", row.name, "erpnext_task", "Task"):
            report["tasks"]["already_mapped"] += 1
            continue
        report["tasks"]["to_create"] += 1
        if row.project and row.status:
            if row.project not in category_cache:
                category_cache[row.project] = _workflow_categories(row.project)
            if str(row.status) not in category_cache[row.project]:
                # Not fatal — it falls back to the `unstarted` category — but
                # it means a status whose intent we are guessing at.
                report["tasks"]["unknown_status"].append(
                    {"name": row.name, "status": row.status, "project": row.project}
                )

    for bp_doctype in _RETIRING_DOCTYPES:
        collisions = _name_collisions(bp_doctype)
        if collisions:
            report["collisions"][bp_doctype] = sorted(collisions)[:20]

    # Child rows are the quiet one: nothing errors if they are left behind, the
    # native parent simply has an empty child table.
    report["child_rows"] = {"tables": 0, "rows": 0, "detail": []}
    for (bp_parenttype, bp_parentfield), _ in _CHILD_TABLES.items():
        child = _CHILD_DOCTYPE[(bp_parenttype, bp_parentfield)]
        anchor, _unused = _ANCHOR[bp_parenttype]
        if not frappe.db.exists("DocType", child):
            continue
        try:
            pending = frappe.db.sql(
                f"""
                SELECT count(*)
                  FROM `tab{child}` c
                  JOIN `tab{bp_parenttype}` bp ON c.`parent` = bp.`name`
                 WHERE c.`parenttype` = %s AND c.`parentfield` = %s
                   AND bp.`{anchor}` is not null AND bp.`{anchor}` != ''
                """,
                (bp_parenttype, bp_parentfield),
            )[0][0]
        except Exception:
            continue
        report["child_rows"]["tables"] += 1
        if pending:
            report["child_rows"]["rows"] += pending
            report["child_rows"]["detail"].append({"doctype": child, "rows": pending})

    for doctype, fieldname, bp_doctype in _satellite_link_fields():
        anchor_field, _ = _ANCHOR[bp_doctype]
        try:
            pending = frappe.db.sql(
                f"""
                SELECT count(*)
                  FROM `tab{doctype}` sat
                  JOIN `tab{bp_doctype}` bp ON sat.`{fieldname}` = bp.`name`
                 WHERE bp.`{anchor_field}` is not null
                   AND bp.`{anchor_field}` != ''
                """
            )[0][0]
        except Exception:
            pending = None  # table may not exist yet on a partial install
        report["satellites"]["fields"] += 1
        if pending:
            report["satellites"]["rows"] += pending
            report["satellites"]["detail"].append(
                {"doctype": doctype, "field": fieldname, "rows": pending}
            )

    # Hierarchy: how much nesting there is to carry over, and how much of it
    # cannot be. `unresolved` is the number whose parent has no native
    # counterpart yet — expected before the first run, a problem after one.
    total = frappe.db.count("BP Task", {"parent_task": ["is", "set"]})
    unresolved = frappe.db.sql(
        """
        SELECT count(*)
          FROM `tabBP Task` child
          LEFT JOIN `tabBP Task` parent ON child.`parent_task` = parent.`name`
         WHERE child.`parent_task` is not null AND child.`parent_task` != ''
           AND (parent.`name` is null
                OR parent.`erpnext_task` is null OR parent.`erpnext_task` = '')
        """
    )[0][0]
    report["hierarchy"] = {
        "links": total,
        "unresolved_parents": unresolved,
        "ready": total - unresolved,
    }

    return report


# ─── CHILD TABLE RE-PARENTING ────────────────────────────────────────────────
#
# Child rows do not move with their parent. A BP Task Assignee row carries
# parent = <BP Task name>, parenttype = "BP Task", parentfield = "assignees";
# after the migration the native Task exists but the row still points at the BP
# record, and `custom_assignees` on the native Task is empty.
#
# retarget_satellite_links() does not cover this — it rewrites Link *fields*,
# and parent/parenttype/parentfield are none of those. So without this step a
# cutover silently loses every assignee, task link, task reference, project
# member and per-project custom field: the parents migrate, the children are
# orphaned, and nothing errors because an empty child table is perfectly valid.
#
# (bp parenttype, bp parentfield) -> (native parenttype, native parentfield)
_CHILD_TABLES = {
    ("BP Task", "assignees"): ("Task", "custom_assignees"),
    ("BP Task", "links"): ("Task", "custom_links"),
    ("BP Task", "references"): ("Task", "custom_references"),
    ("BP Project", "members"): ("Project", "custom_members"),
    ("BP Project", "custom_field_links"): ("Project", "custom_custom_field_links"),
}

# The child doctype each pair lives in.
_CHILD_DOCTYPE = {
    ("BP Task", "assignees"): "BP Task Assignee",
    ("BP Task", "links"): "BP Task Link",
    ("BP Task", "references"): "BP Task Reference",
    ("BP Project", "members"): "BP Project Member",
    ("BP Project", "custom_field_links"): "BP Custom Field Project",
}


def retarget_child_tables():
    """Re-parent child rows from the BP records onto their native counterparts.

    Idempotent and never raises — this runs from a patch. A row is only moved
    when its BP parent has a mapping anchor, so a re-run finds nothing left to
    do (the rows now carry the native parenttype and no longer match).
    """
    stats = {"moved": 0, "tables": 0, "failed": 0, "skipped_collision": []}

    for bp_doctype in _RETIRING_DOCTYPES:
        if _name_collisions(bp_doctype):
            stats["skipped_collision"].append(bp_doctype)

    for (bp_parenttype, bp_parentfield), (native_parenttype, native_parentfield) in _CHILD_TABLES.items():
        if bp_parenttype in stats["skipped_collision"]:
            continue
        child = _CHILD_DOCTYPE[(bp_parenttype, bp_parentfield)]
        anchor, _ = _ANCHOR[bp_parenttype]
        if not frappe.db.exists("DocType", child):
            continue
        try:
            pending = frappe.db.sql(
                f"""
                SELECT count(*)
                  FROM `tab{child}` c
                  JOIN `tab{bp_parenttype}` bp ON c.`parent` = bp.`name`
                 WHERE c.`parenttype` = %s
                   AND c.`parentfield` = %s
                   AND bp.`{anchor}` is not null AND bp.`{anchor}` != ''
                """,
                (bp_parenttype, bp_parentfield),
            )[0][0]
            if pending:
                frappe.db.sql(
                    f"""
                    UPDATE `tab{child}` c
                      JOIN `tab{bp_parenttype}` bp ON c.`parent` = bp.`name`
                       SET c.`parent` = bp.`{anchor}`,
                           c.`parenttype` = %s,
                           c.`parentfield` = %s
                     WHERE c.`parenttype` = %s
                       AND c.`parentfield` = %s
                       AND bp.`{anchor}` is not null AND bp.`{anchor}` != ''
                    """,
                    (native_parenttype, native_parentfield, bp_parenttype, bp_parentfield),
                )
            stats["moved"] += pending
            stats["tables"] += 1
        except Exception:
            stats["failed"] += 1
            frappe.log_error(
                frappe.get_traceback(),
                f"native migration: re-parent {child} ({bp_parenttype}.{bp_parentfield})",
            )

    frappe.db.commit()
    frappe.logger("batch_projects").info(f"child table re-parent: {stats}")
    return stats
