"""The switch that lets the native migration be re-keyed incrementally.

434 call sites name "BP Task" / "BP Project" as literals. Flipping any subset of
them mid-migration breaks the app — the data has not moved, satellite Links
still hold BP row names, and Project has no alias shim. Routing them through
TASK()/PROJECT() makes each conversion behaviour-preserving while the switch is
off, which is the only way this lands in reviewable pieces.

So the property that actually matters is: **off must mean nothing changed**.

Run with:
    bench run-tests --module batch_projects.tests.test_doctype_switch
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from batch_projects import doctypes


class _Conf(dict):
    """site_config stand-in — frappe.conf is a dict-like with .get()."""


def _with_flag(value):
    conf = _Conf(frappe.conf)
    if value is None:
        conf.pop("bp_use_native_doctypes", None)
    else:
        conf["bp_use_native_doctypes"] = value
    return patch.object(frappe, "conf", conf)


class TestSwitchDefaultsOff(UnitTestCase):
    def test_unset_means_bp(self):
        """A site that has not opted in must be completely unaffected."""
        with _with_flag(None):
            self.assertFalse(doctypes.use_native())
            self.assertEqual(doctypes.PROJECT(), "BP Project")
            self.assertEqual(doctypes.TASK(), "BP Task")

    def test_off_passes_field_names_through_untouched(self):
        with _with_flag(None):
            self.assertEqual(doctypes.task_field("title"), "title")
            self.assertEqual(doctypes.project_field("client"), "client")

    def test_off_passes_filters_and_fields_through_unchanged(self):
        with _with_flag(None):
            filters = {"title": "x", "is_deleted": 0}
            self.assertIs(doctypes.task_filters(filters), filters)
            fields = ["title", "status"]
            self.assertIs(doctypes.task_fields(fields), fields)


class TestSwitchOn(UnitTestCase):
    def test_on_selects_the_native_doctypes(self):
        with _with_flag(True):
            self.assertTrue(doctypes.use_native())
            self.assertEqual(doctypes.PROJECT(), "Project")
            self.assertEqual(doctypes.TASK(), "Task")

    def test_on_translates_field_names(self):
        with _with_flag(True):
            self.assertEqual(doctypes.task_field("title"), "subject")
            self.assertEqual(doctypes.task_field("is_deleted"), "custom_is_deleted")
            self.assertEqual(doctypes.project_field("client"), "customer")

    def test_on_translates_filters(self):
        with _with_flag(True):
            self.assertEqual(
                doctypes.task_filters({"title": "x", "is_deleted": 0}),
                {"subject": "x", "custom_is_deleted": 0},
            )

    def test_on_translates_field_lists_and_drops_dead_concepts(self):
        with _with_flag(True):
            self.assertEqual(
                doctypes.project_fields(["key", "erpnext_project", "client"]),
                ["custom_key", "customer"],
            )


class TestSwitchIsReadDynamically(UnitTestCase):
    def test_value_is_not_frozen_at_import(self):
        """site_config is per-site; a constant resolved at import would freeze
        whatever the first-loaded site said, which is wrong on a multi-site
        bench."""
        with _with_flag(None):
            self.assertEqual(doctypes.TASK(), "BP Task")
        with _with_flag(True):
            self.assertEqual(doctypes.TASK(), "Task")
        with _with_flag(None):
            self.assertEqual(doctypes.TASK(), "BP Task")
