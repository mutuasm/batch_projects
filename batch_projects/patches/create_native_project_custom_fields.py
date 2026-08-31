"""Stage 1 of the native-doctype migration.

Adds the BP field set to ERPNext's native Project/Task as Custom Fields on
existing installs (fresh installs get them from after_install). Additive and
idempotent — see batch_projects/setup/native_fields.py for why the fields are
`custom_`-prefixed and why only BP Project/BP Task link targets are retargeted.
"""

from batch_projects.setup.native_fields import create_native_project_fields


def execute():
    create_native_project_fields()
