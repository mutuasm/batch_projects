"""
batch_projects/bp_query.py
──────────────────────────
Query helpers that translate BP field names for whichever model is active.

The doctype re-key swapped `"BP Task"` for `TASK()` at 434 call sites, but a
doctype name is only half of a query. This still names columns that do not
exist on native Task:

    frappe.get_all(TASK(), fields=["title"], filters={"is_deleted": 0})

There are ~200 such sites. Editing each by hand is both a lot of judgement and
the wrong shape of work — the translation is entirely mechanical once you know
the doctype, and `native_adapter` already knows it. So these wrappers take the
already-resolved doctype, translate `fields` / `filters` / `pluck` / `order_by`
/ `group_by` when it is a native one, and delegate.

With the switch off every function is a pass-through: same arguments, same
frappe call, same result. That is what lets the call-site conversion land
incrementally.

Not covered on purpose
──────────────────────
`or_filters` in list-of-list form, and any filter that is not a dict. The
adapter deliberately refuses to half-translate those (see `native_filters`),
and guessing here would be worse — a filter naming the right doctype and the
wrong column returns silently wrong rows rather than raising. Those few sites
resolve their names explicitly with `task_field()` / `project_field()`;
`api/board.py`'s search `or_filters` is the worked example.
"""

import frappe

from batch_projects.doctypes import PROJECT, TASK, use_native

# Which adapter doctype a resolved doctype name belongs to. Both spellings are
# accepted so a caller need not care whether the switch is on.
_NATIVE_OF = {
    "BP Project": "Project",
    "Project": "Project",
    "BP Task": "Task",
    "Task": "Task",
}


def _target(doctype):
    """The native doctype to translate against, or None to pass through."""
    if not use_native():
        return None
    return _NATIVE_OF.get(doctype)


def _fields(target, value):
    if value is None:
        return None
    from batch_projects.native_adapter import native_fields

    if isinstance(value, str):
        resolved = native_fields(target, [value])
        return resolved[0] if resolved else value
    return native_fields(target, list(value))


def _filters(target, value):
    from batch_projects.native_adapter import native_filters

    return native_filters(target, value)


def _order(target, clause):
    """Translate the field names in an `order_by` / `group_by` clause.

    A clause is `"<field> [asc|desc]"`, possibly comma separated. Only the
    field part is translated; direction and any expression we do not recognise
    is left exactly as written.
    """
    if not clause or not isinstance(clause, str):
        return clause
    from batch_projects.native_adapter import UnknownNativeField, native_field

    out = []
    for part in clause.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        try:
            bits[0] = native_field(target, bits[0]) or bits[0]
        except UnknownNativeField:
            pass  # an expression or a field we do not own — leave it alone
        out.append(" ".join(bits))
    return ", ".join(out)


def _translate(doctype, kwargs):
    target = _target(doctype)
    if not target:
        return kwargs
    out = dict(kwargs)
    if "fields" in out:
        out["fields"] = _fields(target, out["fields"])
    if "pluck" in out and isinstance(out["pluck"], str):
        out["pluck"] = _fields(target, out["pluck"])
    if "filters" in out:
        out["filters"] = _filters(target, out["filters"])
    for clause in ("order_by", "group_by"):
        if out.get(clause):
            out[clause] = _order(target, out[clause])
    return out


def get_all(doctype, **kwargs):
    return frappe.get_all(doctype, **_translate(doctype, kwargs))


def get_list(doctype, **kwargs):
    return frappe.get_list(doctype, **_translate(doctype, kwargs))


def db_get_all(doctype, **kwargs):
    return frappe.db.get_all(doctype, **_translate(doctype, kwargs))


def get_value(doctype, filters=None, fieldname="name", **kwargs):
    """frappe.db.get_value with both `filters` and `fieldname` translated.

    `filters` is often a bare record name rather than a dict; that passes
    through untouched, since a name is not a field reference.
    """
    target = _target(doctype)
    if target:
        if isinstance(filters, dict):
            filters = _filters(target, filters)
        fieldname = _fields(target, fieldname)
        if kwargs.get("order_by"):
            kwargs["order_by"] = _order(target, kwargs["order_by"])
    return frappe.db.get_value(doctype, filters, fieldname, **kwargs)


def set_value(doctype, filters, fieldname, value=None, **kwargs):
    """frappe.db.set_value. `fieldname` may also be a {field: value} dict."""
    target = _target(doctype)
    if target:
        if isinstance(filters, dict):
            filters = _filters(target, filters)
        if isinstance(fieldname, dict):
            fieldname = {_fields(target, k): v for k, v in fieldname.items()}
        else:
            fieldname = _fields(target, fieldname)
    return frappe.db.set_value(doctype, filters, fieldname, value, **kwargs)


def exists(doctype, filters=None, **kwargs):
    target = _target(doctype)
    if target and isinstance(filters, dict):
        filters = _filters(target, filters)
    return frappe.db.exists(doctype, filters, **kwargs)


def count(doctype, filters=None, **kwargs):
    target = _target(doctype)
    if target and isinstance(filters, dict):
        filters = _filters(target, filters)
    # Passed as a keyword because that is frappe's own parameter name here, and
    # because callers (and the tests that patch this) inspect
    # call_args.kwargs["filters"]. Positional would still work but would break
    # that introspection silently. `exists` and `set_value` take `dn` rather
    # than `filters`, so they stay positional on purpose.
    return frappe.db.count(doctype, filters=filters, **kwargs)
