"""Regression tests for generate_invoice's fail-closed period contract."""

import unittest
from unittest.mock import patch

import frappe

from batch_projects.api import erp_link


class TestBillingPeriodContract(unittest.TestCase):
    def test_nonempty_period_fails_before_financial_selection(self):
        with (
            patch.object(erp_link, "_check_permission"),
            patch("batch_projects.access.require_capability"),
            patch.object(erp_link.frappe, "get_doc") as get_doc,
            patch.object(erp_link.frappe.db, "sql") as sql,
            patch.object(
                erp_link,
                "guard_timesheet_details",
            ) as guard,
            patch.object(
                erp_link.frappe,
                "new_doc",
            ) as new_doc,
        ):
            with self.assertRaisesRegex(
                frappe.ValidationError,
                "Period-scoped invoice generation is not supported",
            ):
                erp_link.generate_invoice(
                    "BP-PERIOD-TEST",
                    period="last_30_days",
                )

        # Permission + entitlement checks are allowed to run, but no financial
        # source selection/reservation/draft construction may happen.
        get_doc.assert_not_called()
        sql.assert_not_called()
        guard.assert_not_called()
        new_doc.assert_not_called()

    def test_empty_period_values_are_supported_legacy_noops(self):
        for period in (None, "", "   "):
            with self.subTest(period=period):
                erp_link._validate_invoice_period_contract(period)

    def test_blank_period_reaches_normal_invoice_path(self):
        # Prove generate_invoice itself accepts the legacy blank value rather
        # than testing only the helper. Stop deliberately at the first project
        # load so this remains a focused contract test, not another large
        # Sales Invoice fixture.
        with (
            patch.object(erp_link, "_check_permission"),
            patch("batch_projects.access.require_capability"),
            patch.object(
                erp_link.frappe,
                "get_doc",
                side_effect=RuntimeError("normal invoice path reached"),
            ) as get_doc,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "normal invoice path reached",
            ):
                erp_link.generate_invoice(
                    "BP-PERIOD-TEST",
                    period="   ",
                )

        get_doc.assert_called_once_with(
            "BP Project",
            "BP-PERIOD-TEST",
        )

if __name__ == "__main__":
    unittest.main()
