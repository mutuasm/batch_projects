"""Query helpers that translate BP field names for the active model.

A doctype name is only half a query. After the re-key, call sites still ask for
BP columns on a native doctype:

    frappe.get_all(TASK(), fields=["title"], filters={"is_deleted": 0})

Getting this wrong is silent in the worst way — a filter naming a column that
does not exist returns the wrong rows rather than raising, so nothing fails and
the data is simply incorrect. Hence tests on both switch positions, and an
explicit assertion that OFF changes nothing at all.

Run with:
    bench run-tests --module batch_projects.tests.test_bp_query
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from batch_projects import bp_query as q


class _Conf(dict):
    pass


def _flag(value):
    conf = _Conf(frappe.conf)
    if value is None:
        conf.pop("bp_use_native_doctypes", None)
    else:
        conf["bp_use_native_doctypes"] = value
    return patch.object(frappe, "conf", conf)


class TestPassThroughWhenOff(UnitTestCase):
    """With the switch off, the wrappers must be invisible."""

    def test_nothing_is_translated(self):
        with _flag(None):
            kwargs = {"fields": ["title"], "filters": {"is_deleted": 0},
                      "order_by": "board_rank asc", "pluck": "task_key"}
            self.assertEqual(q._translate("BP Task", kwargs), kwargs)

    def test_unknown_doctypes_pass_through_even_when_on(self):
        """Only Project/Task are being migrated; every other doctype is not ours."""
        with _flag(True):
            kwargs = {"fields": ["subject"], "filters": {"x": 1}}
            self.assertEqual(q._translate("Sales Invoice", kwargs), kwargs)


class TestTranslationWhenOn(UnitTestCase):
    def test_fields_and_filters(self):
        with _flag(True):
            out = q._translate("Task", {"fields": ["title", "status"],
                                        "filters": {"is_deleted": 0}})
            self.assertEqual(out["fields"], ["subject", "status"])
            self.assertEqual(out["filters"], {"custom_is_deleted": 0})

    def test_pluck_is_translated(self):
        with _flag(True):
            self.assertEqual(q._translate("Task", {"pluck": "task_key"})["pluck"],
                             "custom_task_key")

    def test_order_by_keeps_its_direction(self):
        """Only the field part moves; `asc`/`desc` must survive intact."""
        with _flag(True):
            self.assertEqual(q._translate("Task", {"order_by": "board_rank asc"})["order_by"],
                             "custom_board_rank asc")

    def test_order_by_handles_several_clauses(self):
        with _flag(True):
            out = q._translate("Task", {"order_by": "board_rank asc, title desc"})["order_by"]
            self.assertEqual(out, "custom_board_rank asc, subject desc")

    def test_unrecognised_order_expression_is_left_alone(self):
        """Better an untranslated expression than a mangled one."""
        with _flag(True):
            out = q._translate("Task", {"order_by": "modified desc"})["order_by"]
            self.assertEqual(out, "modified desc")

    def test_project_and_task_translate_differently(self):
        """`description` is mapped on Project and verbatim on Task."""
        with _flag(True):
            self.assertEqual(q._translate("Project", {"fields": ["description"]})["fields"],
                             ["notes"])
            self.assertEqual(q._translate("Task", {"fields": ["description"]})["fields"],
                             ["description"])

    def test_both_spellings_of_the_doctype_are_accepted(self):
        """A caller should not have to know which side of the switch it is on."""
        with _flag(True):
            for spelling in ("Task", "BP Task"):
                self.assertEqual(
                    q._translate(spelling, {"fields": ["title"]})["fields"], ["subject"]
                )

    def test_non_dict_filters_are_not_half_translated(self):
        """A record name is not a field reference; list filters are refused."""
        with _flag(True):
            listy = [["Task", "status", "=", "Open"]]
            self.assertIs(q._translate("Task", {"filters": listy})["filters"], listy)


class TestCallShapeIsPreserved(UnitTestCase):
    """A wrapper that normalises call shape is not a pass-through.

    Two existing tests proved this from opposite directions: test_dashboard_
    security reads `count.call_args.kwargs["filters"]` while
    test_live_task_surface_invariants reads `count.call_args.args[1]`, because
    the two original call sites passed filters differently. An earlier version
    of these wrappers forced everything to keyword form and broke the second
    while fixing the first.

    Nothing failed at runtime either time — frappe accepts both — so only
    introspection broke. Anything else reading those call args would have
    silently seen the wrong thing.
    """

    def _shape(self, call):
        return tuple(call.args[1:]), dict(call.kwargs)

    def test_positional_filters_stay_positional(self):
        for flag_value in (None, True):
            with _flag(flag_value):
                with patch.object(frappe.db, "count") as mock:
                    q.count("BP Task", {"is_deleted": 0})
                args, kwargs = self._shape(mock.call_args)
                self.assertEqual(len(args), 1, "positional filters became a keyword")
                self.assertEqual(kwargs, {})

    def test_keyword_filters_stay_keyword(self):
        for flag_value in (None, True):
            with _flag(flag_value):
                with patch.object(frappe.db, "count") as mock:
                    q.count("BP Task", filters={"is_deleted": 0})
                args, kwargs = self._shape(mock.call_args)
                self.assertEqual(args, ())
                self.assertIn("filters", kwargs)

    def test_translation_still_happens_in_both_shapes(self):
        with _flag(True):
            with patch.object(frappe.db, "count") as mock:
                q.count("Task", {"is_deleted": 0})
            self.assertEqual(mock.call_args.args[1], {"custom_is_deleted": 0})

            with patch.object(frappe.db, "count") as mock:
                q.count("Task", filters={"is_deleted": 0})
            self.assertEqual(mock.call_args.kwargs["filters"], {"custom_is_deleted": 0})

    def test_get_value_preserves_positional_fieldname(self):
        with _flag(True):
            with patch.object(frappe.db, "get_value") as mock:
                q.get_value("Task", "TASK-1", "title")
            self.assertEqual(mock.call_args.args, ("Task", "TASK-1", "subject"))
