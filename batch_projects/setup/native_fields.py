"""
batch_projects/setup/native_fields.py
─────────────────────────────────────
Stage 1 of moving this app onto ERPNext's native `Project` and `Task` doctypes.

Every field the BP model carries that native Project/Task does not, added as a
Custom Field on the native doctype. Purely additive and idempotent: it creates
nothing that already exists, changes no behaviour, and removes nothing. Nothing
in the app reads these yet — re-keying the `BP Task`/`BP Project` references is
a later, separately reviewable stage.

Prefer the native field
    Where native Project/Task already has a field meaning the same thing, we
    use it rather than adding a parallel column. NATIVE_FIELD_MAP below records
    those, and is the mapping stage 3's read/write paths follow. Duplicating
    them would give every Task two titles and two identifiers, which is exactly
    how two sources of truth drift apart.

`custom_` prefix
    Frappe's convention for an app adding fields to another app's doctype, and
    the app's existing fixtures already follow it (`custom_bp_task` on
    Timesheet Detail). Without it, a future ERPNext release adding a field of
    the same name would collide on a core doctype.

No `reqd`
    A Custom Field must never be mandatory on a doctype another app owns. The
    BP model could require `key`/`title` because BP Project/BP Task were ours;
    native Project/Task belong to ERPNext and are created by erpnext's own
    tests and fixtures, by CRM/HRMS, and by users. Carrying `reqd: 1` across
    broke exactly that — `MandatoryError: [Project, PROJ-0001]: custom_key`
    from erpnext's own test records. Where a value is genuinely required, the
    app enforces it on its own write path in a later stage; it is not a schema
    constraint on a shared doctype.

Why the two key fields are NOT mapped onto native naming
    `custom_key` (a project's short prefix, e.g. BIM) and `custom_task_key`
    (BIM-42) look like duplicates of native naming, and are deliberately kept.
    Native Task autonames `TASK-.YYYY.-.#####` and Project `PROJ-.####` — both
    site-wide sequences. A Jira key is a *per-project* counter, which a Frappe
    naming series cannot express: BIM-1 and FA-1 must be able to coexist. So
    these are genuinely additional information rather than a second spelling of
    `name`.

Only BP Project / BP Task are retargeted
    Of the 54 BP doctypes, exactly these two are being replaced by native
    counterparts. The other 52 — BP Sprint, BP Epic, BP Milestone, BP Team,
    BP Task Assignee and the rest — remain, and become satellites linked *from*
    native Project/Task. So a Link whose target is `BP Project` becomes
    `Project` (see custom_parent_project) and `BP Task` becomes `Task` (see
    custom_recurrence_source), while every other BP target is left alone.

No `insert_after`: Frappe appends, and field layout is the desk-UI stage's job.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# BP field name (unprefixed) -> the native Project/Task field that already
# means the same thing. These are deliberately NOT added as custom fields;
# stage 3 reads and writes the native field instead. `None` means the BP field
# is simply meaningless once native Project is the model.
NATIVE_FIELD_MAP = {
    "Project": {
        "description": 'notes',
        "client": 'customer',
        "start_date": 'expected_start_date',
        "target_end_date": 'expected_end_date',
        "budget_amount": 'estimated_costing',
        "source_sales_order": 'sales_order',
        "template_used": 'project_template',
        "category": 'project_type',
        "erpnext_project": None,
    },
    "Task": {
        "title": 'subject',
        "task_type": 'type',
        "due_date": 'exp_end_date',
        "start_date": 'exp_start_date',
        "estimated_hours": 'expected_time',
        "actual_hours": 'actual_time',
        "started_on": 'act_start_date',
    },
}

CUSTOM_FIELDS = {
    "Project": [
        {"fieldname": "custom_key", "label": 'Key', "fieldtype": 'Data', "description": '2-6 char prefix for issue IDs (e.g., BIM, FA, HTR)', "unique": 1},
        {"fieldname": "custom_project_color", "label": 'Project Color', "fieldtype": 'Color', "default": '#0B6BCB'},
        {"fieldname": "custom_project_icon", "label": 'Project Icon', "fieldtype": 'Data', "default": 'Folder'},
        {"fieldname": "custom_theme", "label": 'Theme', "fieldtype": 'Select', "options": '\nkoalaBlue\nkoalaGreen\nkoalaRed\nnotesOrange\nnotesPurple\ntreasureGray\ntreasureSand\nwhiteboard\nyetiBlue\nyetiGreen', "description": 'Illustrated project avatar shown in the sidebar and project cards.'},
        {"fieldname": "custom_health_override", "label": 'Health (override)', "fieldtype": 'Select', "options": '\nOn track\nAt risk\nOff track', "description": 'Phase 22B — blank (default) = auto-derived from overdue %, done % vs elapsed time, and target-date slip. Set explicitly to override the computed value in Portfolio.'},
        {"fieldname": "custom_visibility", "label": 'Visibility', "fieldtype": 'Select', "options": 'workspace\nprivate\nteam', "default": 'workspace'},
        {"fieldname": "custom_parent_project", "label": 'Parent Project (WBS)', "fieldtype": 'Link', "options": 'Project', "description": 'For project hierarchy / WBS breakdown. Child projects inherit visibility from parent.'},
        {"fieldname": "custom_team", "label": 'Team', "fieldtype": 'Link', "options": 'BP Team'},
        {"fieldname": "custom_lead", "label": 'Project Lead', "fieldtype": 'Link', "options": 'User'},
        {"fieldname": "custom_default_assignee", "label": 'Default Assignee', "fieldtype": 'Link', "options": 'User'},
        {"fieldname": "custom_issue_counter", "label": 'Issue Counter', "fieldtype": 'Int', "default": '0', "read_only": 1, "hidden": 1},
        {"fieldname": "custom_schema_version", "label": 'Schema Version', "fieldtype": 'Int', "default": '1', "read_only": 1, "hidden": 1},
        {"fieldname": "custom_currency", "label": 'Currency', "fieldtype": 'Data', "default": 'INR'},
        {"fieldname": "custom_hourly_rate", "label": 'Hourly Rate', "fieldtype": 'Float', "precision": '2', "depends_on": "eval:doc.project_type == 'tm' || doc.project_type == 'retainer'"},
        {"fieldname": "custom_retainer_hours", "label": 'Monthly Retainer Hours', "fieldtype": 'Int', "depends_on": "eval:doc.project_type == 'retainer'"},
        {"fieldname": "custom_cycle_label", "label": 'Work Cycle Label', "fieldtype": 'Data', "default": 'Sprint', "description": 'What do you call a time-boxed work cycle? Sprint, Production Run, Phase, Campaign, Iteration, etc.'},
        {"fieldname": "custom_effort_label", "label": 'Effort Unit Label', "fieldtype": 'Data', "default": 'Story Points', "description": 'What unit do you estimate work in? Story Points, Hours, Units, Batch Size, Billable Days, etc.'},
        {"fieldname": "custom_workflow_states", "label": 'Workflow States', "fieldtype": 'Long Text'},
        {"fieldname": "custom_issue_types", "label": 'Issue Types', "fieldtype": 'Long Text'},
        {"fieldname": "custom_triage_enabled", "label": 'Enable Triage', "fieldtype": 'Check', "default": '0', "description": 'When enabled, new tasks with no explicit status land in the Triage inbox (needs_triage=1) rather than the default workflow column.'},
        {"fieldname": "custom_labels", "label": 'Labels', "fieldtype": 'Long Text'},
        {"fieldname": "custom_custom_fields", "label": 'Custom Fields Schema', "fieldtype": 'Long Text', "description": 'Deprecated — superseded by the BP Custom Field workspace library (custom_field_links). Left in place, unused, as a migration safety net.'},
        {"fieldname": "custom_custom_field_links", "label": 'Custom Fields', "fieldtype": 'Table', "options": 'BP Custom Field Project'},
        {"fieldname": "custom_custom_field_values", "label": 'Custom Field Values', "fieldtype": 'Long Text', "description": 'Project-level custom field values, mirrors BP Task.custom_field_values.'},
        {"fieldname": "custom_enabled_views", "label": 'Enabled Views', "fieldtype": 'Long Text'},
        {"fieldname": "custom_pinned_views", "label": 'Pinned Views', "fieldtype": 'Long Text', "description": 'Ordered view keys shown inline in the header tab strip; the rest live behind the overflow drawer. Null = default split (summary/board/list/gantt pinned).'},
        {"fieldname": "custom_default_view", "label": 'Default View', "fieldtype": 'Data', "default": 'summary'},
        {"fieldname": "custom_members", "label": 'Members', "fieldtype": 'Table', "options": 'BP Project Member'},
        {"fieldname": "custom_source_lead", "label": 'Source Lead', "fieldtype": 'Link', "options": 'Lead', "read_only": 1, "description": 'Set when this project was created from a Lead.'},
        {"fieldname": "custom_source_opportunity", "label": 'Source Opportunity', "fieldtype": 'Link', "options": 'Opportunity', "read_only": 1, "description": 'Set when this project was created from an Opportunity.'},
        {"fieldname": "custom_source_quotation", "label": 'Source Quotation', "fieldtype": 'Link', "options": 'Quotation', "read_only": 1, "description": 'Set when this project was created from a Quotation.'},
    ],
    "Task": [
        {"fieldname": "custom_status_label", "label": 'Status Label', "fieldtype": 'Data', "read_only": 1, "description": 'The project\'s own workflow-state name. Native status holds the Jira-style category (unstarted/started/completed/cancelled -> Open/Working/Completed/Cancelled), which is a closed Select and cannot hold arbitrary per-project state names.'},
        {"fieldname": "custom_task_key", "label": 'Task Key', "fieldtype": 'Data', "read_only": 1, "in_list_view": 1, "unique": 1},
        {"fieldname": "custom_sequence_no", "label": 'Sequence No', "fieldtype": 'Int', "read_only": 1, "hidden": 1, "description": 'Global monotonic sequence — stable internal identity independent of the display task_key. Assigned automatically at creation, never changed.'},
        {"fieldname": "custom_epic", "label": 'Epic', "fieldtype": 'Link', "options": 'BP Epic', "in_standard_filter": 1},
        {"fieldname": "custom_reporter", "label": 'Reporter', "fieldtype": 'Link', "options": 'Employee'},
        {"fieldname": "custom_assignees", "label": 'Assignees', "fieldtype": 'Table', "options": 'BP Task Assignee'},
        {"fieldname": "custom_labels", "label": 'Labels', "fieldtype": 'Long Text', "description": 'List of label IDs from project labels schema'},
        {"fieldname": "custom_story_points", "label": 'Story Points', "fieldtype": 'Int', "default": '0'},
        {"fieldname": "custom_actual_points", "label": 'Actual Points', "fieldtype": 'Int', "default": '0', "description": "Points it actually took, vs Story Points' estimate — filled in during/after the sprint for calibration."},
        {"fieldname": "custom_is_unplanned", "label": 'Unplanned', "fieldtype": 'Check', "default": '0', "description": 'Added to the sprint after it started, rather than during planning.'},
        {"fieldname": "custom_planned_start", "label": 'Planned Start', "fieldtype": 'Date', "description": 'Scheduled start (the plan). Gantt/scheduling read this first and fall back to Start Date. Actual execution lives in started_on/completed_on.'},
        {"fieldname": "custom_planned_end", "label": 'Planned End', "fieldtype": 'Date', "description": 'Scheduled finish (the plan). Distinct from Due Date, which stays the commitment/deadline that drives reminders.'},
        {"fieldname": "custom_sprint", "label": 'Sprint', "fieldtype": 'Link', "options": 'BP Sprint', "in_standard_filter": 1},
        {"fieldname": "custom_milestone", "label": 'Milestone', "fieldtype": 'Link', "options": 'BP Milestone', "in_standard_filter": 1},
        {"fieldname": "custom_team", "label": 'Team', "fieldtype": 'Link', "options": 'BP Team', "in_standard_filter": 1},
        {"fieldname": "custom_is_recurring", "label": 'Repeats', "fieldtype": 'Check', "default": '0'},
        {"fieldname": "custom_recurrence_frequency", "label": 'Repeat Frequency', "fieldtype": 'Select', "options": 'Daily\nWeekly\nBiweekly\nMonthly', "depends_on": 'eval:doc.is_recurring'},
        {"fieldname": "custom_recurrence_end_date", "label": 'Repeat Until', "fieldtype": 'Date', "description": 'Optional. Leave blank to repeat indefinitely.', "depends_on": 'eval:doc.is_recurring'},
        {"fieldname": "custom_recurrence_source", "label": 'Recurring From', "fieldtype": 'Link', "options": 'Task', "read_only": 1, "hidden": 1, "description": 'Set only on tasks spawned by a recurring template — points back to that template.'},
        {"fieldname": "custom_submitted_via_intake", "label": 'Submitted Via Intake Form', "fieldtype": 'Link', "options": 'BP Intake Form', "read_only": 1, "hidden": 1, "description": 'Set only on tasks created from a public intake form submission — points back to that form.'},
        {"fieldname": "custom_bridge_job_id", "label": 'Bridge Job ID', "fieldtype": 'Data', "read_only": 1, "hidden": 1, "description": "Internal: the agent's job id for this task's recurrence timer."},
        {"fieldname": "custom_blocked_reason", "label": 'Blocked', "fieldtype": 'Select', "options": '\nWaiting for Client\nWaiting for Vendor\nWaiting for Approval\nTechnical Blocker\nResource Shortage', "description": 'Set a reason to mark the task blocked; clear to unblock. blocked_since / blocked_by are maintained automatically.'},
        {"fieldname": "custom_blocked_since", "label": 'Blocked Since', "fieldtype": 'Datetime', "read_only": 1, "description": 'When the task was last blocked — feeds the time-blocked project-health metric.'},
        {"fieldname": "custom_blocked_by", "label": 'Blocked By', "fieldtype": 'Link', "options": 'User', "read_only": 1, "description": 'The user who last marked this task blocked.'},
        {"fieldname": "custom_billable", "label": 'Billable', "fieldtype": 'Check', "default": '0'},
        {"fieldname": "custom_needs_triage", "label": 'Needs Triage', "fieldtype": 'Check', "default": '0', "description": 'Flag for triage review. Previously defaulted to on for every task — existing rows can be bulk-cleared.'},
        {"fieldname": "custom_resolution", "label": 'Resolution', "fieldtype": 'Select', "options": "\nDone\nWon't Do\nDuplicate\nCannot Reproduce\nObsolete", "description": 'Why the task was closed. Set automatically when moved to a completed status; cleared when reopened.'},
        {"fieldname": "custom_custom_field_values", "label": 'Custom Field Values', "fieldtype": 'Long Text', "hidden": 1, "description": 'Flat key-value map: {cf_id: value}. Managed by the SPA. Stored as JSON string.'},
        {"fieldname": "custom_sales_order", "label": 'Sales Order', "fieldtype": 'Link', "options": 'Sales Order'},
        {"fieldname": "custom_timesheet_detail", "label": 'Timesheet Detail', "fieldtype": 'Link', "options": 'Timesheet Detail'},
        {"fieldname": "custom_board_order", "label": 'Board Order', "fieldtype": 'Int', "default": '0', "hidden": 1},
        {"fieldname": "custom_board_rank", "label": 'Board Rank', "fieldtype": 'Data', "read_only": 1, "hidden": 1, "description": 'Fractional manual-ordering key (see rank.py).'},
        {"fieldname": "custom_links", "label": 'Linked Tasks', "fieldtype": 'Table', "options": 'BP Task Link'},
        {"fieldname": "custom_references", "label": 'ERPNext References', "fieldtype": 'Table', "options": 'BP Task Reference'},
        {"fieldname": "custom_approval_status", "label": 'Approval Status', "fieldtype": 'Select', "options": '\nApproval Not Required\nPending\nApproved\nRejected', "default": 'Approval Not Required'},
        {"fieldname": "custom_approver", "label": 'Approver', "fieldtype": 'Link', "options": 'User'},
        {"fieldname": "custom_approved_by", "label": 'Approved/Rejected By', "fieldtype": 'Link', "options": 'User'},
        {"fieldname": "custom_approved_on", "label": 'Approved On', "fieldtype": 'Datetime'},
        {"fieldname": "custom_is_deleted", "label": 'In Trash', "fieldtype": 'Check', "default": '0', "read_only": 1, "in_standard_filter": 1},
        {"fieldname": "custom_deleted_on", "label": 'Trashed On', "fieldtype": 'Datetime', "read_only": 1},
        {"fieldname": "custom_deleted_by", "label": 'Trashed By', "fieldtype": 'Link', "options": 'User', "read_only": 1},
    ],
}


def create_native_project_fields():
    """Add the BP field set to native Project/Task. Idempotent.

    Never raises: this runs from `after_install` and a patch, where an
    exception would abort app installation or `bench migrate`. A missing field
    is a degraded UI, not a reason to fail a migration — and the fields are
    re-asserted on every migrate anyway.
    """
    try:
        create_custom_fields(CUSTOM_FIELDS, update=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "batch_projects: could not create native Project/Task custom fields",
        )
