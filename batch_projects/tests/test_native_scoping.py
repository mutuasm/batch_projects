"""Access semantics for scoping native Project/Task by BP membership.

These are the riskiest lines in the native-doctype migration: native Project
and Task are shared with the rest of the site, so a mistake here changes who
can see existing ERPNext data. `Task` is readable today by `Projects User` and
`HR Manager` (HRMS reads it for timesheet/leave flows); `Project` by
`Desk User`, `Projects Manager` and `Projects User`.

The rule under test has two halves, and both matter:

  per-user fallback     a user with no BP memberships is not a BP user, so
                        they keep stock ERPNext visibility rather than seeing
                        nothing.
  per-project fallback  a project with no `custom_visibility` was not created
                        through this app and stays visible regardless. Without
                        this, adding a Projects Manager to one BP project would
                        hide every other project on the site from them.

Pure SQL-shape assertions: get_accessible_projects is stubbed, so no site data
is touched and the clauses are checked directly.

Run with:
    bench run-tests --module batch_projects.tests.test_native_scoping
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from batch_projects import permissions

# Identifiers are backticked in the generated SQL.
_BP_MANAGED = "`custom_visibility` is not null"


class _NativeOn(UnitTestCase):
    """Runs with `bp_use_native_doctypes` on.

    The permission functions return "" unconditionally while the switch is off
    — registering the hooks must not filter Project/Task for HRMS, CRM and
    stock ERPNext users on a site that never opted in. That inertness is
    covered by test_native_activation; everything here is about the clauses
    built once a site HAS opted in, so the flag is on for the whole module.
    Without this the assertions below pass vacuously against an empty string.
    """

    def setUp(self):
        super().setUp()
        conf = dict(frappe.conf)
        conf["bp_use_native_doctypes"] = True
        patcher = patch.object(frappe, "conf", conf)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestNativeProjectScoping(_NativeOn):
    def _conditions(self, accessible):
        with patch.object(permissions, "get_accessible_projects", return_value=accessible):
            return permissions.native_project_query_conditions(user="someone@example.com")

    def test_admin_is_unrestricted(self):
        """None means admin — no clause at all."""
        self.assertEqual(self._conditions(None), "")

    def test_non_bp_user_still_sees_non_bp_projects(self):
        """The whole point of the fallback: no memberships must not mean no rows.

        An HR Manager or Projects User who has never touched this app keeps
        stock ERPNext visibility for projects the app doesn't manage.
        """
        clause = self._conditions(set())
        self.assertIn(_BP_MANAGED, clause)
        self.assertTrue(clause.startswith("not "), clause)
        self.assertNotIn("1=0", clause)

    def test_member_sees_own_projects_plus_non_bp_ones(self):
        """Joining one BP project must not hide the rest of the site."""
        clause = self._conditions({"PROJ-A"})
        self.assertIn("PROJ-A", clause)
        self.assertIn(_BP_MANAGED, clause)
        self.assertIn(" or ", clause)

    def test_never_emits_a_deny_all(self):
        """`1=0` on a shared doctype would blank the Projects module."""
        for accessible in (set(), {"PROJ-A"}, {"PROJ-A", "PROJ-B"}):
            self.assertNotIn("1=0", self._conditions(accessible))


class TestNativeTaskScoping(_NativeOn):
    def _conditions(self, accessible):
        with patch.object(permissions, "get_accessible_projects", return_value=accessible):
            return permissions.native_task_query_conditions(user="someone@example.com")

    def test_trash_is_always_excluded(self):
        for accessible in (None, set(), {"PROJ-A"}):
            self.assertIn("`tabTask`.`custom_is_deleted` = 0", self._conditions(accessible))

    def test_admin_gets_only_the_trash_filter(self):
        self.assertEqual(self._conditions(None), "`tabTask`.`custom_is_deleted` = 0")

    def test_non_bp_user_still_sees_tasks_outside_bp_projects(self):
        clause = self._conditions(set())
        self.assertIn("`tabTask`.`project` is null", clause)
        self.assertIn("not in", clause)
        self.assertNotIn("1=0", clause)

    def test_member_keeps_assignee_carve_out(self):
        """An explicit assignee sees their own task with no project standing."""
        clause = self._conditions({"PROJ-A"})
        self.assertIn("tabBP Task Assignee", clause)
        self.assertIn("PROJ-A", clause)

    def test_never_emits_a_deny_all(self):
        for accessible in (set(), {"PROJ-A"}):
            self.assertNotIn("1=0", self._conditions(accessible))

    def test_user_is_escaped_into_the_assignee_subquery(self):
        """The user value reaches SQL, so it must go through db.escape."""
        with patch.object(permissions, "get_accessible_projects", return_value={"P"}):
            clause = permissions.native_task_query_conditions(user="o'brien@example.com")
        self.assertNotIn("o'brien@example.com", clause.replace("\\'", ""))
