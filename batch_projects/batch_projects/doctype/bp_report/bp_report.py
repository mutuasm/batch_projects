import frappe
import json
from frappe.model.document import Document


class BPReport(Document):
    def validate(self):
        if self.layout:
            try:
                json.loads(self.layout) if isinstance(self.layout, str) else self.layout
            except (json.JSONDecodeError, TypeError):
                frappe.throw("Report layout must be valid JSON.")
