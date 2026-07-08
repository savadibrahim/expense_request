import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def expense_account_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search: Expense root accounts and Fixed Asset account type."""
	filters = frappe._dict(filters or {})
	company = filters.get("company")
	if not company:
		return []

	return frappe.db.sql(
		"""
		select name
		from `tabAccount`
		where disabled = 0
			and is_group = 0
			and company = %(company)s
			and (root_type = 'Expense' or account_type = 'Fixed Asset')
			and `{key}` like %(txt)s
		order by
			(case when locate(%(_txt)s, name) > 0 then locate(%(_txt)s, name) else 99999 end),
			name
		limit %(start)s, %(page_len)s
		""".format(
			key=searchfield
		),
		{
			"company": company,
			"txt": "%%%s%%" % txt,
			"_txt": txt.replace("%", ""),
			"start": start or 0,
			"page_len": page_len or 10,
		},
	)
