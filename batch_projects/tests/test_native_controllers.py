"""BP field aliases on the native Task controller.

The alias layer is what lets ~5,400 field references keep working when the model
moves to native Task: `doc.title` reads and writes `subject`. If an alias is
missing the attribute simply does not exist; if one shadows a framework
attribute the breakage surfaces somewhere unrelated. Both are worth pinning.

Run with:
    bench run-tests --module batch_projects.tests.test_native_controllers
"""

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from batch_projects.native_controllers import BPTask, _bp_to_native

# Names that must never be shadowed by an alias: framework-owned, or identical
# on both models.
_PROTECTED = {
    "name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
    "status", "priority", "project", "parent_task", "description",
    "completed_by", "completed_on",
}


class TestTaskAliases(UnitTestCase):
    def test_bp_only_fields_are_aliased(self):
        for bp_field in ("title", "is_deleted", "board_rank", "task_key", "story_points"):
            self.assertIn(bp_field, BPTask._bp_aliases, f"{bp_field} has no alias")

    def test_title_maps_to_subject(self):
        self.assertEqual(_bp_to_native("Task")["title"], "subject")

    def test_no_alias_shadows_a_protected_name(self):
        """Overriding `name` or a Document method breaks things far from here."""
        offenders = sorted(set(BPTask._bp_aliases) & _PROTECTED)
        self.assertEqual(offenders, [], f"aliases shadow framework/shared names: {offenders}")

    def test_aliases_are_properties_not_plain_attributes(self):
        """A plain class attribute would be shared across every document."""
        for bp_field in BPTask._bp_aliases[:5]:
            self.assertIsInstance(
                getattr(BPTask, bp_field), property, f"{bp_field} is not a property"
            )

    def test_subclasses_the_real_erpnext_controller(self):
        """frappe rejects an override that is not a subclass of the original."""
        from erpnext.projects.doctype.task.task import Task

        self.assertTrue(issubclass(BPTask, Task))


class TestControllerWiring(IntegrationTestCase):
    def test_task_resolves_to_the_aliased_controller(self):
        from frappe.model.base_document import get_controller

        self.assertIs(get_controller("Task"), BPTask)

    def test_project_controller_is_left_to_whoever_owns_it(self):
        """HRMS registers EmployeeProject for Project and frappe applies only
        one override — ours would displace theirs, silently removing another
        app's behaviour."""
        overrides = frappe.get_hooks("override_doctype_class", app_name="batch_projects") or {}
        self.assertNotIn("Project", overrides)

    def test_alias_reads_and_writes_the_native_field(self):
        doc = frappe.new_doc("Task")
        doc.subject = "written natively"
        self.assertEqual(doc.title, "written natively")
        doc.title = "written through the alias"
        self.assertEqual(doc.subject, "written through the alias")


class TestProjectAliasesAugmentRatherThanOverride(IntegrationTestCase):
    """Project aliases must be added to HRMS's controller, never replace it.

    HRMS registers EmployeeProject for Project and frappe applies only one
    override — ours would displace theirs, silently removing another app's
    behaviour from a site running HR, with the winner flipping on install
    order. So the properties are attached to whatever class frappe already
    resolved.

    159 Project field accesses depend on these aliases; the alternative was
    translating each by hand, every one a chance to silently read None.
    """

    def test_installing_aliases_does_not_replace_the_controller(self):
        from frappe.model.base_document import get_controller
        from batch_projects.native_controllers import install_project_aliases

        before = get_controller("Project")
        install_project_aliases()
        self.assertIs(get_controller("Project"), before, "the controller was replaced")

    def test_another_apps_controller_survives(self):
        """On a site with HRMS this must still be EmployeeProject."""
        from frappe.model.base_document import get_controller
        from batch_projects.native_controllers import install_project_aliases

        install_project_aliases()
        controller = get_controller("Project")
        overrides = frappe.get_hooks("override_doctype_class") or {}
        for path in overrides.get("Project", []):
            owner = path.rsplit(".", 1)[-1]
            self.assertTrue(
                any(c.__name__ == owner for c in controller.__mro__),
                f"{owner} was displaced from the Project controller",
            )

    def test_aliases_read_and_write_the_native_field(self):
        from batch_projects.native_controllers import install_project_aliases

        install_project_aliases()
        doc = frappe.new_doc("Project")
        doc.customer = "written natively"
        self.assertEqual(doc.client, "written natively")
        doc.client = "written through the alias"
        self.assertEqual(doc.customer, "written through the alias")

    def test_installing_twice_is_harmless(self):
        from batch_projects.native_controllers import install_project_aliases

        install_project_aliases()
        install_project_aliases()
        from frappe.model.base_document import get_controller

        self.assertTrue(hasattr(get_controller("Project"), "client"))

    def test_both_request_and_job_entrypoints_are_registered(self):
        """Background jobs never go through before_request."""
        for hook in ("before_request", "before_job"):
            registered = frappe.get_hooks(hook, app_name="batch_projects") or []
            self.assertTrue(
                any("native_controllers" in h for h in registered),
                f"{hook} does not install the Project aliases",
            )
