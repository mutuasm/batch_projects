"""Every link in the app's Workspace Sidebar must point somewhere real.

A sidebar entry naming a doctype, report or workspace that does not exist
renders as a dead link — the desk does not complain, it just goes nowhere. This
file previously pointed all 16 of its items at `/workspace/*` SPA routes, which
this stage retargets to desk destinations; without a check, a typo or a renamed
report would silently reintroduce the same dead-end.

Run with:
    bench run-tests --module batch_projects.tests.test_sidebar_targets
"""

import json
import pathlib

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

_SIDEBAR = (
    pathlib.Path(frappe.get_app_path("batch_projects"))
    / "workspace_sidebar"
    / "batchprojects.json"
)

# link_type -> the doctype whose records it names.
_TARGET_DOCTYPE = {
    "DocType": "DocType",
    "Report": "Report",
    "Workspace": "Workspace",
    "Dashboard": "Dashboard",
    "Page": "Page",
}


def _items():
    return json.loads(_SIDEBAR.read_text())["items"]


def _links():
    return [i for i in _items() if i.get("type") == "Link"]


class TestSidebarShape(UnitTestCase):
    """Checks that need no database."""

    def test_no_link_points_at_the_retired_spa(self):
        """The SPA is being removed; a /workspace route is a future 404."""
        offenders = [
            i["label"] for i in _items() if "/workspace" in json.dumps(i)
        ]
        self.assertEqual(offenders, [], f"still pointing at SPA routes: {offenders}")

    def test_url_links_stay_inside_the_desk(self):
        offenders = [
            f"{i['label']} -> {i.get('url')}"
            for i in _links()
            if i.get("link_type") == "URL" and not str(i.get("url", "")).startswith("/desk/")
        ]
        self.assertEqual(offenders, [], f"URL links outside the desk: {offenders}")

    def test_every_link_declares_a_destination(self):
        offenders = [
            i["label"]
            for i in _links()
            if not (i.get("url") if i.get("link_type") == "URL" else i.get("link_to"))
        ]
        self.assertEqual(offenders, [], f"links with no destination: {offenders}")

    def test_title_does_not_collide_with_erpnext(self):
        """Workspace Sidebar autonames field:title and erpnext owns "Projects"."""
        doc = json.loads(_SIDEBAR.read_text())
        self.assertNotEqual(doc["title"], "Projects")
        self.assertEqual(doc["name"], doc["title"])  # autoname field:title


class TestSidebarTargetsResolve(IntegrationTestCase):
    """Every named record must actually exist on the site."""

    def test_no_dead_links(self):
        dead = []
        for item in _links():
            link_type = item.get("link_type")
            if link_type == "URL":
                continue
            target_doctype = _TARGET_DOCTYPE.get(link_type)
            if not target_doctype:
                dead.append(f"unknown link_type {link_type!r} ({item['label']})")
                continue
            if not frappe.db.exists(target_doctype, item["link_to"]):
                dead.append(f"{link_type}:{item['link_to']} ({item['label']})")
        self.assertEqual(dead, [], f"dead sidebar links: {dead}")

    def test_the_task_board_url_names_an_existing_kanban_board(self):
        """The board link is a URL, so nothing else would catch a rename."""
        board_links = [
            i for i in _links()
            if i.get("link_type") == "URL" and "/view/kanban/" in str(i.get("url"))
        ]
        self.assertTrue(board_links, "no kanban board link in the sidebar")
        for item in board_links:
            board = item["url"].rsplit("/view/kanban/", 1)[1]
            self.assertTrue(
                frappe.db.exists("Kanban Board", board),
                f"sidebar points at Kanban Board {board!r}, which does not exist",
            )
