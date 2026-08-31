"""Invariants for the Custom Fields this app adds to ERPNext's Project/Task.

These fields land on doctypes another app owns, on a site that may also be
running CRM, HRMS and third-party apps. A mistake here does not degrade
BatchProjects — it breaks everyone else's writes to core doctypes. Each
assertion below corresponds to a way that has actually gone wrong or plausibly
could.

Run with:
    bench run-tests --module batch_projects.tests.test_native_fields_invariants
"""

from frappe.tests import UnitTestCase

from batch_projects.setup.native_fields import CUSTOM_FIELDS

# The two doctypes being replaced by native counterparts. Nothing we add to a
# native doctype may point back at them.
_RETIRING = {"BP Project", "BP Task"}

_LINKISH = {"Link", "Table", "Table MultiSelect", "Dynamic Link"}


class TestNativeFieldInvariants(UnitTestCase):
    def _all_fields(self):
        for doctype, rows in CUSTOM_FIELDS.items():
            for row in rows:
                yield doctype, row

    def test_no_field_is_mandatory(self):
        """A Custom Field must never be mandatory on a doctype we don't own.

        Regression: `custom_key` shipped with reqd=1 and erpnext's own test
        records immediately failed with
        `MandatoryError: [Project, PROJ-0001]: custom_key`. Every other
        creation path on the site — CRM, HRMS, real users — would have failed
        the same way. Requiredness belongs on this app's write path, not in the
        shared schema.
        """
        offenders = [
            f"{dt}.{row['fieldname']}"
            for dt, row in self._all_fields()
            if row.get("reqd")
        ]
        self.assertEqual(offenders, [], f"mandatory custom fields on core doctypes: {offenders}")

    def test_every_fieldname_is_custom_prefixed(self):
        """Without the prefix, a future ERPNext field of the same name collides."""
        offenders = [
            f"{dt}.{row['fieldname']}"
            for dt, row in self._all_fields()
            if not row["fieldname"].startswith("custom_")
        ]
        self.assertEqual(offenders, [], f"unprefixed custom fields: {offenders}")

    def test_no_field_points_at_a_retiring_doctype(self):
        """Link/Table targets must be the native doctypes, not BP Project/BP Task.

        The other 52 BP doctypes legitimately remain as satellites, so only
        these two are checked.
        """
        offenders = [
            f"{dt}.{row['fieldname']} -> {row.get('options')}"
            for dt, row in self._all_fields()
            if row.get("fieldtype") in _LINKISH and row.get("options") in _RETIRING
        ]
        self.assertEqual(offenders, [], f"fields still targeting a retiring doctype: {offenders}")

    def test_link_and_table_fields_declare_options(self):
        """A Link or Table with no options is an unresolvable field."""
        offenders = [
            f"{dt}.{row['fieldname']} ({row.get('fieldtype')})"
            for dt, row in self._all_fields()
            if row.get("fieldtype") in _LINKISH and not row.get("options")
        ]
        self.assertEqual(offenders, [], f"link/table fields without options: {offenders}")

    def test_fieldnames_are_unique_per_doctype(self):
        for doctype, rows in CUSTOM_FIELDS.items():
            names = [r["fieldname"] for r in rows]
            duplicates = sorted({n for n in names if names.count(n) > 1})
            self.assertEqual(duplicates, [], f"duplicate fieldnames on {doctype}: {duplicates}")

    def test_targets_only_the_two_native_doctypes(self):
        """Guards against a stray doctype key creeping into the spec."""
        self.assertEqual(set(CUSTOM_FIELDS), {"Project", "Task"})
