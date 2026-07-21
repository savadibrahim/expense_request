# Copyright (c) 2026, Bantoo and contributors
# License: MIT. See license.txt

"""Set status to Cancelled for Expense Entries that were cancelled before workflow had a Cancelled state."""

from __future__ import unicode_literals

import frappe


def execute():
	updated = frappe.db.sql(
		"""
		UPDATE `tabExpense Entry`
		SET status = 'Cancelled'
		WHERE docstatus = 2 AND IFNULL(status, '') != 'Cancelled'
		"""
	)

	count = updated[0] if updated else 0
	if count:
		print(f"Updated status to Cancelled for {count} Expense Entries")
