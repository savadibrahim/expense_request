# Copyright (c) 2026, Bantoo and contributors
# License: MIT. See license.txt

"""Set status to Cancelled for Expense Entries that were cancelled before workflow had a Cancelled state."""

from __future__ import unicode_literals

import frappe


def execute():
	names = frappe.get_all(
		"Expense Entry",
		filters={"docstatus": 2, "status": ["!=", "Cancelled"]},
		pluck="name",
	)

	for name in names:
		frappe.db.set_value("Expense Entry", name, "status", "Cancelled", update_modified=False)

	if names:
		print(f"Updated status to Cancelled for {len(names)} Expense Entries")
