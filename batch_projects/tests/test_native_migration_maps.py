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


class _FakeDoc:
    """Minimal Document stand-in: .get()/.set() only.

    frappe._dict is NOT usable here — it resolves unknown attributes to None
    via __getattr__, so `doc.set(...)` silently becomes None and the call fails
    with "NoneType object is not callable" rather than testing anything.
    """

    def __init__(self, **values):
        self._values = dict(values)

    def get(self, field, default=None):
        return self._values.get(field, default)

    def set(self, field, value):
        self._values[field] = value


class TestBackfillEmptiness(UnitTestCase):
    """Numeric zero must count as "not filled in yet" on the native side.

    Regression, found only by migrating on a real site: Frappe creates
    Int/Float/Currency/Check columns NOT NULL DEFAULT 0, so a fresh native row
    reads 0.0 for every number. Treating that as "already has a value" made the
    backfill skip every numeric field in complete silence — BP budget_amount
    5000 and hourly_rate 120 both landed as 0.0 with no error anywhere.

    This is the failure mode the migration is most exposed to: nothing raises,
    nothing logs, the numbers are just quietly missing.
    """

    def test_native_numeric_zero_counts_as_unset(self):
        from batch_projects.setup.native_migration import _native_unset

        for value in (0, 0.0, None, ""):
            self.assertTrue(_native_unset(value), f"{value!r} should count as unset")

    def test_real_native_values_do_not_count_as_unset(self):
        from batch_projects.setup.native_migration import _native_unset

        for value in (1, 0.01, -1, "x", "0"):
            self.assertFalse(_native_unset(value), f"{value!r} should count as set")

    def test_only_none_and_blank_are_nothing_to_copy(self):
        """A BP zero is a real value; absence is None or "" only."""
        from batch_projects.setup.native_migration import _nothing_to_copy

        self.assertTrue(_nothing_to_copy(None))
        self.assertTrue(_nothing_to_copy(""))
        self.assertFalse(_nothing_to_copy(0))
        self.assertFalse(_nothing_to_copy(0.0))

    def test_fill_writes_over_a_numeric_zero(self):
        from batch_projects.setup.native_migration import _fill

        doc = _FakeDoc(estimated_costing=0.0)
        self.assertTrue(_fill(doc, "estimated_costing", 5000))
        self.assertEqual(doc.get("estimated_costing"), 5000)

    def test_fill_does_not_clobber_a_real_native_value(self):
        from batch_projects.setup.native_migration import _fill

        doc = _FakeDoc(estimated_costing=999.0)
        self.assertFalse(_fill(doc, "estimated_costing", 5000))
        self.assertEqual(doc.get("estimated_costing"), 999.0)

    def test_authoritative_fill_overwrites_regardless(self):
        """Translated enums must win — a stale status defeats the translation."""
        from batch_projects.setup.native_migration import _fill

        doc = _FakeDoc(status="Open")
        self.assertTrue(_fill(doc, "status", "Completed", authoritative=True))
        self.assertEqual(doc.get("status"), "Completed")

    def test_fill_is_a_noop_when_the_value_already_matches(self):
        from batch_projects.setup.native_migration import _fill

        doc = _FakeDoc(status="Completed")
        self.assertFalse(_fill(doc, "status", "Completed", authoritative=True))
