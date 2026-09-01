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


# Project: aliases are ADDED to whatever controller is active, never replacing it.
#
# HRMS registers `hrms.overrides.employee_project.EmployeeProject` for Project,
# and frappe applies only ONE override — `class_overrides[doctype][-1]`, the
# last installed app. It does not chain. Registering ours would displace HRMS's
# controller on any site running HR, silently removing another app's behaviour,
# and the winner would flip with install order. Confirmed on a live site:
# get_controller("Project") returns EmployeeProject there.
#
# So instead of an override, the BP-named properties are attached to the class
# frappe already resolved. That leaves HRMS's controller exactly as it is and
# only adds attributes to it. The alternative was translating 159 Project field
# accesses by hand — each one a chance to silently read None, which is the
# failure mode this migration is most exposed to.
#
# add_bp_aliases() never shadows: it skips any name the class already defines.
# The alias names cannot collide with a native docfield either, by
# construction — they are exactly the BP fields that have no native equivalent
# (which is why they became custom fields) plus the mapped ones (which are
# mapped precisely because the native side spells them differently).

_project_aliases_installed = False


def install_project_aliases():
    """Attach BP-named properties to the active Project controller. Idempotent.

    Called from `before_request` and `before_job` so it covers both web traffic
    and background jobs; a module-level flag makes every call after the first a
    single boolean check.
    """
    global _project_aliases_installed
    if _project_aliases_installed:
        return
    try:
        from frappe.model.base_document import get_controller

        add_bp_aliases(get_controller("Project"), "Project")
        _project_aliases_installed = True
    except Exception:
        # A missing controller must not break request handling; the aliases are
        # a convenience over frappe's own get()/set().
        frappe.log_error(
            frappe.get_traceback(), "batch_projects: could not install Project aliases"
        )


def before_request():
    install_project_aliases()


def before_job(*args, **kwargs):
    install_project_aliases()
