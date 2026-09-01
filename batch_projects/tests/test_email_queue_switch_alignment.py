"""The email-queue authorization guard must track the sender's doctype.

`events._send_notification_email` queues task mail with
`reference_doctype=TASK()`, and `secure_email_queue.BPEmailQueue` decides
whether to re-verify delivery authorization by comparing `reference_doctype`
against the task doctype. If those two ever disagree — say the sender moves to
"Task" while the guard stays pinned to "BP Task" — the guard matches nothing
and the last-mile authorization check silently stops running. No error, no log,
no failing test: email just quietly goes out unchecked.

That is the failure this file exists to prevent, so it asserts they agree in
BOTH switch positions rather than in whichever one happens to be active.

Run with:
    bench run-tests --module batch_projects.tests.test_email_queue_switch_alignment
"""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from batch_projects import doctypes
from batch_projects.secure_email_queue import BPEmailQueue


class _Conf(dict):
    pass


def _with_flag(value):
    conf = _Conf(frappe.conf)
    if value is None:
        conf.pop("bp_use_native_doctypes", None)
    else:
        conf["bp_use_native_doctypes"] = value
    return patch.object(frappe, "conf", conf)


def _queue_row(reference_doctype):
    row = BPEmailQueue({"doctype": "Email Queue"})
    row.reference_doctype = reference_doctype
    row.reference_name = "TASK-1"
    return row


class TestGuardTracksSender(UnitTestCase):
    def test_guard_matches_the_sender_with_the_switch_off(self):
        with _with_flag(None):
            self.assertEqual(doctypes.TASK(), "BP Task")
            self.assertTrue(_queue_row(doctypes.TASK())._is_bp_task_mail())

    def test_guard_matches_the_sender_with_the_switch_on(self):
        with _with_flag(True):
            self.assertEqual(doctypes.TASK(), "Task")
            self.assertTrue(_queue_row(doctypes.TASK())._is_bp_task_mail())

    def test_guard_does_not_match_the_other_models_doctype(self):
        """The specific regression: guard pinned to the wrong side matches nothing."""
        with _with_flag(True):
            self.assertFalse(_queue_row("BP Task")._is_bp_task_mail())
        with _with_flag(None):
            self.assertFalse(_queue_row("Task")._is_bp_task_mail())

    def test_guard_still_requires_a_reference_name(self):
        with _with_flag(None):
            row = _queue_row(doctypes.TASK())
            row.reference_name = None
            self.assertFalse(row._is_bp_task_mail())

    def test_unrelated_mail_is_never_claimed(self):
        """Every other Email Queue row on the site must behave as frappe ships."""
        for flag in (None, True):
            with _with_flag(flag):
                self.assertFalse(_queue_row("Sales Invoice")._is_bp_task_mail())
