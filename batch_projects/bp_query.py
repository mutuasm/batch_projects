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


def _translate_positional(target, args, kwargs, names):
    """Translate arguments without changing whether they were positional.

    A wrapper that normalises call shape is not a pass-through. Two tests
    proved it from opposite directions: one asserts on
    `call_args.kwargs["filters"]`, the other on `call_args.args[1]`, because
    the two original call sites passed filters differently. Forwarding exactly
    as received keeps both true — and keeps the "OFF changes nothing" promise
    honest for any other caller that introspects these calls.

    `names` maps each positional slot (after the doctype) to how it should be
    translated: "filters" or "fields".
    """
    args = list(args)
    for index, kind in enumerate(names):
        if index < len(args):
            args[index] = (
                _filters(target, args[index])
                if kind == "filters" and isinstance(args[index], dict)
                else _fields(target, args[index]) if kind == "fields" else args[index]
            )
        elif kind in kwargs:
            value = kwargs[kind]
            if kind == "filters" and isinstance(value, dict):
                kwargs[kind] = _filters(target, value)
            elif kind == "fields":
                kwargs[kind] = _fields(target, value)
    return args, kwargs


def get_value(doctype, *args, **kwargs):
    """frappe.db.get_value(doctype, filters, fieldname, ...).

    `filters` is often a bare record name rather than a dict; a name is not a
    field reference, so it passes through untouched.
    """
    target = _target(doctype)
    if target:
        args, kwargs = _translate_positional(target, args, kwargs, ["filters", "fieldname"])
        if "fieldname" in kwargs:
            kwargs["fieldname"] = _fields(target, kwargs["fieldname"])
        if len(args) > 1:
            args[1] = _fields(target, args[1])
        if kwargs.get("order_by"):
            kwargs["order_by"] = _order(target, kwargs["order_by"])
    return frappe.db.get_value(doctype, *args, **kwargs)


def set_value(doctype, *args, **kwargs):
    """frappe.db.set_value(doctype, dn, fieldname, value, ...).

    `fieldname` may also be a {field: value} dict.
    """
    target = _target(doctype)
    if target:
        args = list(args)
        if args and isinstance(args[0], dict):
            args[0] = _filters(target, args[0])
        if len(args) > 1:
            args[1] = (
                {_fields(target, k): v for k, v in args[1].items()}
                if isinstance(args[1], dict)
                else _fields(target, args[1])
            )
        elif "fieldname" in kwargs:
            kwargs["fieldname"] = _fields(target, kwargs["fieldname"])
    return frappe.db.set_value(doctype, *args, **kwargs)


def exists(doctype, *args, **kwargs):
    target = _target(doctype)
    if target:
        args = list(args)
        if args and isinstance(args[0], dict):
            args[0] = _filters(target, args[0])
        elif "dn" in kwargs and isinstance(kwargs["dn"], dict):
            kwargs["dn"] = _filters(target, kwargs["dn"])
    return frappe.db.exists(doctype, *args, **kwargs)


def count(doctype, *args, **kwargs):
    target = _target(doctype)
    if target:
        args, kwargs = _translate_positional(target, args, kwargs, ["filters"])
    return frappe.db.count(doctype, *args, **kwargs)
