# Copyright (c) 2026, Bantoo and contributors
# License: MIT. See license.txt

"""Sync Expense Entry posting_date with required_by (expense date).

For submitted entries where posting_date != date(required_by), this script:
1. Cancels the linked Journal Entry (if any)
2. Cancels the Expense Entry
3. Creates an amended copy with the corrected posting_date
4. Submits the amended entry (which recreates the Journal Entry)

Run a dry run first:
    bench --site <site> execute expense_request.patches.sync_expense_posting_dates.execute

Apply fixes:
    bench --site <site> execute expense_request.patches.sync_expense_posting_dates.execute --kwargs "{'dry_run': False}"
"""

from __future__ import unicode_literals

import frappe
from frappe.utils import getdate, now


def execute(dry_run=True, company=None, from_date=None, to_date=None):
	"""Fix posting_date on submitted Expense Entries.

	Args:
		dry_run: If True, only report entries that would be updated.
		company: Optional company filter.
		from_date: Optional filter on required_by date (inclusive).
		to_date: Optional filter on required_by date (inclusive).
	"""
	frappe.only_for("System Manager")

	entries = get_mismatched_entries(company=company, from_date=from_date, to_date=to_date)
	summary = {"total": len(entries), "fixed": 0, "skipped": 0, "failed": 0, "dry_run": dry_run}

	if not entries:
		frappe.msgprint("No submitted Expense Entries with mismatched posting dates found.")
		return summary

	frappe.msgprint(f"Found {len(entries)} Expense Entries to process.")

	for row in entries:
		name = row.name
		target_date = getdate(row.required_by)
		current_date = getdate(row.posting_date)

		if dry_run:
			print(
				f"[DRY RUN] {name}: posting_date {current_date} -> {target_date} "
				f"(required_by={row.required_by})"
			)
			summary["fixed"] += 1
			continue

		try:
			result = fix_expense_entry(name, target_date)
			frappe.db.commit()
			print(f"[OK] {name}: {result}")
			summary["fixed"] += 1
		except Exception:
			frappe.db.rollback()
			summary["failed"] += 1
			frappe.log_error(
				title=f"Failed to sync posting date for {name}",
				message=frappe.get_traceback(),
			)
			print(f"[FAILED] {name}: see Error Log")

	print_summary(summary)
	return summary


def get_mismatched_entries(company=None, from_date=None, to_date=None):
	"""Return submitted Approved entries where posting_date != date(required_by)."""
	filters = {
		"docstatus": 1,
		"status": "Approved",
	}

	if company:
		filters["company"] = company

	entries = frappe.get_all(
		"Expense Entry",
		filters=filters,
		fields=["name", "posting_date", "required_by", "company"],
		order_by="posting_date asc",
	)

	mismatched = []
	for entry in entries:
		if not entry.required_by:
			continue

		target_date = getdate(entry.required_by)
		current_date = getdate(entry.posting_date) if entry.posting_date else None

		if current_date == target_date:
			continue

		if from_date and target_date < getdate(from_date):
			continue
		if to_date and target_date > getdate(to_date):
			continue

		mismatched.append(entry)

	return mismatched


def fix_expense_entry(name, target_posting_date):
	"""Cancel, amend, and resubmit a single Expense Entry with corrected posting_date."""
	if frappe.db.exists("Expense Entry", {"amended_from": name, "docstatus": ["!=", 2]}):
		return "skipped (active amendment already exists)"

	doc = frappe.get_doc("Expense Entry", name)
	target_posting_date = getdate(target_posting_date)

	if getdate(doc.posting_date) == target_posting_date:
		return "skipped (already correct)"

	cancel_linked_journal_entry(name)

	doc.reload()
	doc.flags.ignore_permissions = True
	doc.cancel()

	amended = frappe.copy_doc(doc)
	amended.docstatus = 0
	amended.amended_from = doc.name
	amended.set_posting_time = 1
	amended.posting_date = target_posting_date
	amended.status = "Pending"

	if amended.meta.get_field("workflow_state"):
		amended.workflow_state = "Approved"

	amended.flags.ignore_permissions = True
	amended.insert()

	amended.status = "Approved"
	amended.flags.ignore_permissions = True
	amended.submit()

	return f"amended to {amended.name}, posting_date={target_posting_date}"


def cancel_linked_journal_entry(expense_entry_name):
	je_names = frappe.get_all(
		"Journal Entry",
		filters={"bill_no": expense_entry_name, "docstatus": 1},
		pluck="name",
	)

	for je_name in je_names:
		je = frappe.get_doc("Journal Entry", je_name)
		je.flags.ignore_permissions = True
		je.cancel()


def print_summary(summary):
	mode = "DRY RUN" if summary["dry_run"] else "COMPLETED"
	print(
		f"\n{mode}: {summary['total']} found, "
		f"{summary['fixed']} {'would fix' if summary['dry_run'] else 'fixed'}, "
		f"{summary['skipped']} skipped, {summary['failed']} failed"
	)
