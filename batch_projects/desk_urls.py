"""
batch_projects/desk_urls.py
───────────────────────────
Deep links into the desk, for notification emails and CTAs.

Every one of these used to point at a `/workspace/...` route served by the Vue
SPA. The SPA is gone, so those links now 404 — and they are the links that reach
people *outside* the app, in email, which makes them the worst place to leave a
dead URL. This module is the single place they are built.

Destinations are the BP doctype forms and lists, because BP Project / BP Task
are still the model at this stage. When the native migration is activated, only
this file changes: `_TASK` and `_PROJECT` become `Task` and `Project` and every
call site follows.

v16 serves the desk at `/desk`; `/app` still works via a redirect frappe ships,
but there is no reason to send people through an extra hop.
"""

import frappe

_DESK = "/desk"

# The doctypes these links address. Two constants rather than inline strings so
# activation is a two-line change here instead of a hunt through email code.
_PROJECT = "BP Project"
_TASK = "BP Task"


def slug(doctype: str) -> str:
    """"BP Task" -> "bp-task", frappe's own route slug."""
    return doctype.lower().replace(" ", "-")


def _abs(path: str) -> str:
    return f"{frappe.utils.get_url()}{path}"


def form_url(doctype: str, name: str) -> str:
    """Link to one record's form."""
    return _abs(f"{_DESK}/{slug(doctype)}/{frappe.utils.quoted(name)}")


def list_url(doctype: str, filters: dict | None = None) -> str:
    """Link to a list view, optionally filtered."""
    path = f"{_DESK}/{slug(doctype)}"
    if filters:
        from urllib.parse import urlencode

        path = f"{path}?{urlencode(filters)}"
    return _abs(path)


def project_url(project: str | None) -> str:
    """The project's own record, or the Projects workspace when unknown."""
    if not project:
        return _abs(f"{_DESK}/projects")
    return form_url(_PROJECT, project)


def project_tasks_url(project: str | None) -> str:
    """The project's task list — the closest desk equivalent of its board."""
    if not project:
        return _abs(f"{_DESK}/{slug(_TASK)}")
    return list_url(_TASK, {"project": project})


def task_url(project: str | None, task_key: str | None) -> str:
    """A single task.

    BP Task autonames `field:task_key`, so the key IS the record name and this
    can address the form directly rather than going via a filtered list.
    """
    if task_key:
        return form_url(_TASK, task_key)
    return project_tasks_url(project)


def my_tasks_url() -> str:
    """Tasks assigned to the reader.

    `_assign` is frappe's own ToDo-backed assignment field, which its list views
    filter on — so this works without the app owning a "my tasks" view.
    """
    return list_url(_TASK, {"_assign": f'["like","%{frappe.session.user}%"]'})


def report_url(report_name: str) -> str:
    return form_url("BP Report", report_name)


def saved_view_url(view_name: str) -> str:
    return form_url("BP View", view_name)


def notification_settings_url() -> str:
    """Where a recipient manages what email they get.

    Every notification email footer points here, so it must resolve for an
    ordinary member, not only an admin.
    """
    return _abs(f"{_DESK}/{slug('BP Notification Preference')}")


def workspace_settings_url() -> str:
    return _abs(f"{_DESK}/{slug('BP Workspace Settings')}")
