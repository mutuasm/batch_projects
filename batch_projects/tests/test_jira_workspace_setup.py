"""setup_jira_workspace must actually produce the board and issue types.

This test exists because of a specific failure. `setup_jira_workspace()` never
raises, by design — it runs from `after_install` and `after_migrate`, where an
exception would abort an install or a whole `bench migrate`. But that same
defensiveness meant a total failure was invisible: `Task Type` autonames by
`Prompt`, the code did not set `name`, frappe raised "Please set the document
name", the exception was logged and swallowed, and CI stayed green while
neither the issue types nor the board had been created. It was only caught by
installing on a real site and looking.

So the contract is asserted from the outside: call the setup and check the
records exist. A "never raises" function needs a test that checks it did the
work, not merely that it returned.

Run with:
    bench run-tests --module batch_projects.tests.test_jira_workspace_setup
"""

import frappe
from frappe.tests import IntegrationTestCase

from batch_projects.setup.jira_workspace import (
    BOARD_NAME,
    _COLUMNS,
    _ISSUE_TYPES,
    setup_jira_workspace,
)


class TestJiraWorkspaceSetup(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_jira_workspace()

    def test_every_issue_type_exists(self):
        missing = [t for t in _ISSUE_TYPES if not frappe.db.exists("Task Type", t)]
        self.assertEqual(missing, [], f"issue types not created: {missing}")

    def test_board_exists_on_task_grouped_by_status(self):
        self.assertTrue(
            frappe.db.exists("Kanban Board", BOARD_NAME),
            f"{BOARD_NAME} was not created",
        )
        board = frappe.get_doc("Kanban Board", BOARD_NAME)
        self.assertEqual(board.reference_doctype, "Task")
        self.assertEqual(board.field_name, "status")

    def test_every_task_status_has_a_column(self):
        """A Kanban Board only renders cards matching a defined column, so a
        missing column silently hides those tasks — `Overdue` especially."""
        board = frappe.get_doc("Kanban Board", BOARD_NAME)
        columns = {row.column_name for row in board.columns}
        native_statuses = {
            s for s in (frappe.get_meta("Task").get_field("status").options or "").split("\n") if s
        }
        self.assertEqual(
            native_statuses - columns,
            set(),
            "Task statuses with no board column would be invisible on the board",
        )

    def test_column_keys_are_field_values_not_display_labels(self):
        """column_name must equal the status value or cards never match it."""
        board = frappe.get_doc("Kanban Board", BOARD_NAME)
        columns = {row.column_name for row in board.columns}
        self.assertEqual(columns, {status for status, _, _, _ in _COLUMNS})

    def test_setup_is_idempotent(self):
        """It runs on every migrate, so a second call must not duplicate."""
        before = frappe.db.count("Kanban Board", {"name": BOARD_NAME})
        setup_jira_workspace()
        self.assertEqual(frappe.db.count("Kanban Board", {"name": BOARD_NAME}), before)
        self.assertEqual(
            [t for t in _ISSUE_TYPES if not frappe.db.exists("Task Type", t)], []
        )
