"""Work-breakdown ordering for the Project WBS report.

Native Project is not a nested set — Task is, Project isn't — so project-level
hierarchy has no tree view to sit in. `custom_parent_project` holds the
relationship and this report renders it, using frappe's `tree: true` datatable
support, which draws whatever `indent` each row carries.

Nearly everything here exercises `build_tree` directly rather than `execute`.
That is not test convenience: creating a native Project requires a Company, a
fresh CI site has none, and an earlier test in this app quietly skipped its
whole class for exactly that reason while CI reported success. The decisions
worth testing — depth-first order, orphan rescue, cycle refusal — are all in
build_tree and need no site data at all.

Run with:
    bench run-tests --module batch_projects.tests.test_project_wbs
"""

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from batch_projects.batch_projects.report.project_wbs.project_wbs import (
    _MAX_DEPTH,
    build_tree,
    execute,
)


def _p(name, parent=None):
    return {
        "name": name,
        "project_name": name.lower(),
        "status": "Open",
        "percent_complete": 0,
        "expected_start_date": None,
        "expected_end_date": None,
        "custom_parent_project": parent,
    }


def _order(rows):
    return [(r["project"], r["indent"]) for r in rows]


class TestBuildTree(UnitTestCase):
    def test_unrelated_projects_are_all_roots(self):
        rows = build_tree([_p("A"), _p("B")])
        self.assertEqual(_order(rows), [("A", 0), ("B", 0)])

    def test_children_follow_their_parent_depth_first(self):
        """A child must be adjacent to its parent; the datatable builds the
        tree from row order plus indent, not from the parent value."""
        rows = build_tree([_p("A"), _p("B", "A"), _p("C", "B"), _p("D")])
        self.assertEqual(_order(rows), [("A", 0), ("B", 1), ("C", 2), ("D", 0)])

    def test_every_project_appears_exactly_once(self):
        rows = build_tree([_p("A"), _p("B", "A"), _p("C", "A")])
        self.assertEqual(sorted(r["project"] for r in rows), ["A", "B", "C"])

    def test_a_child_whose_parent_is_filtered_out_is_not_lost(self):
        """The parent may be excluded by the report's own filters. Dropping its
        children with it would silently hide projects from a WBS."""
        rows = build_tree([_p("B", "A-not-in-this-run")])
        self.assertEqual(_order(rows), [("B", 0)])

    def test_task_counts_are_attached(self):
        rows = build_tree([_p("A")], {"A": 7})
        self.assertEqual(rows[0]["tasks"], 7)

    def test_a_missing_count_is_zero_not_none(self):
        self.assertEqual(build_tree([_p("A")])[0]["tasks"], 0)


class TestCyclesAndDepth(UnitTestCase):
    """custom_parent_project is a plain Link and cannot prevent a cycle."""

    def test_a_two_node_cycle_terminates_and_keeps_both(self):
        rows = build_tree([_p("A", "B"), _p("B", "A")])
        self.assertEqual(sorted(r["project"] for r in rows), ["A", "B"])

    def test_a_self_parent_terminates_and_keeps_the_row(self):
        rows = build_tree([_p("A", "A")])
        self.assertEqual([r["project"] for r in rows], ["A"])

    def test_a_deep_chain_is_truncated_rather_than_recursing_away(self):
        depth = _MAX_DEPTH + 20
        chain = [_p("n0")] + [_p(f"n{i}", f"n{i - 1}") for i in range(1, depth)]
        rows = build_tree(chain)
        self.assertLessEqual(max(r["indent"] for r in rows), _MAX_DEPTH)


class TestReportRuns(IntegrationTestCase):
    """One end-to-end pass, to catch a query the pure tests cannot see.

    `_task_counts` in particular is exactly the kind of thing that breaks
    silently: v16 rejects SQL functions written as strings in `fields`, which
    the first version of this report did.
    """

    def test_execute_returns_columns_and_indented_rows(self):
        columns, rows = execute({})
        self.assertTrue(columns)
        self.assertIn("project", [c["fieldname"] for c in columns])
        for row in rows:
            self.assertIn("indent", row)
            self.assertIsInstance(row["tasks"], int)

    def test_the_report_is_registered_as_a_standard_report(self):
        import json
        import pathlib

        path = (
            pathlib.Path(frappe.get_app_path("batch_projects"))
            / "batch_projects/report/project_wbs/project_wbs.json"
        )
        meta = json.loads(path.read_text())
        self.assertEqual(meta["report_type"], "Script Report")
        self.assertEqual(meta["ref_doctype"], "Project")
        self.assertEqual(meta["is_standard"], "Yes")


class TestSidebarEntry(IntegrationTestCase):
    """The sidebar link and the report name must not drift apart.

    test_sidebar_targets covers this app's own Workspace Sidebar; these items
    are appended to ERPNext's `Projects` sidebar instead, so nothing else
    checks them. A renamed report would leave a link that goes nowhere and the
    desk would not complain.
    """

    def test_the_wbs_link_names_the_report_that_exists(self):
        import json
        import pathlib as _pl

        from batch_projects.setup.projects_module import _EXTRA_ITEMS

        meta = json.loads(
            (
                _pl.Path(frappe.get_app_path("batch_projects"))
                / "batch_projects/report/project_wbs/project_wbs.json"
            ).read_text()
        )
        item = next(i for i in _EXTRA_ITEMS if i["label"] == "Project WBS")
        self.assertEqual(item["url"], f"/desk/query-report/{meta['report_name']}")

    def test_every_extra_sidebar_item_stays_inside_the_desk(self):
        from batch_projects.setup.projects_module import _EXTRA_ITEMS

        for item in _EXTRA_ITEMS:
            self.assertTrue(
                str(item.get("url", "")).startswith("/desk/"),
                f"{item['label']} points outside the desk: {item.get('url')}",
            )
