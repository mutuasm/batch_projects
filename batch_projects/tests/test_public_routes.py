"""The three public, unauthenticated pages must actually render.

/invite, /share and /intake are URLs that live outside this app: in an email, a
client's bookmark, a published form. Whoever holds one cannot recover from a
404, so a broken route here is invisible to us and terminal for them. The SPA
that used to serve all three was removed, which is precisely how /share and
/intake came to point at nothing while their APIs kept working.

These tests render through frappe's real website stack — routing, get_context
and the Jinja template — rather than calling get_context directly, because two
of the three ways this breaks (an unregistered route, a template error) are
invisible to a get_context-only test.

Run with:
    bench run-tests --module batch_projects.tests.test_public_routes
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_html_for_route

from batch_projects import hooks


class TestPublicRoutesRegistered(IntegrationTestCase):
    def test_every_public_page_has_a_route(self):
        routes = {r["from_route"]: r["to_route"] for r in hooks.website_route_rules}
        for prefix, page in (
            ("/invite/<path:app_path>", "invite"),
            ("/share/<path:app_path>", "share"),
            ("/intake/<path:app_path>", "intake"),
        ):
            self.assertEqual(routes.get(prefix), page, f"{prefix} is not routed")

    def test_share_url_helper_matches_the_registered_route(self):
        """api.sharing mints these links; a mismatch here is a 404 by design."""
        from batch_projects.api.sharing import _share_url

        self.assertIn("/share/tok123", _share_url("tok123"))


class _PublicPage(IntegrationTestCase):
    """Fixtures for the share and intake pages, plus a Guest-rendered fetch."""

    def setUp(self):
        super().setUp()
        # get_shared commits — it updates access_count/last_accessed and calls
        # frappe.db.commit() so the accounting survives a failed read. That
        # also commits this test's fixtures, defeating IntegrationTestCase's
        # rollback and leaving projects, tasks and share links behind on
        # whatever site the suite ran against. Stubbed so the rollback holds;
        # the accounting itself is not what these tests are about.
        commit = patch.object(frappe.db, "commit", lambda *a, **k: None)
        commit.start()
        self.addCleanup(commit.stop)

        tag = frappe.generate_hash("", 8)
        self.project = frappe.get_doc(
            {"doctype": "BP Project", "project_name": f"pub {tag}", "key": tag[:6].upper()}
        )
        self.project.flags.ignore_mandatory = True
        self.project.insert(ignore_permissions=True)

    def _task(self, title):
        doc = frappe.get_doc(
            {
                "doctype": "BP Task",
                "task_key": f"PUB-{frappe.generate_hash('', 6).upper()}",
                "title": title,
                "project": self.project.name,
            }
        )
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        return doc

    def _link(self, scope, access_level="view", task=None):
        token = frappe.generate_hash("", 24)
        doc = frappe.get_doc(
            {
                "doctype": "BP Share Link",
                "project": self.project.name,
                "scope": scope,
                "task": task,
                "access_level": access_level,
                "token": token,
            }
        )
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        return token

    def _render(self, route):
        """Render as Guest — these pages exist for people with no account."""
        frappe.set_user("Guest")
        try:
            return get_html_for_route(route)
        finally:
            frappe.set_user("Administrator")


class TestSharePage(_PublicPage):
    def test_a_shared_task_renders_its_title(self):
        task = self._task("Ship the thing")
        html = self._render(f"/share/{self._link('task', task=task.name)}")
        self.assertIn("Ship the thing", html)
        self.assertIn("Read-only", html)

    def test_a_shared_board_renders_its_columns(self):
        self._task("On the board")
        html = self._render(f"/share/{self._link('board')}")
        self.assertIn("On the board", html)

    def test_the_comment_box_appears_only_when_the_link_permits_it(self):
        """add_guest_comment refuses anything but access_level 'comment', so
        offering the box anywhere else invites a rejection the visitor cannot
        act on."""
        task = self._task("Commentable")

        view_only = self._render(f"/share/{self._link('task', 'view', task.name)}")
        self.assertNotIn("bp-comment-send", view_only)

        commentable = self._render(
            f"/share/{self._link('task', 'comment', task.name)}"
        )
        self.assertIn("bp-comment-send", commentable)

    def test_member_authored_markup_is_escaped_not_rendered(self):
        """Task text is written by members and shown to anonymous visitors —
        the exact direction stored XSS travels.

        `<b>` rather than `<script>` on purpose. Frappe's own XSS filter strips
        script tags out of Data fields at write time, so a script payload never
        reaches the template and would prove nothing about it — an earlier
        version of this test asserted on escaped script tags and failed because
        the title had been emptied before it ever got here. `<b>bold</b>` is
        stored verbatim, so it isolates the one layer this app owns: Jinja
        autoescaping in the template."""
        task = self._task("<b>bold</b>")
        html = self._render(f"/share/{self._link('task', task=task.name)}")
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", html)
        self.assertNotIn("<b>bold</b>", html)

    def test_script_tags_never_reach_the_page(self):
        """Belt and braces over the layer above: whatever the storage filter
        does or stops doing, the rendered page must carry no injected script."""
        task = self._task("<script>alert('xss')</script>")
        html = self._render(f"/share/{self._link('task', task=task.name)}")
        self.assertNotIn("alert('xss')", html)

    def test_an_unknown_token_explains_itself(self):
        html = self._render("/share/definitely-not-a-token")
        self.assertIn("Ask whoever shared this", html)

    def test_a_revoked_link_is_refused(self):
        task = self._task("Revoked")
        token = self._link("task", task=task.name)
        frappe.db.set_value("BP Share Link", {"token": token}, "revoked", 1)
        html = self._render(f"/share/{token}")
        self.assertNotIn("Revoked", html)
        self.assertIn("Ask whoever shared this", html)


class TestIntakePage(_PublicPage):
    def _form(self, active=1, fields=None):
        doc = frappe.get_doc(
            {
                "doctype": "BP Intake Form",
                "form_title": "Request something",
                "project": self.project.name,
                "is_active": active,
                "fields_json": json.dumps(
                    fields
                    if fields is not None
                    else [
                        {"label": "What do you need", "type": "text", "required": True},
                        {"label": "Details", "type": "textarea"},
                    ]
                ),
            }
        )
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        return doc

    def test_an_active_form_renders_its_fields(self):
        form = self._form()
        html = self._render(f"/intake/{form.name}")
        self.assertIn("Request something", html)
        self.assertIn("What do you need", html)
        self.assertIn("Details", html)
        self.assertIn("<textarea", html)

    def test_inputs_are_keyed_by_label(self):
        """submit_intake_form reads `values` by label, not fieldname. Keying
        the inputs any other way drops every answer and still reports success."""
        form = self._form(fields=[{"label": "Your email", "type": "email"}])
        html = self._render(f"/intake/{form.name}")
        self.assertIn('data-label="Your email"', html)
        self.assertIn('type="email"', html)

    def test_an_unknown_field_type_still_renders_an_input(self):
        """The type vocabulary is not constrained anywhere server-side."""
        form = self._form(fields=[{"label": "Odd one", "type": "quantum"}])
        html = self._render(f"/intake/{form.name}")
        self.assertIn('data-label="Odd one"', html)
        self.assertIn('type="text"', html)

    def test_an_inactive_form_is_refused(self):
        form = self._form(active=0)
        html = self._render(f"/intake/{form.name}")
        self.assertNotIn('data-label="What do you need"', html)
