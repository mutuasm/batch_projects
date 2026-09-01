"""Move BP data onto ERPNext's native Project/Task — but only when asked.

Runs the three migration steps in the one order that works:

    1. run_native_migration()      create/backfill the native rows
    2. retarget_satellite_links()  point 39 satellite Link fields at them
    3. retarget_child_tables()     re-parent assignees, members, links, refs

Steps 2 and 3 both depend on step 1 having recorded a mapping anchor, and
step 2 must not run before the native rows exist or every satellite Link
dangles. Each step is independently idempotent, so a re-run after a partial
failure resumes rather than duplicating.

This is a no-op unless `bp_use_native_doctypes` is set in site_config. That is
deliberate: the migration creates real Project and Task rows, and doing so on
a site that has not opted in would mean data nobody asked for and nothing
reads. Operators can see exactly what it would do first, without writing
anything, via:

    bench --site <site> execute \
        batch_projects.setup.native_migration.dry_run_native_migration
"""

import frappe

from batch_projects.doctypes import use_native


def execute():
    if not use_native():
        frappe.logger("batch_projects").info(
            "native model not enabled (bp_use_native_doctypes unset) — skipping migration"
        )
        return

    from batch_projects.setup.native_migration import (
        retarget_child_tables,
        retarget_satellite_links,
        run_native_migration,
    )

    frappe.logger("batch_projects").info(f"native migration: {run_native_migration()}")
    frappe.logger("batch_projects").info(f"satellite links: {retarget_satellite_links()}")
    frappe.logger("batch_projects").info(f"child tables:    {retarget_child_tables()}")
