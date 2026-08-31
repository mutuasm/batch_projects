"""
batch_projects/native_adapter.py
────────────────────────────────
Translation between BP field names and their native `Project`/`Task`
equivalents, so the ~434 doctype references can be switched over without
hand-editing every field name at every call site.

Why this exists rather than a bulk rename
─────────────────────────────────────────
84 BP field names change when the model moves to native Project/Task, and a
word-boundary search finds ~5,400 textual occurrences of them across the app.
Those cannot be mechanically replaced: `title` alone appears ~400 times and
means BP Task's title in some places, BP Project's in others, a dict key in
others, and a UI label elsewhere. A blind rename would corrupt code while
looking plausible.

So the field names stay as they are at call sites, and the translation happens
once, here, at the boundary where a query or a write is built.

Resolution order, per doctype (order matters — `description` is a mapped field
on Project but a verbatim one on Task):

    1. NATIVE_FIELD_MAP  — a native field already means this (title -> subject).
       `None` means the concept is gone entirely (erpnext_project).
    2. shared verbatim   — the name is identical on both (status, priority,
       project, company, ...).
    3. custom_<field>    — one of ours, added as a Custom Field.
    4. unknown           — raises. Deliberately loud: a silent pass-through
       would read a nonexistent column and quietly return None, which is the
       failure mode this whole migration most needs to avoid.

Enum values are translated too, not just names. `status` is spelled the same on
both models but its *vocabulary* differs — BP task status is a free-text
per-project workflow state, native is a closed Select. A filter of
`{"status": "In Progress"}` is meaningless natively, so callers must go through
`native_filters`, which maps the value as well.
"""

import frappe

from batch_projects.setup.native_fields import CUSTOM_FIELDS, NATIVE_FIELD_MAP
from batch_projects.setup.native_migration import (
    _CATEGORY_TO_TASK_STATUS,
    _PROJECT_STATUS,
    _TASK_PRIORITY,
)

# BP doctype -> the native doctype replacing it.
DOCTYPE_MAP = {
    "BP Project": "Project",
    "BP Task": "Task",
}

# Field names identical on both models, verified against live v16 meta.
_SHARED = {
    "Project": {"company", "project_name", "project_type", "status"},
    "Task": {
        "completed_by",
        "completed_on",
        "description",
        "parent_task",
        "priority",
        "project",
        "status",
    },
}


class UnknownNativeField(KeyError):
    """A BP field with no native counterpart, mapping, or custom field."""


def _custom_names(doctype):
    return {row["fieldname"] for row in CUSTOM_FIELDS.get(doctype, [])}


def native_doctype(bp_doctype):
    """"BP Task" -> "Task". Unmapped doctypes pass through unchanged."""
    return DOCTYPE_MAP.get(bp_doctype, bp_doctype)


def native_field(doctype, bp_field):
    """The native field to read/write for a BP field name.

    `doctype` is the NATIVE doctype ("Project"/"Task"). Returns None when the
    concept has no native counterpart at all, so callers can drop it.
    """
    mapped = NATIVE_FIELD_MAP.get(doctype, {})
    if bp_field in mapped:
        return mapped[bp_field]  # may legitimately be None

    if bp_field in _SHARED.get(doctype, set()):
        return bp_field

    candidate = f"custom_{bp_field}"
    if candidate in _custom_names(doctype):
        return candidate

    # Frappe's own standard fields are always available.
    if bp_field in {"name", "owner", "creation", "modified", "modified_by", "idx", "docstatus"}:
        return bp_field

    raise UnknownNativeField(
        f"{doctype}: no native field for BP field {bp_field!r}. Add it to "
        f"native_fields.CUSTOM_FIELDS, or map it in NATIVE_FIELD_MAP."
    )


def native_fields(doctype, bp_fields):
    """Translate a `fields=[...]` list, dropping concepts with no counterpart."""
    out = []
    for f in bp_fields:
        resolved = native_field(doctype, f)
        if resolved:
            out.append(resolved)
    return out


def native_status(doctype, value, workflow_categories=None):
    """Translate a status VALUE into the native vocabulary.

    Task status is the hard case: BP holds a per-project workflow-state name,
    native holds one of a closed set. `workflow_categories` is the
    {state name: category} map for the relevant project (see
    native_migration._workflow_categories); without it an unrecognised state
    falls back to the `unstarted` category rather than guessing.
    """
    if value in (None, ""):
        return value

    if doctype == "Project":
        mapped = _PROJECT_STATUS.get(value)
        return mapped[0] if mapped else value

    category = (workflow_categories or {}).get(str(value), "unstarted")
    return _CATEGORY_TO_TASK_STATUS.get(category, "Open")


def native_priority(value):
    return _TASK_PRIORITY.get(value, value) if value else value


def native_filters(doctype, filters, workflow_categories=None):
    """Translate a filters dict's keys AND its enum values.

    Only dict filters are handled. Frappe also accepts list-of-list filters;
    those are passed back untouched rather than half-translated, because a
    silently partial translation is worse than an obvious no-op — callers using
    list filters must translate explicitly.
    """
    if not isinstance(filters, dict):
        return filters

    out = {}
    for key, value in filters.items():
        resolved = native_field(doctype, key)
        if not resolved:
            continue  # concept dropped under the native model
        if resolved == "status" and not isinstance(value, (list, tuple)):
            value = native_status(doctype, value, workflow_categories)
        elif resolved == "priority" and doctype == "Task" and not isinstance(value, (list, tuple)):
            value = native_priority(value)
        out[resolved] = value
    return out


def workflow_categories_for(project):
    """{state name: category} for a native Project, from its BP counterpart.

    After migration the workflow-state catalog still lives on the BP Project
    row (it has no native home — native Task.status is a fixed Select), so the
    lookup goes back through the mapping anchor.
    """
    if not project:
        return {}
    bp_project = frappe.db.get_value("BP Project", {"erpnext_project": project}, "name")
    if not bp_project:
        return {}
    from batch_projects.setup.native_migration import _workflow_categories

    return _workflow_categories(bp_project)
