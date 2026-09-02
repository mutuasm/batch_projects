// Work-breakdown view of the project hierarchy.
//
// `tree: true` makes frappe's datatable render the `indent` each row carries
// as an expandable level, which is what gives this the level-by-level shape
// without native Project being a nested set.
frappe.query_reports["Project WBS"] = {
	tree: true,
	initial_depth: 3,
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Completed", "Cancelled"].join("\n"),
		},
		{
			fieldname: "include_completed",
			label: __("Include completed"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
