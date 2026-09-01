app_name = "batch_projects"
app_title = "Projects"
app_publisher = "BatchNepal Consultancy"
app_description = "Enterprise Grade Project Management for ERPNext"
app_email = "info@batchnepal.com"
app_license = "AGPL-3.0"
# Single source of truth is __init__.py's __version__ — the same thing
# pyproject.toml resolves (dynamic = ["version"], flit reads it) and the same
# thing frappe.utils.get_app_version() returns. Hardcoding the number a second
# time here is what let the two drift silently; frappe's own hooks.py imports
# it exactly this way for the same reason.
from . import __version__ as app_version

# No `add_to_apps_screen`, deliberately.
#
# This app is not a separate destination any more — it IS ERPNext's Projects
# module, reached through the Projects workspace on the desk. The entry it used
# to declare pointed at `/workspace`, the Vue SPA route that is being removed.
#
# Removing it also fixes a real, site-wide side effect of titling the app
# "Projects". frappe's create_desktop_icons_from_installed_apps() labels an
# app's Desktop Icon with `app_title`, and Desktop Icon autonames `field:label`
# — but its duplicate guard checks (label, icon_type="App") while the primary
# key is `label` alone. ERPNext already owns a Desktop Icon named "Projects"
# with icon_type="Link" (auto-generated from its Projects *Workspace*), so the
# guard misses it and the insert raises IntegrityError. That exception is caught
# one level up in frappe.utils.install.auto_generate_icons_and_sidebar, which
# aborts the whole block — so create_desktop_icons_from_workspace() never runs
# and workspace icons stop being generated for EVERY app on the site.
#
# Confirmed on a live v16 site: install printed
# `Error creating icons ('Desktop Icon', 'Projects', IntegrityError(1062, ...))`
# and afterwards only 5 of the installed apps had an icon_type="App" icon.
# With no add_to_apps_screen the icon is never attempted, so nothing collides.

# app_include_js = ["/assets/batch_projects/js/batch_projects.js"]

# The Vue SPA that served /workspace, /share/<token> and /intake/<token> has
# been removed; the desk is the UI now. One public route survives, because
# losing it would break a flow nobody chose to drop:
#
#   /invite/<token>  server-rendered accept page (www/invite.py). Without it
#                    every invitation email points at a 404 and there is no way
#                    to join a project at all.
website_route_rules = [
    {"from_route": "/invite/<path:app_path>", "to_route": "invite"},
]

#
# Removing /share and /intake is an outward-facing change, not just a cleanup —
# those were PUBLIC, unauthenticated URLs. Any share link already handed to a
# client, and any published intake form, stops resolving. The BP Share Link and
# BP Intake Form doctypes and their whitelisted endpoints are left intact, so
# the data and the API are still there; what is gone is the page that rendered
# them. Rebuilding either on the desk would be new work, deliberately not done
# here.

# Fixtures for export — roles must match what board.py actually uses
fixtures = [
    {"dt": "Role", "filters": [[
        "name", "in", ["BP Admin", "BP Manager", "BP Member", "BP Viewer", "BP Guest"]
    ]]},
    # Custom fields on core ERPNext doctypes — NEVER edit erpnext JSON directly,
    # these ship as fixtures. Filtered to exactly the fields we own.
    {"dt": "Custom Field", "filters": [[
        "name", "in", ["Timesheet Detail-custom_bp_task", "Sales Order-custom_bp_project",
                       "Expense Claim Detail-custom_is_billable",
                       "Expense Claim Detail-custom_sales_invoice",
                       "Expense Claim Type-custom_reinvoice_policy",
                       "Expense Claim Type-custom_markup_percent",
                       "Lead-custom_bp_project", "Opportunity-custom_bp_project",
                       "Quotation-custom_bp_project"]
    ]]},
    # Client Script on Sales Order (8C) / Lead / Opportunity / Quotation —
    # the "Create Batch Project" button, one per stage of the pipeline.
    {"dt": "Client Script", "filters": [[
        "name", "in", ["Sales Order Batch Project Button", "Lead Batch Project Button",
                       "Opportunity Batch Project Button", "Quotation Batch Project Button"]
    ]]},
]

# Jira-shaped navigation on ERPNext's own Project/Task, using v16 desk views.
# The SPA is being retired, so the desk lists are the real destination now
# rather than something to redirect out of — the earlier redirect into
# /workspace is gone.
#
# Opening a project goes to its task board (Jira's default), with the form one
# click away. Hierarchy needs nothing built: Task is `is_tree: 1` on
# parent_task, so the native Tree view already renders epics -> stories ->
# sub-tasks level by level.
doctype_js = {
    "Project": "public/js/project_jira.js",
}
doctype_list_js = {
    "Project": "public/js/project_jira.js",
}

# Project's BP-named field aliases are ATTACHED to whatever controller is
# already active rather than registered as an override — HRMS owns Project's
# controller and frappe applies only one. Both hooks are needed: before_request
# covers web traffic, before_job covers background jobs. Idempotent after the
# first call. See native_controllers.install_project_aliases.
before_request = ["batch_projects.native_controllers.before_request"]
before_job = ["batch_projects.native_controllers.before_job"]

# Hooks
after_install = "batch_projects.setup.install.after_install"

# ERPNext's `Projects` Workspace Sidebar is a standard record, so `bench
# migrate` re-imports it from erpnext's JSON and reverts our override every
# run. after_migrate fires after that sync, which is the only place the
# re-point survives an upgrade. Idempotent — see the module docstring.
after_migrate = [
    "batch_projects.setup.projects_module.override_erpnext_projects_module",
    "batch_projects.setup.jira_workspace.setup_jira_workspace",
]

# Data-layer access control — closes the generic-REST bypass and enforces
# project `visibility`. See batch_projects/permissions.py.
#
# BP Milestone / BP Risk / BP Automation Run are project-scoped but granted
# to broad stock roles (Projects User/Manager) with no hook at all, so the
# generic REST API bypasses project access entirely for them (including
# BP Milestone's invoice_amount/sales_invoice billing fields). BP
# Notification is scoped to `recipient`, not a project; it has `All: write`,
# letting any user mark ANY other user's notification read/unread via raw
# REST (mark_notification_read/_unread are the correct, redundant-but-
# harmless whitelisted path for the SPA).
permission_query_conditions = {
    "BP Task":            "batch_projects.permissions.bp_task_query_conditions",
    "BP Project":         "batch_projects.permissions.bp_project_query_conditions",
    "BP Sprint":          "batch_projects.permissions.bp_sprint_query_conditions",
    "BP Epic":            "batch_projects.permissions.bp_epic_query_conditions",
    "BP Report":          "batch_projects.permissions.bp_report_query_conditions",
    "BP Team":           "batch_projects.permissions.bp_team_query_conditions",
    "BP Milestone":       "batch_projects.permissions.bp_milestone_query_conditions",
    "BP Risk":            "batch_projects.permissions.bp_risk_query_conditions",
    "BP Automation Run":  "batch_projects.permissions.bp_automation_run_query_conditions",
    "BP Notification":    "batch_projects.notification_permissions.query_conditions",
    "BP Webhook Token":   "batch_projects.permissions.bp_webhook_token_query_conditions",
    # Project-scoped doctypes with a `project` field but no hook without
    # this (see permissions.py for the shared query-condition primitives).
    "BP Drawing":           "batch_projects.permissions.bp_drawing_query_conditions",
    "BP Intake Form":       "batch_projects.permissions.bp_intake_form_query_conditions",
    "BP Invitation":        "batch_projects.permissions.bp_invitation_query_conditions",
    "BP Note":              "batch_projects.permissions.bp_note_query_conditions",
    "BP Share Link":        "batch_projects.permissions.bp_share_link_query_conditions",
    "BP SLA Policy":        "batch_projects.permissions.bp_sla_policy_query_conditions",
    "BP Task Template":     "batch_projects.permissions.bp_task_template_query_conditions",
    "BP View":              "batch_projects.permissions.bp_view_query_conditions",
    "BP Activity":          "batch_projects.permissions.bp_activity_query_conditions",
    "BP Audit Log":         "batch_projects.permissions.bp_audit_log_query_conditions",
    "BP Automation Rule":   "batch_projects.permissions.bp_automation_rule_query_conditions",
    "BP Notification Mute": "batch_projects.permissions.bp_notification_mute_query_conditions",
    "BP Notification Rule": "batch_projects.permissions.bp_notification_rule_query_conditions",
    "BP Dashboard":        "batch_projects.permissions.bp_dashboard_query_conditions",
    "BP SLA Breach":        "batch_projects.permissions.bp_sla_breach_query_conditions",
    "BP Task Watcher":      "batch_projects.permissions.bp_task_watcher_query_conditions",
    "BP View Preference":   "batch_projects.permissions.bp_view_preference_query_conditions",
    "BP Workflow":          "batch_projects.permissions.bp_workflow_query_conditions",
}
has_permission = {
    "BP Task":            "batch_projects.permissions.bp_task_has_permission",
    "BP Project":         "batch_projects.permissions.bp_doc_has_permission",
    "BP Sprint":          "batch_projects.permissions.bp_doc_has_permission",
    "BP Epic":            "batch_projects.permissions.bp_doc_has_permission",
    "BP Report":          "batch_projects.permissions.bp_report_has_permission",
    "BP Dashboard":       "batch_projects.permissions.bp_dashboard_has_permission",
    "BP Team":           "batch_projects.permissions.bp_team_has_permission",
    "BP Milestone":       "batch_projects.permissions.bp_doc_has_permission",
    "BP Risk":            "batch_projects.permissions.bp_doc_has_permission",
    "BP Automation Run":  "batch_projects.permissions.bp_doc_has_permission",
    "BP Notification":    "batch_projects.notification_permissions.has_permission",
    "BP Webhook Token":   "batch_projects.permissions.bp_webhook_token_has_permission",
    "BP Drawing":           "batch_projects.permissions.bp_doc_has_permission",
    "BP Intake Form":       "batch_projects.permissions.bp_doc_has_permission",
    "BP Invitation":        "batch_projects.permissions.bp_doc_has_permission",
    "BP Note":              "batch_projects.permissions.bp_doc_has_permission",
    "BP Share Link":        "batch_projects.permissions.bp_doc_has_permission",
    "BP SLA Policy":        "batch_projects.permissions.bp_doc_has_permission",
    "BP Task Template":     "batch_projects.permissions.bp_doc_has_permission",
    "BP View":              "batch_projects.permissions.bp_doc_has_permission",
    "BP Activity":          "batch_projects.permissions.bp_doc_has_permission",
    "BP Audit Log":         "batch_projects.permissions.bp_doc_has_permission",
    "BP Automation Rule":   "batch_projects.permissions.bp_doc_has_permission",
    "BP Notification Mute": "batch_projects.permissions.bp_user_owned_has_permission",
    "BP Notification Rule": "batch_projects.permissions.bp_doc_has_permission",
    "BP SLA Breach":        "batch_projects.permissions.bp_doc_has_permission",
    "BP Task Watcher":      "batch_projects.permissions.bp_doc_has_permission",
    "BP View Preference":   "batch_projects.permissions.bp_user_owned_has_permission",
    "BP Workflow":          "batch_projects.permissions.bp_doc_has_permission",
}

# Transparently redirects a whitelisted dotted path's real implementation to
# a hardened replacement, without every existing caller (frontend, gateway)
# needing to change what it calls.
override_whitelisted_methods = {
    "batch_projects.api.automation.apply_action":
        "batch_projects.automation_security.apply_action",
    "batch_projects.api.automation.run_rule_node":
        "batch_projects.automation_security.run_rule_node",
    "batch_projects.api.automation.run_scheduled_event":
        "batch_projects.automation_security.run_scheduled_event",
    "batch_projects.api.board.update_project_members":
        "batch_projects.membership_invariants.update_project_members",
    "batch_projects.api.board.get_task":
        "batch_projects.task_reads.get_task",
    "batch_projects.api.board.get_export_data":
        "batch_projects.task_reads.get_export_data",
    "batch_projects.api.board.delete_task":
        "batch_projects.task_lifecycle.delete_task",
    "batch_projects.api.board.restore_task":
        "batch_projects.task_lifecycle.restore_task",
    "batch_projects.api.board.bulk_delete_tasks":
        "batch_projects.task_lifecycle.bulk_delete_tasks",
    "batch_projects.api.board.get_milestone_report":
        "batch_projects.task_aggregates.get_milestone_report",
    "batch_projects.api.board.get_sprint_capacity":
        "batch_projects.task_aggregates.get_sprint_capacity",
    "batch_projects.api.board.get_reports":
        "batch_projects.task_aggregates.get_reports",
    "batch_projects.api.board.complete_sprint":
        "batch_projects.task_surfaces.complete_sprint",
    "batch_projects.api.board.get_project_files":
        "batch_projects.task_surfaces.get_project_files",
    "batch_projects.api.dashboards.get_column_widget_data":
        "batch_projects.dashboard_task_reads.get_column_widget_data",
    "batch_projects.api.dashboards.get_widget_source_fields":
        "batch_projects.dashboard_security.get_widget_source_fields",
    "batch_projects.api.dashboards.get_widget_source_field_options":
        "batch_projects.dashboard_security.get_widget_source_field_options",
    "batch_projects.api.dashboards.get_multi_source_count":
        "batch_projects.dashboard_security.get_multi_source_count",
    "batch_projects.api.dashboards.get_doctype_group_data":
        "batch_projects.dashboard_security.get_doctype_group_data",
    "batch_projects.api.dashboards.get_doctype_column_data":
        "batch_projects.dashboard_security.get_doctype_column_data",
    "batch_projects.api.dashboards.update_widget_source_field":
        "batch_projects.dashboard_security.update_widget_source_field",
    "batch_projects.api.dashboards.get_widget_source_doc_quickview":
        "batch_projects.dashboard_security.get_widget_source_doc_quickview",
    "batch_projects.api.board.get_notifications":
        "batch_projects.notification_reads.get_notifications",
    "batch_projects.api.board.get_notification_count":
        "batch_projects.notification_reads.get_notification_count",
    "batch_projects.api.board.mark_notification_read":
        "batch_projects.notification_reads.mark_notification_read",
    "batch_projects.api.board.mark_notification_unread":
        "batch_projects.notification_reads.mark_notification_unread",
    "batch_projects.api.board.mark_all_notifications_read":
        "batch_projects.notification_reads.mark_all_notifications_read",
    "batch_projects.api.workflows.list_workflows":
        "batch_projects.workflow_security.list_workflows",
    "batch_projects.api.workflows.test_workflow":
        "batch_projects.workflow_security.test_workflow",
    "batch_projects.api.automation.run_workflow_node":
        "batch_projects.workflow_security.run_workflow_node",
    "batch_projects.api.automation.run_local_workflow_step":
        "batch_projects.workflow_security.run_local_workflow_step",
}

# BPEmailQueue scopes its override to BP-Task-referenced mail only (see the
# class docstring) — every other Email Queue doc on the site behaves exactly
# as Frappe core ships it.
override_doctype_class = {
    # Native Task carrying BP field aliases, so `doc.title` keeps working on a
    # native Task without editing thousands of field references. Task has no
    # other override; Project deliberately gets none — HRMS owns that one. See
    # native_controllers.py.
    "Task": "batch_projects.native_controllers.BPTask",
    "Email Queue": "batch_projects.secure_email_queue.BPEmailQueue",
}

# actual_hours rollup — resync every BP Task a submitted/cancelled
# Timesheet's rows point at (via the custom_bp_task fixture field).
# erp.* automation triggers fire onto the same events.emit() bus every
# task/comment/schedule trigger already rides. Tenancy-checked no-ops for
# anything outside a BP Project.
doc_events = {
    "Timesheet": {
        "on_submit": "batch_projects.timesheet_sync.on_timesheet_submit",
        "on_cancel": "batch_projects.timesheet_sync.on_timesheet_cancel",
    },
    "Sales Invoice": {
        # P0 billing reservation: native ERPNext draft creation/editing must
        # obey the same Timesheet Detail exclusivity as BatchProjects.
        "validate": "batch_projects.billing_reservation.validate_sales_invoice_sources",

        # Milestone billing lifecycle. on_submit also delegates to the existing
        # erp.invoice_submitted automation emitter so there remains exactly one
        # specific Sales Invoice submit hook.
        "after_insert": "batch_projects.milestone_billing.on_sales_invoice_after_insert",
        "on_submit": "batch_projects.milestone_billing.on_sales_invoice_submit",
        "on_cancel": "batch_projects.milestone_billing.on_sales_invoice_cancel",
        "on_trash": "batch_projects.milestone_billing.on_sales_invoice_trash",
    },
    "Sales Order": {
        "on_submit": "batch_projects.erp_triggers.on_sales_order_submit",
    },
    "Payment Entry": {
        "on_submit": "batch_projects.erp_triggers.on_payment_entry_submit",
    },
    # Single authority model for task creation/read/update validation —
    # applies on every save path (whitelisted API, generic REST, import, ORM),
    # not just the SPA's own endpoints.
    "BP Task": {
        "before_insert": "batch_projects.task_defaults.before_task_insert",
        "validate": "batch_projects.task_validation.validate_task",
        "after_insert": "batch_projects.task_defaults.after_task_insert",
    },
    # Generic doc-event trigger — widens erp.* coverage beyond the 4
    # hardcoded doctypes above. "*" fires for EVERY doctype site-wide;
    # on_any_doctype_event() bails in ~microseconds via a cached "does any
    # active rule even care" check before doing any real work, so this is
    # near-zero overhead for the common case of zero erp.doc_event rules.
    # The 4 specific handlers above stay as-is (real project-resolution
    # logic worth keeping, and they predate/are unaffected by this).
    "*": {
        "after_insert": "batch_projects.erp_triggers.on_any_doctype_event",
        "on_update": "batch_projects.erp_triggers.on_any_doctype_event",
        "on_submit": "batch_projects.erp_triggers.on_any_doctype_event",
        "on_cancel": "batch_projects.erp_triggers.on_any_doctype_event",
        "on_trash": "batch_projects.erp_triggers.on_any_doctype_event",
    },
    "BP Project Member": {
        # Revoked membership must not leave a stale watcher routing task
        # notifications to a user with no other access edge to that task.
        "after_delete": "batch_projects.membership_invariants.after_project_member_delete",
    },
    # Re-scopes rule authority at save time — a rule is a durable capability,
    # and the gateway's own service-account identity only proves who called
    # in, not what a saved rule is allowed to do. See automation_security.py.
    "BP Automation Rule": {
        "validate": "batch_projects.automation_security.validate_rule_authority",
    },
    # Same reasoning, for the graph-canvas surface — a workflow's action
    # nodes carry the exact same {type, config} shape a rule's actions do.
    # See workflow_security.py.
    "BP Workflow": {
        "validate": "batch_projects.workflow_security.validate_workflow_authority",
    },
}

# Task-email delivery authorization is enforced at the actual send()
# boundary via BPEmailQueue below, not a separate scheduled recheck — a
# scheduler job on Frappe v15's "all" cadence runs independently of and in
# unpredictable order relative to frappe.email.queue.flush (jobs are
# shuffled and enqueued independently), so it could not reliably run
# "immediately before" delivery. See secure_email_queue.py.

# Scheduled jobs
scheduler_events = {
    "hourly": [
        "batch_projects.events.send_scheduled_reports",
        "batch_projects.api.timers.send_timer_reminders",
    ],
    "daily": [
        "batch_projects.events.send_due_date_reminders",
        "batch_projects.events.run_due_soon_automations",
        "batch_projects.events.run_overdue_automations",
        "batch_projects.api.erp_link.reconcile_erpnext_sync",
        "batch_projects.events.purge_expired_trash",
        # Repairs BP Task.actual_hours when it drifts from the submitted
        # timesheets. The live rollup only fires on Timesheet submit/cancel,
        # so anything that moves hours outside that path (failed hook, patch,
        # import, direct row edit) silently desynced a field that feeds
        # billing and margin.
        "batch_projects.timesheet_sync.reconcile_actual_hours",
    ],
    "daily_long": [
        "batch_projects.events.send_daily_digest",
        "batch_projects.events.send_view_subscriptions_daily",
    ],
    "weekly_long": [
        "batch_projects.events.send_weekly_project_summary",
    ],
}
