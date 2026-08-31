"""
batch_projects/setup/jira_workspace.py
──────────────────────────────────────
Stage 2: the Jira-shaped Projects experience, built from v16 desk primitives on
ERPNext's own `Project` and `Task` — no standalone SPA.

Almost nothing here is new machinery. Native Task already carries the whole
skeleton, so this wires it up rather than reimplementing it:

    hierarchy   Task is `is_tree: 1` with `nsm_parent_field: parent_task`, plus
                is_group / lft / rgt. ERPNext even ships task_tree.js. So
                "tasks grouped level by level" is the native Tree view at
                /app/task/view/tree — an epic with stories under it with
                sub-tasks under those, arbitrarily deep.
    board       Task.status is a Select, which is exactly what a Kanban Board
                groups on.
    issue types Task.type is a Link to `Task Type`, so Epic/Story/Task/Bug/
                Sub-task are records, not an enum we own.

Everything below is idempotent and never raises: it runs from `after_install`
and `after_migrate`, where an exception would abort an install or a whole
`bench migrate`. A missing board is a degraded UI, not a reason to fail a
migration.
"""

import json

import frappe

BOARD_NAME = "Projects Board"

# Task.status options, mapped to Jira-ish column semantics.
#
# Every status a task can actually hold gets a column. A Kanban Board only
# renders cards whose value matches a defined column, so omitting one would
# silently hide those tasks — `Overdue` in particular is a real state tasks land
# in, and hiding overdue work is the opposite of useful. `Template` and
# `Cancelled` are real values too but aren't active work, so they exist as
# Archived columns: present, not cluttering the board.
_COLUMNS = [
    ("Open", "To Do", "Gray", "Active"),
    ("Working", "In Progress", "Blue", "Active"),
    ("Pending Review", "In Review", "Purple", "Active"),
    ("Overdue", "Overdue", "Red", "Active"),
    ("Completed", "Done", "Green", "Active"),
    ("Cancelled", "Cancelled", "Light Blue", "Archived"),
    ("Template", "Template", "Yellow", "Archived"),
]

# Jira's default issue-type ladder. Task Type is a plain Link target, so these
# are ordinary records — a workspace can add or rename its own without touching
# code, which an enum would not allow.
_ISSUE_TYPES = ["Epic", "Story", "Task", "Bug", "Sub-task"]


def setup_jira_workspace():
    """Create the board and issue types. Idempotent, never raises."""
    try:
        _ensure_issue_types()
        _ensure_task_board()
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "batch_projects: could not set up the Jira-style Projects workspace",
        )


def _ensure_issue_types():
    if not frappe.db.exists("DocType", "Task Type"):
        return  # erpnext not installed
    for name in _ISSUE_TYPES:
        if not frappe.db.exists("Task Type", name):
            frappe.get_doc({"doctype": "Task Type", "task_type": name}).insert(
                ignore_permissions=True
            )


def _ensure_task_board():
    """One shared board on Task, grouped by status.

    Deliberately one board rather than one per project: a per-project board
    would mean creating and garbage-collecting a Kanban Board record for every
    project ever made, and Frappe already supports filtering a board by URL. So
    the board is generic and the Project form passes `project=<name>`.
    """
    if not frappe.db.exists("DocType", "Task"):
        return

    existing = frappe.db.exists("Kanban Board", BOARD_NAME)
    doc = (
        frappe.get_doc("Kanban Board", BOARD_NAME)
        if existing
        else frappe.new_doc("Kanban Board")
    )

    doc.kanban_board_name = BOARD_NAME
    doc.reference_doctype = "Task"
    doc.field_name = "status"
    doc.private = 0
    doc.show_labels = 1
    # No stored filters: the board is shared and scoped per visit by the URL the
    # Project form builds. Baking a project filter in here would pin the one
    # shared board to a single project.
    doc.filters = json.dumps([])

    wanted = {status for status, _, _, _ in _COLUMNS}
    have = {row.column_name for row in (doc.columns or [])}
    if have != wanted:
        doc.columns = []
        for status, label, indicator, col_status in _COLUMNS:
            # column_name must equal the field value, or cards never match it.
            # `label` is the Jira-facing wording and is intentionally not used
            # as the key.
            doc.append(
                "columns",
                {"column_name": status, "status": col_status, "indicator": indicator},
            )

    doc.flags.ignore_permissions = True
    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
