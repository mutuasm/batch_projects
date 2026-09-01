"""Activation must be opt-in, and completely inert until opted into.

Everything built for the native migration is registered unconditionally — the
patch runs on every `bench migrate`, and the permission hooks are registered for
Project and Task on every site. That is deliberate: activation should be a
site_config setting, not a hooks edit.

It also means the OFF path is load-bearing. Without these guards, merely
installing this app would start creating Project and Task rows nobody asked for
and filtering every Project query for HRMS, CRM and stock ERPNext users. So the
inertness is tested directly rather than assumed.

Run with:
    bench run-tests --module batch_projects.tests.test_native_activation
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from batch_projects import permissions


class _Conf(dict):
    pass


def _flag(value):
    conf = _Conf(frappe.conf)
    if value is None:
        conf.pop("bp_use_native_doctypes", None)
    else:
        conf["bp_use_native_doctypes"] = value
    return patch.object(frappe, "conf", conf)


class TestPatchIsOptIn(UnitTestCase):
    def test_patch_does_nothing_while_the_switch_is_off(self):
        """It must not touch the migration functions at all, not merely skip work."""
        from batch_projects.patches import activate_native_model as p

        with _flag(None), patch(
            "batch_projects.setup.native_migration.run_native_migration"
        ) as run:
            p.execute()
        run.assert_not_called()

    def test_patch_runs_the_three_steps_in_order_when_on(self):
        """Satellites and children both depend on the mapping anchors the
        migration writes, so the order is not interchangeable."""
        from batch_projects.patches import activate_native_model as p

        calls = []
        with _flag(True), \
             patch("batch_projects.setup.native_migration.run_native_migration",
                   side_effect=lambda: calls.append("migrate") or {}), \
             patch("batch_projects.setup.native_migration.retarget_satellite_links",
                   side_effect=lambda: calls.append("satellites") or {}), \
             patch("batch_projects.setup.native_migration.retarget_child_tables",
                   side_effect=lambda: calls.append("children") or {}):
            p.execute()
        self.assertEqual(calls, ["migrate", "satellites", "children"])


class TestPermissionHooksAreInertWhenOff(UnitTestCase):
    def test_no_restriction_is_applied(self):
        with _flag(None):
            self.assertEqual(permissions.native_project_query_conditions("u@e.com"), "")
            self.assertEqual(permissions.native_task_query_conditions("u@e.com"), "")

    def test_a_restriction_appears_once_on(self):
        with _flag(True), patch.object(permissions, "get_accessible_projects",
                                       return_value=set()):
            self.assertNotEqual(permissions.native_project_query_conditions("u@e.com"), "")
            self.assertNotEqual(permissions.native_task_query_conditions("u@e.com"), "")


class TestHooksAreRegistered(IntegrationTestCase):
    def test_native_doctypes_have_permission_hooks(self):
        hooks = frappe.get_hooks("permission_query_conditions") or {}
        for doctype in ("Project", "Task"):
            self.assertIn(doctype, hooks, f"no permission hook registered for {doctype}")

    def test_activation_patch_is_registered_last(self):
        """It depends on every doctype and custom field declared above it."""
        import pathlib

        text = (pathlib.Path(frappe.get_app_path("batch_projects")) / "patches.txt").read_text()
        entries = [l.strip() for l in text.splitlines()
                   if l.strip() and not l.strip().startswith(("#", "["))]
        self.assertEqual(entries[-1], "batch_projects.patches.activate_native_model")
