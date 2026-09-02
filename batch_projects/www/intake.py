"""Server-rendered public intake form: /intake/<form>.

Same story as the share page: the SPA served this route, and dropping the SPA
left every published intake form unreachable. An intake form's whole purpose is
to be handed to people outside the workspace, so a 404 here silently stops
inbound work with nothing to indicate it to the person filling it in.

The API was never removed — `get_public_form` and `submit_intake_form` are both
`allow_guest=True` and still create the task. Only the page was gone.

The URL segment is the BP Intake Form's `name`, which is a random hash: the
doctype used to autoname on `form_title`, making the URL guessable, and both the
doctype and the `rename_intake_forms_to_random` patch fixed that. So the name in
this URL is the credential, exactly as the token is for a share link.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    form = frappe.form_dict.get("form") or (frappe.form_dict.get("app_path") or "").strip("/")

    context.no_breadcrumbs = True
    context.title = _("Submit a request")
    context.error = None
    context.form = None
    context.form_name = form

    if not form:
        context.error = _("This form link is incomplete.")
        return context

    from batch_projects.api.forms import get_public_form

    try:
        context.form = get_public_form(form)
    except Exception as exc:
        # Throws distinctly for "no such form" and "no longer active", and the
        # difference matters to whoever was sent the link.
        context.error = str(exc) or _("This form is not available.")
        return context

    context.title = context.form.get("form_title") or context.title
    return context
