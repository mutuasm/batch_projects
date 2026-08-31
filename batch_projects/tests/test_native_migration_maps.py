"""The value translations used when copying BP rows into native Project/Task.

These tables are the lossy part of the native-doctype migration, and a wrong
entry is quiet: the row still saves, it just carries the wrong status or
priority forever. So each table is asserted for totality and for legality
against the real native options.

Run with:
    bench run-tests --module batch_projects.tests.test_native_migration_maps
"""

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from batch_projects.setup.native_migration import (
    _CATEGORY_TO_TASK_STATUS,
    _PROJECT_STATUS,
    _TASK_PRIORITY,
    _scalar_custom_fields,
)

# The categories api/board.py validates against; anything else is coerced to
# "unstarted" there, so the migration table must cover exactly these.
_BP_CATEGORIES = {"unstarted", "started", "completed", "cancelled"}

# BP Project.status options, from bp_project.json.
_BP_PROJECT_STATUSES = {"Active", "Archived", "On Hold"}

# BP Task.priority options, from bp_task.json.
_BP_TASK_PRIORITIES = {"Highest", "High", "Medium", "Low", "Lowest"}


class TestMigrationMapTotality(UnitTestCase):
    """Every BP value must have a translation — a gap means a silent default."""

    def test_every_workflow_category_is_mapped(self):
        self.assertEqual(set(_CATEGORY_TO_TASK_STATUS), _BP_CATEGORIES)

    def test_every_bp_project_status_is_mapped(self):
        self.assertEqual(set(_PROJECT_STATUS), _BP_PROJECT_STATUSES)

    def test_every_bp_task_priority_is_mapped(self):
        self.assertEqual(set(_TASK_PRIORITY), _BP_TASK_PRIORITIES)

    def test_on_hold_uses_native_is_active_rather_than_inventing_a_status(self):
        """Native has no "on hold" status but does carry an is_active axis."""
        self.assertEqual(_PROJECT_STATUS["On Hold"], ("Open", "No"))
        self.assertEqual(_PROJECT_STATUS["Active"], ("Open", "Yes"))

    def test_archived_is_not_conflated_with_cancelled(self):
        """Archived work happened; cancelled work did not."""
        status, _ = _PROJECT_STATUS["Archived"]
        self.assertEqual(status, "Completed")

    def test_completed_and_cancelled_categories_stay_distinct(self):
        self.assertNotEqual(
            _CATEGORY_TO_TASK_STATUS["completed"], _CATEGORY_TO_TASK_STATUS["cancelled"]
        )

    def test_child_tables_are_not_copied_as_scalars(self):
        """Satellite rows are retargeted as a set, not half-copied per parent."""
        for doctype in ("Project", "Task"):
            for fieldname in _scalar_custom_fields(doctype):
                self.assertNotIn(
                    fieldname,
                    {"custom_members", "custom_assignees", "custom_links",
                     "custom_references", "custom_custom_field_links"},
                    f"{doctype}.{fieldname} is a child table and must not be copied here",
                )


class TestMigrationMapLegality(IntegrationTestCase):
    """Every translated value must be a real option on the native field.

    Without this, a mapping typo produces a row whose status is not in the
    Select — which Frappe will happily store and every native view will then
    render oddly.
    """

    def _options(self, doctype, fieldname):
        field = frappe.get_meta(doctype).get_field(fieldname)
        return set((field.options or "").split("\n"))

    def test_task_statuses_are_valid(self):
        valid = self._options("Task", "status")
        self.assertLessEqual(set(_CATEGORY_TO_TASK_STATUS.values()), valid)

    def test_project_statuses_are_valid(self):
        valid = self._options("Project", "status")
        self.assertLessEqual({s for s, _ in _PROJECT_STATUS.values()}, valid)

    def test_project_is_active_values_are_valid(self):
        valid = self._options("Project", "is_active")
        self.assertLessEqual({a for _, a in _PROJECT_STATUS.values()}, valid)

    def test_task_priorities_are_valid(self):
        valid = self._options("Task", "priority")
        self.assertLessEqual(set(_TASK_PRIORITY.values()), valid)
