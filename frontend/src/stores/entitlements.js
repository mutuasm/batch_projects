/**
 * entitlements.js — workspace feature state.
 *
 * There is no paid tier, licence or seat cap in BatchProjects any more: every
 * feature ships enabled for every install (see batch_projects/entitlements.py).
 * What remains here is the state the SPA genuinely needs at bootstrap:
 *
 *   • workspaceFeatures — a workspace admin's own on/off toggles
 *   • capabilityMatrix / viewMoneyAnywhere — role-based capability grid
 *   • branding — white-label shell (now always available)
 *   • onboarding + nudge dismissal
 *
 * The tier-shaped exports (`can`, `isPaid`, `seatsTotal`, `showUpgradePrompt`,
 * `requiredPlanFor`, …) are kept as always-allow constants so the components
 * that historically gated on them keep working and can be cleaned up
 * incrementally. `can()` always returns true.
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import * as api from "@/utils/api";

export const useEntitlementsStore = defineStore("entitlements", () => {
  const workspaceFeatures = ref({}); // { gantt: true|false, ... } — admin on/off toggle
  const isWorkspaceAdmin = ref(false);
  const loaded = ref(false);
  // { role: { capability: bool } }, same for every project (a workspace-wide
  // policy, not project data). Combine with the per-project role from the
  // project store's my_capabilities call to answer "can I see money/files
  // HERE" — see stores/project.js `hasCapability`.
  const capabilityMatrix = ref({});
  // Cross-project surfaces (margin report) have no single project to resolve a
  // role against — pre-resolved by the backend instead.
  const viewMoneyAnywhere = ref(true);
  // White-label branding — null fields = default app branding.
  const branding = ref({ brand_name: null, logo_url: null, favicon_url: null });
  // Distinguishes "this workspace has zero projects at all" (true first-run,
  // App.vue shows the create-workspace wizard) from "my own project list is
  // empty because nothing's shared with me yet" (an invited teammate —
  // App.vue shows a lighter join/waiting state instead).
  const workspaceHasProjects = ref(true); // fail-open: don't wizard-trap an existing workspace on a slow/failed bootstrap
  const onboardingDismissed = ref(false);
  // Dismissable nudge/announcement cards (floating, bottom-corner — see
  // ui/NudgeCard.vue). Per-user, per-nudge-id persistence via frappe.defaults
  // (batch_projects.entitlements.dismiss_nudge), same mechanism as onboarding.
  const dismissedNudges = ref(new Set());

  // ── Retained, plan-free constants ────────────────────────────────────
  // Every install is the single Community edition now. These are exported
  // because components still read them; none of them gate anything.
  const tier = ref("community");
  const tierLabel = ref("Community");
  const features = ref({});
  const limits = ref({ max_users: 0 });
  const isPaid = computed(() => false);
  const seatsUsed = computed(() => limits.value.seats_used ?? 0);
  const seatsTotal = computed(() => 0); // 0 = unlimited
  const seatsRemaining = computed(() => Infinity);
  const isAtCapacity = computed(() => false);
  const expiresAt = computed(() => null);
  const daysRemaining = computed(() => null);
  const isExpiringSoon = computed(() => false);
  const isExpired = computed(() => false);
  const isTrial = computed(() => false);
  const trialDaysRemaining = computed(() => null);

  /** Apply an entitlements payload from `get_entitlements`. */
  function applyEntitlements(e) {
    if (!e) return;
    features.value = e.features || {};
    const base = e.limits || {};
    if (e.seats_used != null) base.seats_used = e.seats_used;
    limits.value = base;
    workspaceFeatures.value = e.workspace_features || {};
    isWorkspaceAdmin.value = e.is_workspace_admin === true;
    capabilityMatrix.value = e.capability_matrix || {};
    viewMoneyAnywhere.value = e.view_money_anywhere !== false;
    branding.value = e.branding || { brand_name: null, logo_url: null, favicon_url: null };
    if (e.workspace_has_projects !== undefined) workspaceHasProjects.value = e.workspace_has_projects;
    if (e.onboarding_dismissed !== undefined) onboardingDismissed.value = e.onboarding_dismissed;
    if (Array.isArray(e.dismissed_nudges)) dismissedNudges.value = new Set(e.dismissed_nudges);
    loaded.value = true;
  }

  // Call when the onboarding wizard (or the lighter "nothing shared with you
  // yet" state) is dismissed, skipped, or completed. Optimistic: flips the
  // local flag immediately so it can't re-fire later in the same session even
  // if the request is slow; the server call makes it stick across reloads.
  async function dismissOnboarding() {
    onboardingDismissed.value = true;
    try {
      await api.dismissOnboarding();
    } catch {
      // Best-effort — worst case it re-prompts next session, not a lockout.
    }
  }

  async function load() {
    try {
      applyEntitlements(await api.getEntitlements());
    } catch {
      // Nothing to fail closed to any more — mark loaded so the shell renders
      // rather than blocking on a transient bootstrap failure.
      loaded.value = true;
    }
  }

  /** Branding lives in Frappe's BP Workspace Settings, and carries
   *  workspace_has_projects / onboarding_dismissed / dismissed_nudges with it.
   *  Kept separate so a caller can refresh just those without re-seeding the
   *  whole bootstrap. */
  async function loadBranding() {
    try {
      const e = await api.getEntitlements();
      branding.value = e.branding || { brand_name: null, logo_url: null, favicon_url: null };
      if (e.workspace_has_projects !== undefined) workspaceHasProjects.value = e.workspace_has_projects;
      if (e.onboarding_dismissed !== undefined) onboardingDismissed.value = e.onboarding_dismissed;
      if (Array.isArray(e.dismissed_nudges)) dismissedNudges.value = new Set(e.dismissed_nudges);
    } catch {
      // Leave whatever's already loaded — a transient failure here shouldn't
      // strip a workspace's custom branding or re-wizard-trap.
    }
  }

  /** True once the user has dismissed this specific nudge (any device, any session). */
  const isNudgeDismissed = (nudgeId) => dismissedNudges.value.has(nudgeId);

  /** Optimistic, same pattern as dismissOnboarding. */
  async function dismissNudge(nudgeId) {
    dismissedNudges.value.add(nudgeId);
    try {
      await api.dismissNudge(nudgeId);
    } catch {
      // Best-effort — worst case it reappears next session, not a lockout.
    }
  }

  /** Always true — there are no plan-gated features. */
  const can = () => true;

  /** True unless a workspace admin explicitly switched `feature` off
   *  (BP Workspace Settings). Absent key = enabled — default open, not closed. */
  const canWorkspace = (feature) => workspaceFeatures.value[feature] !== false;

  /** Retained for callers that render upgrade copy; there is no plan to name. */
  const requiredPlanFor = () => "";

  /** Pure lookup, given an already-resolved role string. Defaults to true when
   *  the bootstrap hasn't loaded yet or the role is unknown — cosmetic-only,
   *  same "fail open, server re-checks" posture as canWorkspace. */
  const hasCapability = (role, cap) => {
    if (!role) return false;
    const row = capabilityMatrix.value[role];
    return row ? row[cap] !== false : true;
  };

  /** No-op. Nothing is gated by a plan, so there is nothing to upgrade to.
   *  Kept so historical call sites don't throw. */
  function showUpgradePrompt() {}

  return {
    tier, tierLabel, features, workspaceFeatures, isWorkspaceAdmin, limits, loaded, isPaid,
    capabilityMatrix, viewMoneyAnywhere, branding,
    workspaceHasProjects, onboardingDismissed,
    dismissedNudges, isNudgeDismissed, dismissNudge,
    seatsUsed, seatsTotal, seatsRemaining, isAtCapacity,
    expiresAt, daysRemaining, isExpiringSoon, isExpired,
    isTrial, trialDaysRemaining,
    load, loadBranding, applyEntitlements, can, canWorkspace, requiredPlanFor, hasCapability,
    showUpgradePrompt, dismissOnboarding,
  };
});
