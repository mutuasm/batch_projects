"""Server-rendered public share page: /share/<token>.

The Vue SPA served this route, and removing the SPA left every share link ever
issued pointing at a 404 — including links already sent to clients, which is the
one kind of breakage the people affected cannot do anything about. Worse,
`api.sharing._share_url` still mints `/share/<token>`, so links created *after*
the SPA was dropped were born broken.

Nothing server-side was missing: BP Share Link, `get_shared` and
`add_guest_comment` are all intact and already `allow_guest=True`. Only the page
was gone, so this restores the page and changes no API.

Deliberately read-only, and deliberately plain. The SPA rendered a drag-and-drop
board; this renders the same data as static columns. A share recipient is
reading, not planning — the one write a share link ever permitted is a guest
comment, which is gated on `access_level == "comment"` server-side and only
offered here when the API says it applies.

Everything member-authored is escaped in the template with an explicit `| e`.
Frappe's website Jinja environment does not autoescape — a bare {{ value }}
emits raw HTML, which the first revision of this page did — and this page shows
member-authored text to anonymous visitors, which is the direction stored XSS
travels.
"""

import frappe
from frappe import _

no_cache = 1


def get_context(context):
    token = frappe.form_dict.get("token") or (frappe.form_dict.get("app_path") or "").strip("/")

    context.no_breadcrumbs = True
    context.title = _("Shared")
    context.token = token
    context.error = None
    context.data = None
    context.can_comment = False

    if not token:
        context.error = _("This share link is missing its token.")
        return context

    from batch_projects.api.sharing import get_shared

    try:
        data = get_shared(token)
    except Exception as exc:
        # get_shared throws for a genuinely informative set of reasons —
        # unknown, revoked, expired, or the underlying task deleted — so the
        # visitor is better served by its message than by a generic error.
        context.error = str(exc) or _("This link is no longer available.")
        return context

    context.data = data
    header = data.get("project") or {}
    context.title = header.get("project_name") or _("Shared")

    # The one write a share link can permit. Mirrors add_guest_comment's own
    # preconditions so the box is never shown where the endpoint would refuse.
    context.can_comment = (
        data.get("scope") == "task" and data.get("access_level") == "comment"
    )
    return context
