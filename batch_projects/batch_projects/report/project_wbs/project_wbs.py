"""Work-breakdown structure over the project hierarchy.

Native Project is not a nested set — unlike Task, which is — so there is no
tree view to hang project-level WBS on. The hierarchy itself does exist:
`custom_parent_project` is created by setup/native_fields and is what a child
project points at.

A script report with `tree: true` is what closes that gap without touching
ERPNext's own doctype. Making Project a nested set would mean adding lft/rgt
and swapping its controller for one app's feature, on a doctype HRMS and
several ERPNext modules already build on — a much larger blast radius than a
report that reads a Link field.

Rows are emitted depth-first with an `indent`, which is what frappe's datatable
renders as an expandable level.

Visibility: rows come from `frappe.get_list`, NOT `frappe.db.sql`, so the
permission query conditions this app registers for Project apply exactly as
they do everywhere else. A WBS that reached past them would be a disclosure
bug, and a report is an easy place to introduce one by reaching for raw SQL.
"""

import frappe
from frappe import _

# Deeper than any real breakdown; a plain Link cannot prevent a cycle, and a
# cycle here would otherwise recurse until the worker died.
_MAX_DEPTH = 32


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return _columns(), _rows(filters)


def _columns():
    return [
        {
            "fieldname": "project",
            "label": _("Project"),
            "fieldtype": "Link",
            "options": "Project",
            "width": 300,
        },
        {"fieldname": "project_name", "label": _("Name"), "fieldtype": "Data", "width": 240},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {
            "fieldname": "percent_complete",
            "label": _("% Complete"),
            "fieldtype": "Percent",
            "width": 110,
        },
        {
            "fieldname": "expected_start_date",
            "label": _("Start"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "expected_end_date",
            "label": _("End"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "tasks",
            "label": _("Tasks"),
            "fieldtype": "Int",
            "width": 80,
        },
    ]


def _fetch(filters):
    conditions = {}
    if filters.get("company"):
        conditions["company"] = filters.company
    if filters.get("status"):
        conditions["status"] = filters.status
    elif not filters.get("include_completed"):
        conditions["status"] = ["!=", "Completed"]

    return frappe.get_list(
        "Project",
        filters=conditions,
        fields=[
            "name",
            "project_name",
            "status",
            "percent_complete",
            "expected_start_date",
            "expected_end_date",
            "custom_parent_project",
        ],
        order_by="project_name asc",
        limit_page_length=0,
    )


def _task_counts(names):
    if not names:
        return {}
    # Dict syntax, not "count(name) as n": v16's query builder rejects SQL
    # functions written as strings in `fields`.
    rows = frappe.get_all(
        "Task",
        filters={"project": ["in", names]},
        fields=["project", {"COUNT": "*"}],
        group_by="project",
        limit_page_length=0,
    )
    return {r["project"]: r.get("COUNT(*)") or 0 for r in rows}


def _rows(filters):
    projects = _fetch(filters)
    if not projects:
        return []
    return build_tree(projects, _task_counts([p["name"] for p in projects]))


def build_tree(projects, counts=None):
    """Order projects depth-first and give each row its `indent`.

    Separated from the query so the part with the actual decisions in it —
    ordering, orphan handling, cycle refusal — is testable without a site
    that has a Company (native Project cannot be created without one, and a
    fresh CI site has none).
    """
    counts = counts or {}
    visible = {p["name"] for p in projects}

    children = {}
    roots = []
    for p in projects:
        parent = p.get("custom_parent_project")
        # A parent filtered out of this run (or deleted) must not take its
        # children with it — they surface at the top rather than vanishing.
        if parent and parent in visible:
            children.setdefault(parent, []).append(p)
        else:
            roots.append(p)

    out = []
    seen = set()

    def walk(node, indent):
        if node["name"] in seen or indent > _MAX_DEPTH:
            # A cycle, or deeper than any genuine breakdown. Dropping the row
            # is the only safe move: rendering it again would loop forever.
            return
        seen.add(node["name"])
        out.append(
            {
                "project": node["name"],
                "project_name": node.get("project_name"),
                "status": node.get("status"),
                "percent_complete": node.get("percent_complete"),
                "expected_start_date": node.get("expected_start_date"),
                "expected_end_date": node.get("expected_end_date"),
                "tasks": counts.get(node["name"], 0),
                "indent": indent,
            }
        )
        for child in children.get(node["name"], []):
            walk(child, indent + 1)

    for root in roots:
        walk(root, 0)

    # Anything left unvisited was only reachable through a cycle. Emitting it
    # flat is better than silently dropping a project from a WBS.
    for p in projects:
        if p["name"] not in seen:
            walk(p, 0)

    return out
