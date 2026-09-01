"""
batch_projects/native_controllers.py
────────────────────────────────────
A controller subclass that lets ERPNext's native `Task` answer to the BP field
names, so the switch to native doctypes does not require editing ~5,400 field
references by hand.

Task only. Project is left alone because HRMS already owns that controller —
see the note at the bottom of this file.

Why a controller shim and not a rename
──────────────────────────────────────
84 BP field names change under the native model. A word-boundary search finds
~5,400 textual occurrences, and they cannot be bulk-replaced: `title` alone
appears ~400 times and means BP Task's title in some places, BP Project's in
others, a dict key in others, a UI label elsewhere. A blind rename would corrupt
code while looking entirely plausible in review.

So instead: `doc.title` keeps working on a native Task, because `title` is a
property here that reads and writes `subject`.

What this does NOT cover
────────────────────────
Queries. `frappe.get_all("Task", fields=["title"], filters={"is_deleted": 0})`
never constructs a Document, so no property is consulted — it goes straight to
SQL and would fail on a column that does not exist. Those call sites go through
`native_adapter.native_fields` / `native_filters` instead. The two mechanisms
are complementary and both are needed:

    document access  -> this module
    query building   -> native_adapter

Names that are already Document attributes are never shadowed. `name`, `owner`,
`status`, `project` and friends either mean the same thing on both models or are
framework-owned, and quietly overriding one of those would be a far worse bug
than the one this solves.
"""

import frappe

from batch_projects.setup.native_fields import CUSTOM_FIELDS, NATIVE_FIELD_MAP


def _bp_to_native(doctype: str) -> dict[str, str]:
    """BP field name -> the native field backing it, for one doctype."""
    mapping = {}
    for bp_field, native_field in NATIVE_FIELD_MAP.get(doctype, {}).items():
        if native_field:  # None = the concept is gone; nothing to proxy
            mapping[bp_field] = native_field
    for row in CUSTOM_FIELDS.get(doctype, []):
        mapping[row["fieldname"][len("custom_") :]] = row["fieldname"]
    return mapping


def _make_property(native_field: str):
    def getter(self):
        return self.get(native_field)

    def setter(self, value):
        self.set(native_field, value)

    return property(getter, setter, doc=f"BP alias for `{native_field}`.")


def add_bp_aliases(cls, doctype: str):
    """Attach BP-named properties to a native controller class.

    Skips any name the base class already defines. That guard matters more than
    it looks: shadowing something like `name` or a Document method with a
    property would break the framework in ways that surface far from here.
    """
    attached = []
    for bp_field, native_field in _bp_to_native(doctype).items():
        if bp_field == native_field:
            continue  # same name on both models — nothing to alias
        if hasattr(cls, bp_field):
            continue  # never shadow an existing attribute or method
        setattr(cls, bp_field, _make_property(native_field))
        attached.append(bp_field)
    cls._bp_aliases = tuple(sorted(attached))
    return cls


# The base class is imported directly from erpnext, NOT via get_controller():
# frappe resolves an override by importing this module, so calling
# get_controller("Task") here would re-enter that resolution and recurse. The
# first attempt did exactly that, the exception was swallowed by a try/except,
# the classes were never defined, and frappe failed with
# "issubclass() arg 1 must be a class" — a None where a class should be.
from erpnext.projects.doctype.task.task import Task as _TaskBase


class BPTask(_TaskBase):
    """Native Task, answering to BP Task's field names."""


add_bp_aliases(BPTask, "Task")


# Project is deliberately NOT overridden.
#
# HRMS already registers `hrms.overrides.employee_project.EmployeeProject` for
# Project, and frappe applies only ONE override — `class_overrides[doctype][-1]`,
# the last installed app. It does not chain them. Registering ours would
# therefore displace HRMS's controller on any site running HR, silently removing
# behaviour that belongs to another app, and the winner would flip with install
# order. Confirmed on a live site: get_controller("Project") returns
# EmployeeProject there.
#
# Project field access goes through native_adapter instead, which needs no
# controller and cannot collide with another app.
