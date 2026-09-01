"""Server-rendered invitation landing page.

The Vue SPA used to serve /workspace/invite/<token>. Removing the SPA would
have left invitation emails pointing at a 404 — and unlike Draw or the intake
forms, invitations are not a surface anyone chose to drop: without a landing
page there is no way to accept one at all, so project onboarding simply stops.

This is deliberately the smallest thing that keeps the flow working, not a
rebuild of the SPA page:

    already a member   -> straight to the project
    logged in          -> accept, then to the project
    signed out         -> frappe's own /login, with redirect-to back here

What is NOT carried over is the inline "set a password and join" step
(api/invitations.signup_and_accept). That endpoint still exists, but a brand-new
invitee now sets their password through Frappe's standard reset flow rather than
a bespoke form. Reduced, but working — and honest about which part shrank.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    token = frappe.form_dict.get("token") or (frappe.form_dict.get("app_path") or "").strip("/")

    context.no_breadcrumbs = True
    context.title = _("Project invitation")
    context.token = token
    context.error = None
    context.project = None

    if not token:
        context.error = _("This invitation link is missing its token.")
        return context

    if frappe.session.user == "Guest":
        # Bounce through frappe's own login, then land back here.
        frappe.local.flags.redirect_location = (
            f"/login?redirect-to=/invite/{frappe.utils.quoted(token)}"
        )
        raise frappe.Redirect

    from batch_projects.api.invitations import accept_invitation

    try:
        result = accept_invitation(token)
    except Exception as exc:
        # The endpoint throws for a genuinely useful set of reasons — expired,
        # revoked, or addressed to a different account — so surface its message
        # rather than a generic failure.
        context.error = str(exc) or _("This invitation could not be accepted.")
        return context

    project = (result or {}).get("project")
    context.project = project
    if project:
        from batch_projects import desk_urls

        frappe.local.flags.redirect_location = desk_urls.project_url(project)
        raise frappe.Redirect

    return context
