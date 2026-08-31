// Makes BatchProjects the default Projects experience in ERPNext v16.
//
// Loaded onto the stock `Project` AND `Task` list views via the
// `doctype_list_js` hook (see hooks.py). ERPNext's own lists are what people
// reach from the Projects workspace, the awesome-bar, and every /desk/project
// link ever pasted into a ticket — so replacing "the default project views"
// means intercepting here, not just re-pointing the nav.
//
// One file, registered for both doctypes, deliberately: Frappe's
// get_code_files_via_hooks() only loads the files registered for the doctype
// being rendered, so a helper defined in a Project-only file would simply not
// exist on the Task list. Everything this needs is therefore self-contained.
//
// Frappe concatenates the doctype's own `<name>_list.js` BEFORE hook files
// (see DocTypeMeta.add_code_via_hook), and ERPNext ships both
// project_list.js and task_list.js — each assigning
// frappe.listview_settings[...]. So this MERGES into whatever is already
// registered and chains any existing onload, rather than assigning over it.
// A plain assignment here would silently drop ERPNext's own indicators,
// formatters and add_fields for anyone using the ?desk=1 escape hatch below.
//
// Escape hatch: append `?desk=1` (e.g. `/desk/project?desk=1`) to load the
// stock ERPNext list anyway. The redirect is a default, not a cage — admins
// still need the raw list for imports, bulk edits and Report Builder, and
// support needs to see what core actually holds. The choice sticks for the
// rest of the browser session so a round trip through the stock list doesn't
// bounce on every navigation.

(function () {
	const SESSION_KEY = "bp_prefer_desk_projects";

	function prefers_desk() {
		const params = new URLSearchParams(window.location.search);

		// Explicit opt-out, remembered for the session.
		if (params.get("desk") === "1") {
			try {
				sessionStorage.setItem(SESSION_KEY, "1");
			} catch (e) {
				// Private mode / storage blocked — the URL param still works per visit.
			}
			return true;
		}

		try {
			return sessionStorage.getItem(SESSION_KEY) === "1";
		} catch (e) {
			return false;
		}
	}

	function redirect(listview, target) {
		if (prefers_desk()) {
			// Leave a way back rather than silently stranding someone on the
			// stock list they may have reached by accident.
			if (listview && listview.page && listview.page.add_inner_button) {
				listview.page.add_inner_button(__("Open in BatchProjects"), () => {
					try {
						sessionStorage.removeItem(SESSION_KEY);
					} catch (e) {
						/* nothing to clear */
					}
					window.location.assign(target);
				});
			}
			return;
		}

		// `replace`, not `assign`: the stock list must not sit in the back-button
		// history, or Back from BatchProjects lands here and redirects forward
		// again, trapping the user in a loop.
		window.location.replace(target);
	}

	function install(doctype, target) {
		const existing = frappe.listview_settings[doctype] || {};
		const prior_onload = existing.onload;

		frappe.listview_settings[doctype] = Object.assign({}, existing, {
			onload(listview) {
				// Run ERPNext's own onload first, and never let a failure in it
				// stop the redirect (or vice versa).
				if (typeof prior_onload === "function") {
					try {
						prior_onload.call(this, listview);
					} catch (e) {
						console.error("[BatchProjects] upstream list onload failed", e);
					}
				}
				redirect(listview, target);
			},
		});
	}

	install("Project", "/workspace/all");

	// Task targets My Tasks rather than a project board: the stock Task list is
	// cross-project, and /workspace/my-tasks is the BatchProjects surface with
	// the same scope. Sending it to one project's board would silently narrow
	// what the user asked to see.
	install("Task", "/workspace/my-tasks");
})();
