# -*- coding: utf-8 -*-
# Copyright (c) 2020, Bantoo and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document


class ExpenseEntry(Document):
	pass


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def expense_account_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search: Expense root accounts and Fixed Asset account type."""
	filters = frappe._dict(filters or {})
	return frappe.db.sql(
		"""
		select name
		from `tabAccount`
		where disabled = 0
			and is_group = 0
			and company = %(company)s
			and (root_type = 'Expense' or account_type = 'Fixed Asset')
			and `{searchfield}` like %(txt)s
		order by
			(case when locate(%(_txt)s, name) > 0 then locate(%(_txt)s, name) else 99999 end),
			name
		limit %(start)s, %(page_len)s
		""".format(
			searchfield=searchfield
		),
		{
			"company": filters.get("company"),
			"txt": "%%%s%%" % txt,
			"_txt": txt.replace("%", ""),
			"start": start,
			"page_len": page_len,
		},
	)
