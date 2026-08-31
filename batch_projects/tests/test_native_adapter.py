"""BP field name -> native Project/Task field translation.

This is the layer that lets the app switch to native doctypes without
hand-editing ~5,400 field references, so a wrong answer here is a wrong read
everywhere. The cases below are the ones that actually bite:

  * `description` is a MAPPED field on Project (-> notes) but a VERBATIM one on
    Task, so resolution has to be per-doctype and order-sensitive.
  * `status` is spelled identically on both models but the vocabularies differ,
    so a filter must translate the value as well as the key.
  * an unknown field must RAISE. Passing it through would read a nonexistent
    column and return None — the exact silent failure this migration is most
    exposed to.

Run with:
    bench run-tests --module batch_projects.tests.test_native_adapter
"""

from frappe.tests import UnitTestCase

from batch_projects.native_adapter import (
    UnknownNativeField,
    native_doctype,
    native_field,
    native_fields,
    native_filters,
    native_priority,
    native_status,
)


class TestDoctypeTranslation(UnitTestCase):
    def test_bp_doctypes_map_to_native(self):
        self.assertEqual(native_doctype("BP Task"), "Task")
        self.assertEqual(native_doctype("BP Project"), "Project")

    def test_satellites_pass_through(self):
        """Only BP Project/BP Task are being replaced; the other 52 remain."""
        for dt in ("BP Sprint", "BP Epic", "BP Milestone", "BP Task Assignee"):
            self.assertEqual(native_doctype(dt), dt)


class TestFieldTranslation(UnitTestCase):
    def test_mapped_field_resolves_to_its_native_counterpart(self):
        self.assertEqual(native_field("Task", "title"), "subject")
        self.assertEqual(native_field("Task", "due_date"), "exp_end_date")
        self.assertEqual(native_field("Project", "client"), "customer")
        self.assertEqual(native_field("Project", "budget_amount"), "estimated_costing")

    def test_description_resolves_differently_per_doctype(self):
        """Mapped on Project, verbatim on Task — the ordering trap."""
        self.assertEqual(native_field("Project", "description"), "notes")
        self.assertEqual(native_field("Task", "description"), "description")

    def test_shared_names_pass_through(self):
        self.assertEqual(native_field("Task", "status"), "status")
        self.assertEqual(native_field("Task", "project"), "project")
        self.assertEqual(native_field("Project", "company"), "company")

    def test_bp_only_fields_get_the_custom_prefix(self):
        self.assertEqual(native_field("Task", "board_rank"), "custom_board_rank")
        self.assertEqual(native_field("Task", "is_deleted"), "custom_is_deleted")
        self.assertEqual(native_field("Project", "key"), "custom_key")

    def test_dropped_concept_resolves_to_none(self):
        """erpnext_project is meaningless once Project IS the model."""
        self.assertIsNone(native_field("Project", "erpnext_project"))

    def test_frappe_standard_fields_resolve(self):
        for f in ("name", "owner", "creation", "modified"):
            self.assertEqual(native_field("Task", f), f)

    def test_unknown_field_raises_rather_than_passing_through(self):
        with self.assertRaises(UnknownNativeField):
            native_field("Task", "no_such_bp_field")

    def test_fields_list_drops_dropped_concepts(self):
        resolved = native_fields("Project", ["key", "erpnext_project", "client"])
        self.assertEqual(resolved, ["custom_key", "customer"])


class TestValueTranslation(UnitTestCase):
    def test_project_status_value_is_translated(self):
        self.assertEqual(native_status("Project", "Active"), "Open")
        self.assertEqual(native_status("Project", "Archived"), "Completed")

    def test_task_status_uses_the_project_workflow_category(self):
        categories = {"In Code Review": "started", "Shipped": "completed"}
        self.assertEqual(native_status("Task", "In Code Review", categories), "Working")
        self.assertEqual(native_status("Task", "Shipped", categories), "Completed")

    def test_unknown_task_state_falls_back_to_unstarted(self):
        """Better a defined lane than an invalid Select value."""
        self.assertEqual(native_status("Task", "Whatever", {}), "Open")

    def test_empty_status_is_left_alone(self):
        self.assertEqual(native_status("Task", "", {}), "")
        self.assertIsNone(native_status("Task", None, {}))

    def test_priority_is_translated(self):
        self.assertEqual(native_priority("Highest"), "Urgent")
        self.assertEqual(native_priority("Lowest"), "Low")


class TestFilterTranslation(UnitTestCase):
    def test_keys_and_values_are_both_translated(self):
        out = native_filters("Task", {"title": "x", "is_deleted": 0})
        self.assertEqual(out, {"subject": "x", "custom_is_deleted": 0})

    def test_status_value_translated_via_categories(self):
        out = native_filters("Task", {"status": "Doing"}, {"Doing": "started"})
        self.assertEqual(out, {"status": "Working"})

    def test_operator_filters_keep_their_value_shape(self):
        """`["in", [...]]` must not be mangled into a status lookup."""
        out = native_filters("Task", {"status": ["in", ["Open", "Working"]]})
        self.assertEqual(out, {"status": ["in", ["Open", "Working"]]})

    def test_dropped_concept_is_removed_from_filters(self):
        out = native_filters("Project", {"erpnext_project": "PROJ-0001", "key": "BIM"})
        self.assertEqual(out, {"custom_key": "BIM"})

    def test_list_filters_are_returned_untouched(self):
        """A partial translation would be worse than an obvious no-op."""
        listy = [["Task", "status", "=", "Open"]]
        self.assertIs(native_filters("Task", listy), listy)
