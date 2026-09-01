"""Deep links in notification emails must point at real desk routes.

These URLs leave the application — they arrive in somebody's inbox. A wrong one
is not a broken page a user can navigate around; it is a dead link in a message
you cannot recall. Every one of them used to point at a `/workspace/...` SPA
route, and the SPA is gone.

Run with:
    bench run-tests --module batch_projects.tests.test_desk_urls
"""

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from batch_projects import desk_urls


class TestDeskUrlShape(UnitTestCase):
    def test_slug_matches_frappe_route_style(self):
        self.assertEqual(desk_urls.slug("BP Task"), "bp-task")
        self.assertEqual(desk_urls.slug("BP Notification Preference"), "bp-notification-preference")

    def test_no_builder_emits_a_workspace_route(self):
        """The SPA is gone; /workspace is a 404 now."""
        built = [
            desk_urls.project_url(None),
            desk_urls.project_url("P"),
            desk_urls.project_tasks_url("P"),
            desk_urls.task_url("P", "P-1"),
            desk_urls.task_url("P", None),
            desk_urls.my_tasks_url(),
            desk_urls.report_url("RPT-0001"),
            desk_urls.saved_view_url("V-1"),
            desk_urls.notification_settings_url(),
            desk_urls.workspace_settings_url(),
        ]
        offenders = [u for u in built if "/workspace" in u]
        self.assertEqual(offenders, [], f"still emitting SPA routes: {offenders}")

    def test_every_builder_targets_the_desk(self):
        for url in (
            desk_urls.project_url("P"),
            desk_urls.task_url("P", "P-1"),
            desk_urls.report_url("RPT-0001"),
            desk_urls.notification_settings_url(),
        ):
            self.assertIn("/desk/", url, f"not a desk route: {url}")

    def test_task_url_addresses_the_record_directly(self):
        """BP Task autonames field:task_key, so the key IS the record name."""
        self.assertTrue(desk_urls.task_url("P", "MIGA-1").endswith("/bp-task/MIGA-1"))

    def test_task_url_falls_back_to_the_project_list_without_a_key(self):
        url = desk_urls.task_url("Some Project", None)
        self.assertIn("/bp-task", url)
        self.assertIn("project=", url)

    def test_names_with_spaces_are_url_encoded(self):
        """Project names are free text — an unencoded space breaks the link."""
        url = desk_urls.project_url("Migration Alpha")
        self.assertNotIn(" ", url)


class TestDeskUrlTargetsResolve(IntegrationTestCase):
    def test_linked_doctypes_exist(self):
        """A slug for a doctype that does not exist is a dead link."""
        missing = [
            dt
            for dt in ("BP Project", "BP Task", "BP Report", "BP View",
                       "BP Notification Preference", "BP Workspace Settings")
            if not frappe.db.exists("DocType", dt)
        ]
        self.assertEqual(missing, [], f"deep links name missing doctypes: {missing}")


class TestInviteRouteSurvives(UnitTestCase):
    """The one public route that outlived the SPA must stay wired.

    /invite/<token> is the only `/workspace/...` route that was replaced rather
    than dropped. If the rule or the page goes missing, invitation emails point
    at a 404 and there is no way to join a project — a silent break, since
    nothing else in the app exercises that path.
    """

    def test_route_rule_is_declared(self):
        rules = frappe.get_hooks("website_route_rules", app_name="batch_projects") or []
        routes = {r.get("from_route") for r in rules}
        self.assertIn("/invite/<path:app_path>", routes)

    def test_no_spa_routes_are_declared(self):
        rules = frappe.get_hooks("website_route_rules", app_name="batch_projects") or []
        offenders = [
            r["from_route"]
            for r in rules
            if any(dead in r.get("from_route", "") for dead in ("/workspace", "/share", "/intake"))
        ]
        self.assertEqual(offenders, [], f"routes for the removed SPA: {offenders}")

    def test_the_invite_page_exists(self):
        import pathlib

        www = pathlib.Path(frappe.get_app_path("batch_projects")) / "www"
        for filename in ("invite.py", "invite.html"):
            self.assertTrue((www / filename).exists(), f"missing www/{filename}")

    def test_invitation_email_links_at_the_surviving_route(self):
        from batch_projects.api.invitations import _accept_url

        url = _accept_url("tok123")
        self.assertIn("/invite/tok123", url)
        self.assertNotIn("/workspace", url)
