"""Every native field NATIVE_FIELD_MAP defers to must actually exist.

Separate from test_native_fields_invariants (which is pure, DB-free) because
this one needs live doctype meta. A typo here is silent: stage 3 would read a
field that does not exist and get None rather than an error, so the mapping is
worth asserting against the real schema.

Run with:
    bench run-tests --module batch_projects.tests.test_native_field_map_targets
"""

import frappe
from frappe.tests import IntegrationTestCase

from batch_projects.setup.native_fields import NATIVE_FIELD_MAP


class TestNativeFieldMapTargets(IntegrationTestCase):
    def test_every_mapped_native_field_exists(self):
        missing = []
        for doctype, mapping in NATIVE_FIELD_MAP.items():
            existing = {df.fieldname for df in frappe.get_meta(doctype).fields}
            for bp_field, native_field in mapping.items():
                # None = the BP field is meaningless now, nothing to point at.
                if native_field and native_field not in existing:
                    missing.append(f"{doctype}.{native_field} (for {bp_field})")
        self.assertEqual(missing, [], f"mapped native fields that do not exist: {missing}")
