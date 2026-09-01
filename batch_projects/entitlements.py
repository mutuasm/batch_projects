"""
batch_projects/entitlements.py
──────────────────────────────
Workspace feature switches. **There is no paid tier, licence, seat cap or
gateway in BatchProjects any more** — every feature ships enabled for every
install.

This module used to be the monetization map: a tier ladder (starter → team →
business → enterprise) resolved from a bp-gateway-signed `X-BP-Tier` header,
a seat cap from `X-BP-Max-Users`, and a `feature → minimum tier` catalog that
gated ~20 surfaces. All of that is gone, along with the gateway that asserted
it. What remains is the one switch that was never about money:

    BP Workspace Settings.features_json — a workspace admin turning a surface
    off for their own org (notes, draw, gantt, money tab, timesheets,
    reports).

`is_feature_enabled()` / `require_feature()` are kept as always-allow shims so
the ~70 historical call sites keep working and can be removed incrementally;
they are no-ops and never raise. New code should not call them.

`get_entitlements()` keeps its original response shape — the SPA bootstraps
off it — but every feature reports enabled and seats report unlimited.
"""

import json

import frappe

from batch_projects.doctypes import PROJECT, TASK

# Every feature key the SPA knows about. This is no longer a monetization map:
# it exists only so `get_entitlements()` can keep returning the
# `{feature: bool}` dict the frontend bootstraps against. Every value is True.
_ALL_FEATURES = (
    "automations",
    "webhooks",
    "templates",
    "scheduler",
    "integrations",
    "intake_forms",
    "time_tracking",
    "realtime",
    "share_links",
    "draw",
    "notification_rules",
    "dashboards",
    "exports",
    "custom_branding",
    "goals",
    "profitability",
    "portfolio",
    "billing_writeback",
    "api",
    "sso",
    "audit_log",
)

# Workspace-admin-configurable on/off switches (BP Workspace Settings.features_json).
# A workspace admin can turn a core surface off for their own org. Absent key =
# enabled (opt-out, not opt-in), so a stale record from before a new toggle
# shipped still passes.
_WORKSPACE_FEATURE_DEFAULTS = {
    "notes": True,
    "draw": True,
    "gantt": True,
    "money_tab": True,
    "timesheets": True,
    "reports": True,
}


class BPFeatureDisabled(frappe.ValidationError):
    """Raised when a workspace admin has switched a feature off for their org."""

    pass


# Retained so any lingering `except BPUpgradeRequired` / patch target resolves.
# Nothing raises it any more — there is no plan to upgrade to.
BPUpgradeRequired = BPFeatureDisabled


# ─── AUTOMATION ENGINE ───────────────────────────────────────────────────────

def automation_engine() -> str:
    """Which engine evaluates automation rules.

    The Go gateway engine is gone, so this is always the in-process Python
    matcher. A site_config `bp_automation_engine` override is still honoured so
    an operator can point at a future engine without a code change, but nothing
    ships one.
    """
    explicit = (frappe.conf.get("bp_automation_engine") or "").strip().lower()
    return explicit or "python"


# ─── FEATURE CHECKS (always-allow shims) ─────────────────────────────────────

def is_feature_enabled(feature: str) -> bool:
    """Always True. Kept for the historical call sites; there are no tiers."""
    return True


def require_feature(feature: str):
    """No-op. Kept for the historical call sites; there are no tiers."""
    return None


# ─── WORKSPACE ADMIN TOGGLES (the real, remaining switch) ────────────────────

def get_workspace_features() -> dict:
    """The effective on/off state of every workspace-toggleable feature,
    defaults applied for anything the settings record doesn't mention yet."""
    flags = dict(_WORKSPACE_FEATURE_DEFAULTS)
    try:
        raw = frappe.db.get_single_value("BP Workspace Settings", "features_json")
        overrides = json.loads(raw) if raw else {}
        for k, v in overrides.items():
            if k in flags:
                flags[k] = bool(v)
    except Exception:
        # Doctype not migrated yet, or a malformed record — fail open to the
        # defaults rather than breaking bootstrap for the whole SPA.
        pass
    return flags


def is_workspace_feature_enabled(feature: str) -> bool:
    return get_workspace_features().get(feature, True)


def require_workspace_feature(feature: str):
    """Raise BPFeatureDisabled if a workspace admin has switched `feature` off."""
    if not is_workspace_feature_enabled(feature):
        frappe.throw(
            f"The {feature.replace('_', ' ').title()} feature has been turned "
            f"off for this workspace. Ask a workspace admin to re-enable it in "
            f"Workspace Settings.",
            exc=BPFeatureDisabled,
            title="Feature disabled",
        )


# ─── SEATS (uncapped) ────────────────────────────────────────────────────────
#
# Seat caps were a licence artifact. Membership is now unlimited; the count is
# still reported because the SPA renders it as a plain "N members" stat.

def count_active_seats() -> int:
    """How many distinct users hold a project or team membership."""
    rows = frappe.get_all("BP Project Member", fields=["user"], pluck="user")
    team_rows = frappe.get_all("BP Team Member", fields=["user"], pluck="user")
    return len({u for u in list(rows) + list(team_rows) if u})


# ─── BRANDING ────────────────────────────────────────────────────────────────

def get_branding():
    """White-label branding for every member's shell. Previously gated behind
    the `custom_branding` tier feature; now always available."""
    try:
        doc = frappe.get_single("BP Workspace Settings")
    except Exception:
        return {"brand_name": None, "logo_url": None, "favicon_url": None}
    return {
        "brand_name": doc.brand_name or None,
        "logo_url": doc.logo_url or None,
        "favicon_url": doc.favicon_url or None,
    }


# ─── SPA BOOTSTRAP ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_entitlements():
    """Drives the SPA bootstrap.

    Response shape is unchanged from the licensed era so the frontend needs no
    rewrite, but every feature reports enabled, seats are unlimited, and all
    licence/expiry fields are permanently null.
    """
    from batch_projects import access

    return {
        # No tiers. Reported as the single edition this app now ships.
        "tier": "community",
        "tier_label": "Community",
        "packs": [],
        "features": {f: True for f in _ALL_FEATURES},
        # Retained key, now empty: nothing has a minimum tier.
        "feature_min_tier": {},
        # Licence fields kept as nulls purely so the SPA's optional-chaining
        # banner logic keeps type-checking; there is no licence to expire.
        "expires_at": None,
        "is_trial": False,
        "trial_days_remaining": None,
        "days_remaining": None,
        # Admin on/off switches (BP Workspace Settings) — the one real gate.
        "workspace_features": get_workspace_features(),
        # Cheap boolean so the sidebar/router can show the Workspace Settings
        # entry without a second bootstrap round trip — the settings API
        # re-checks this server-side regardless, this is UI-visibility only.
        "is_workspace_admin": access.is_workspace_admin(),
        # 0 = unlimited.
        "limits": {"max_users": 0},
        "seats_used": count_active_seats(),
        # The resolved {role: {capability: bool}} grid. Same role for every
        # project (it's a workspace-wide policy, not project data), so it's
        # piggybacked on this existing bootstrap rather than a new endpoint.
        "capability_matrix": access.get_capability_matrix(),
        # Cross-project surfaces (the margin report has no single project to
        # resolve a role against) get a pre-resolved boolean instead — UI-
        # visibility only, the endpoint re-checks server-side regardless.
        "view_money_anywhere": access.has_capability_anywhere("view_money"),
        "branding": get_branding(),
        # The SPA's own get_projects is deliberately access-filtered, so
        # "my project list is empty" can mean either "this workspace has no
        # projects at all" (true first-run — show the create-workspace wizard)
        # or "projects exist but none are shared with me yet" (an invited
        # teammate — show a lightweight join/waiting state instead).
        "workspace_has_projects": bool(frappe.db.exists(PROJECT(), {})),
        # Per-user "I've already seen/skipped onboarding" — without this,
        # onboarding re-fired on every reload for anyone who skipped it.
        "onboarding_dismissed": frappe.defaults.get_user_default("bp_onboarding_dismissed") == "1",
        "dismissed_nudges": _dismissed_nudges(),
    }


# ─── ONBOARDING / NUDGE DISMISSAL ────────────────────────────────────────────

@frappe.whitelist()
def dismiss_onboarding():
    """Persist that the current user has seen/skipped/completed the
    onboarding wizard, so it stops re-firing on every reload."""
    frappe.defaults.set_user_default("bp_onboarding_dismissed", "1", frappe.session.user)
    frappe.db.commit()
    return {"ok": True}


NUDGE_DEFAULT_PREFIX = "bp_nudge_dismissed_"


@frappe.whitelist()
def dismiss_nudge(nudge_id: str):
    """Persist that the current user dismissed a specific nudge card
    (see get_entitlements' dismissed_nudges) so it never reappears for them."""
    frappe.defaults.set_user_default(f"{NUDGE_DEFAULT_PREFIX}{nudge_id}", "1", frappe.session.user)
    frappe.db.commit()
    return {"ok": True}


def _dismissed_nudges() -> list[str]:
    defaults = frappe.defaults.get_defaults() or {}
    return [
        key[len(NUDGE_DEFAULT_PREFIX):]
        for key, value in defaults.items()
        if key.startswith(NUDGE_DEFAULT_PREFIX) and value == "1"
    ]
