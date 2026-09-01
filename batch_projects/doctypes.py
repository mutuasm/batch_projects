"""
batch_projects/doctypes.py
──────────────────────────
Which doctype the app means by "a project" and "a task" — behind one switch.

The native migration cannot be re-keyed incrementally without this. 434 call
sites name `"BP Task"` / `"BP Project"` as string literals, and flipping any
subset of them mid-way breaks the app: the data has not moved yet, the satellite
Links still hold BP row names, and Project has no alias shim. So a half-converted
tree is a broken tree.

Routing every call site through `TASK()` / `PROJECT()` removes that problem.
Converting a file is behaviour-preserving while the switch is off, so the
re-key lands in reviewable pieces and the actual cutover is one setting.

Activation is `bp_use_native_doctypes: true` in site_config.json, and it is
NOT merely a rename — it is only correct once:

    1. the migration has run (native rows exist for every BP row)
    2. satellite Links have been retargeted to the native names
    3. every call site reads through TASK()/PROJECT() and the query adapter

`native_migration.dry_run_native_migration()` reports on 1 and 2 without
writing anything. Turning the switch on before those hold gives an app reading
empty tables, which is why it is a deliberate site setting rather than a
version bump.

Read through a function, not a module constant: site_config is per-site and can
change without a code deploy, and a constant resolved at import would freeze
whatever the first-loaded site happened to say — actively wrong on a multi-site
bench.
"""

import frappe

_FLAG = "bp_use_native_doctypes"

# What the app is moving from, and to.
_BP_PROJECT, _NATIVE_PROJECT = "BP Project", "Project"
_BP_TASK, _NATIVE_TASK = "BP Task", "Task"


def use_native() -> bool:
    """Whether this site has switched to ERPNext's native Project/Task."""
    return bool(frappe.conf.get(_FLAG))


def PROJECT() -> str:
    return _NATIVE_PROJECT if use_native() else _BP_PROJECT


def TASK() -> str:
    return _NATIVE_TASK if use_native() else _BP_TASK


def project_field(name: str) -> str:
    """Translate a BP Project field name for whichever model is active."""
    if not use_native():
        return name
    from batch_projects.native_adapter import native_field

    return native_field(_NATIVE_PROJECT, name)


def task_field(name: str) -> str:
    """Translate a BP Task field name for whichever model is active."""
    if not use_native():
        return name
    from batch_projects.native_adapter import native_field

    return native_field(_NATIVE_TASK, name)


def project_filters(filters, workflow_categories=None):
    """Translate a filters dict for whichever model is active."""
    if not use_native():
        return filters
    from batch_projects.native_adapter import native_filters

    return native_filters(_NATIVE_PROJECT, filters, workflow_categories)


def task_filters(filters, workflow_categories=None):
    if not use_native():
        return filters
    from batch_projects.native_adapter import native_filters

    return native_filters(_NATIVE_TASK, filters, workflow_categories)


def project_fields(fields):
    """Translate a `fields=[...]` list for whichever model is active."""
    if not use_native():
        return fields
    from batch_projects.native_adapter import native_fields

    return native_fields(_NATIVE_PROJECT, fields)


def task_fields(fields):
    if not use_native():
        return fields
    from batch_projects.native_adapter import native_fields

    return native_fields(_NATIVE_TASK, fields)
