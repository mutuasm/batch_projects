// Jira-shaped navigation for ERPNext's native Project, on v16 desk views.
//
// Replaces the earlier redirect that sent the stock Project/Task lists into the
// standalone Vue SPA. The SPA is being retired: the desk *is* the UI now, so
// these lists are the real destination rather than something to bounce out of.
//
// In Jira, opening a project lands you on its board, not on a settings form.
// That's what the title link does here — the project name goes to the task
// board scoped to that project, and the form (where you'd edit dates, customer,
// costing) stays one click away on the ID column and the "Settings" button.
//
// Hierarchy is native: Task is `is_tree: 1` with `nsm_parent_field: parent_task`,
// so the Tree view already renders epics → stories → sub-tasks level by level,
// arbitrarily deep. Nothing to build; it just needs a way in.

const BP_BOARD = "Projects Board";

// Only strings are passed to make_url on purpose: handed a plain object it sets
// `frappe.route_options` as a side effect, which would fire once per rendered
// row while merely building an href.
function bp_task_view_url(view, project, extra) {
	const parts = view === "kanban" ? ["task", "view", "kanban", BP_BOARD] : ["task", "view", view];
	const base = frappe.router.make_url(parts);
	const params = new URLSearchParams({ project, ...(extra || {}) });
	return `${base}?${params.toString()}`;
}

function bp_go(view, project, extra) {
	// route_options is how the desk applies filters to the view it opens.
	frappe.route_options = { project, ...(extra || {}) };
	if (view === "kanban") {
		frappe.set_route("task", "view", "kanban", BP_BOARD);
	} else {
		frappe.set_route("task", "view", view);
	}
}

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		// Primary action: the board. This is the Jira default — you open a
		// project to work, not to edit its metadata.
		frm.page.set_primary_action(__("Open Board"), () => bp_go("kanban", frm.doc.name));

		frm.add_custom_button(__("Board"), () => bp_go("kanban", frm.doc.name), __("Tasks"));
		frm.add_custom_button(__("Tree"), () => bp_go("tree", frm.doc.name), __("Tasks"));
		frm.add_custom_button(__("List"), () => bp_go("list", frm.doc.name), __("Tasks"));
		frm.add_custom_button(__("Gantt"), () => bp_go("gantt", frm.doc.name), __("Tasks"));

		// Backlog: unscheduled, not-yet-done work. Native fields only —
		// exp_start_date is ERPNext's own scheduling field, so "no start date
		// and not finished" is a faithful backlog without inventing a flag.
		frm.add_custom_button(
			__("Backlog"),
			() =>
				bp_go("list", frm.doc.name, {
					exp_start_date: ["is", "not set"],
					status: ["not in", ["Completed", "Cancelled", "Template"]],
				}),
			__("Tasks")
		);
	},
});

frappe.listview_settings["Project"] = (function () {
	const existing = frappe.listview_settings["Project"] || {};
	const prior_onload = existing.onload;

	// Merge rather than assign: ERPNext ships its own project_list.js, and
	// Frappe concatenates that before hook files. Overwriting it would drop
	// ERPNext's own indicators and formatters.
	return Object.assign({}, existing, {
		onload(listview) {
			if (typeof prior_onload === "function") {
				try {
					prior_onload.call(this, listview);
				} catch (e) {
					console.error("[Projects] upstream Project list onload failed", e);
				}
			}
			listview.page.add_inner_button(__("Task Board"), () => {
				frappe.set_route("task", "view", "kanban", BP_BOARD);
			});
			listview.page.add_inner_button(__("Task Tree"), () => {
				frappe.set_route("task", "view", "tree");
			});
		},

		formatters: Object.assign({}, existing.formatters, {
			// The project name links to its board instead of its form.
			project_name(value, df, doc) {
				const label = frappe.utils.escape_html(value || doc.name || "");
				if (!doc || !doc.name) {
					return label;
				}
				return `<a href="${bp_task_view_url("kanban", doc.name)}"
				           title="${__("Open board")}">${label}</a>`;
			},
		}),
	});
})();
