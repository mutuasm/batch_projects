"""BP Task's parent/child structure must survive the native migration.

Before migrate_task_hierarchy existed, it did not: migrate_task never set
parent_task, so every migrated task arrived as a root and the nesting was
silently gone. Silently is the operative word — nothing failed, the tasks were
all present and correct, and only the shape was missing.

The load-bearing assertion here is on `lft`/`rgt`, not on parent_task. Native
Task is a NestedSet and its tree view reads the nested-set bounds, so a
parent_task written with db.set_value would produce exactly the bug this guards
against: a correct-looking parent_task column and a tree that renders the wrong
structure.

`frappe.db.commit` is stubbed throughout so IntegrationTestCase's rollback still
works — the migration commits by design, being written for a patch.

Run with:
    bench run-tests --module batch_projects.tests.test_native_hierarchy
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from batch_projects.setup.native_migration import (
    _bp_parent_chain_is_cyclic,
    migrate_task_hierarchy,
)


class TestCycleGuard(UnitTestCase):
    def test_a_plain_chain_is_not_cyclic(self):
        chain = {"c": "b", "b": "a"}
        self.assertFalse(_bp_parent_chain_is_cyclic("c", chain))

    def test_a_two_node_loop_is_cyclic(self):
        self.assertTrue(_bp_parent_chain_is_cyclic("a", {"a": "b", "b": "a"}))

    def test_self_parent_is_cyclic(self):
        self.assertTrue(_bp_parent_chain_is_cyclic("a", {"a": "a"}))

    def test_a_runaway_chain_is_refused(self):
        """Longer than any real breakdown — refuse rather than walk forever."""
        chain = {f"n{i}": f"n{i + 1}" for i in range(500)}
        self.assertTrue(_bp_parent_chain_is_cyclic("n0", chain))

    def test_an_orphan_is_not_cyclic(self):
        self.assertFalse(_bp_parent_chain_is_cyclic("a", {}))


class TestHierarchyMigration(IntegrationTestCase):
    """Builds a two-level BP tree already anchored to native tasks, then runs
    only the hierarchy pass over it."""

    def setUp(self):
        super().setUp()
        commit = patch.object(frappe.db, "commit", lambda *a, **k: None)
        commit.start()
        self.addCleanup(commit.stop)

        # Two projects, because the two models are still separate here:
        # BP Task.project links to BP Project, native Task.project to Project.
        # The hierarchy pass reads neither — only parent_task and the
        # erpnext_task anchor — but both links have to resolve on insert.
        tag = frappe.generate_hash("", 8)
        self.project = frappe.get_doc(
            {"doctype": "Project", "project_name": f"hier {tag}"}
        ).insert(ignore_permissions=True)
        self.bp_project = frappe.get_doc(
            {"doctype": "BP Project", "project_name": f"hier bp {tag}", "key": tag[:6].upper()}
        )
        self.bp_project.flags.ignore_mandatory = True
        self.bp_project.insert(ignore_permissions=True)

        self.native = {}
        self.bp = {}
        for key in ("epic", "story", "loner"):
            self.native[key] = frappe.get_doc(
                {
                    "doctype": "Task",
                    "subject": f"{key} {frappe.generate_hash('', 6)}",
                    "project": self.project.name,
                }
            ).insert(ignore_permissions=True)

    def _bp(self, key, parent_key=None):
        doc = frappe.get_doc(
            {
                "doctype": "BP Task",
                "task_key": f"HIER-{frappe.generate_hash('', 6).upper()}",
                "title": key,
                "project": self.bp_project.name,
                "erpnext_task": self.native[key].name,
            }
        )
        if parent_key:
            doc.parent_task = self.bp[parent_key].name
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        self.bp[key] = doc
        return doc

    def test_parent_is_marked_a_group_and_child_is_attached(self):
        self._bp("epic")
        self._bp("story", parent_key="epic")

        stats = migrate_task_hierarchy()
        self.assertEqual(stats["linked"], 1, stats)
        self.assertEqual(stats["groups"], 1, stats)

        child = frappe.get_doc("Task", self.native["story"].name)
        self.assertEqual(child.parent_task, self.native["epic"].name)
        self.assertTrue(
            frappe.db.get_value("Task", self.native["epic"].name, "is_group"),
            "parent was not marked is_group; ERPNext would reject the child",
        )

    def test_nested_set_bounds_actually_nest(self):
        """The tree view reads lft/rgt. This is what proves it will render."""
        self._bp("epic")
        self._bp("story", parent_key="epic")
        migrate_task_hierarchy()

        parent = frappe.db.get_value(
            "Task", self.native["epic"].name, ["lft", "rgt"], as_dict=True
        )
        child = frappe.db.get_value(
            "Task", self.native["story"].name, ["lft", "rgt"], as_dict=True
        )
        self.assertLess(parent.lft, child.lft, "child does not sit inside its parent")
        self.assertGreater(parent.rgt, child.rgt, "child does not sit inside its parent")

    def test_running_twice_changes_nothing(self):
        self._bp("epic")
        self._bp("story", parent_key="epic")
        migrate_task_hierarchy()
        before = frappe.db.get_value(
            "Task", self.native["story"].name, ["parent_task", "lft", "rgt"], as_dict=True
        )

        again = migrate_task_hierarchy()
        after = frappe.db.get_value(
            "Task", self.native["story"].name, ["parent_task", "lft", "rgt"], as_dict=True
        )
        self.assertEqual(again["linked"], 0, "re-linked an already-linked task")
        self.assertEqual(before, after)

    def test_a_task_with_no_parent_is_left_alone(self):
        self._bp("loner")
        stats = migrate_task_hierarchy()
        self.assertEqual(stats["linked"], 0, stats)
        self.assertIsNone(
            frappe.db.get_value("Task", self.native["loner"].name, "parent_task") or None
        )

    def test_an_unmigrated_parent_is_skipped_not_guessed(self):
        """A BP parent with no native counterpart must not be invented."""
        self._bp("story")
        orphan = frappe.get_doc(
            {
                "doctype": "BP Task",
                "task_key": f"HIER-{frappe.generate_hash('', 6).upper()}",
                "title": "unmigrated parent",
                "project": self.bp_project.name,
            }
        )
        orphan.flags.ignore_mandatory = True
        orphan.insert(ignore_permissions=True)
        frappe.db.set_value("BP Task", self.bp["story"].name, "parent_task", orphan.name)

        stats = migrate_task_hierarchy()
        self.assertEqual(stats["linked"], 0, stats)
        self.assertGreaterEqual(stats["skipped"], 1, stats)
        self.assertFalse(
            frappe.db.get_value("Task", self.native["story"].name, "parent_task")
        )

    def test_a_cycle_is_refused(self):
        """BP Task is a plain Link and never prevented this; NestedSet cannot
        absorb it, so the pass must drop the pair rather than corrupt the tree."""
        self._bp("epic")
        self._bp("story", parent_key="epic")
        frappe.db.set_value(
            "BP Task", self.bp["epic"].name, "parent_task", self.bp["story"].name
        )

        stats = migrate_task_hierarchy()
        self.assertGreaterEqual(stats["cyclic"], 1, stats)
        self.assertFalse(
            frappe.db.get_value("Task", self.native["epic"].name, "parent_task"),
            "a cycle was written into the nested set",
        )
