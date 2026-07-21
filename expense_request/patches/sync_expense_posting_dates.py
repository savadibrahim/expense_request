# Copyright (c) 2026, Bantoo and contributors
# License: MIT. See license.txt

"""Sync Expense Entry posting_date from Reference / Clearance Date or Expense Date.

Priority:
1. clearance_date (Reference / Clearance Date) when set
2. required_by (Expense Date) when clearance_date is not available

For submitted entries where posting_date != target date, this script:
1. Cancels the linked Journal Entry (if any)
2. Cancels the Expense Entry
3. Creates an amended copy with the corrected posting_date
4. Submits the amended entry (which recreates the Journal Entry)

Run a dry run first:
    bench --site <site> execute expense_request.patches.sync_expense_posting_dates.execute

Fix all mismatched entries:
    bench --site <site> execute expense_request.patches.sync_expense_posting_dates.execute --kwargs "{'dry_run': False}"

Fix a single entry:
    bench --site <site> execute expense_request.patches.sync_expense_posting_dates.execute --kwargs "{'dry_run': False, 'name': 'EXP-2026-00011'}"
"""

from __future__ import unicode_literals

import frappe
from frappe.utils import cint, getdate


def get_expense_date(value):
	"""Return calendar date from required_by (Expense Date)."""
	if not value:
		return None
	return getdate(str(value).split(" ")[0].split("T")[0])


def get_target_posting_date(entry):
	"""Return target posting_date and the source field used."""
	clearance_date = entry.get("clearance_date") if hasattr(entry, "get") else entry.clearance_date
	if clearance_date:
		return getdate(clearance_date), "clearance_date"

	required_by = entry.get("required_by") if hasattr(entry, "get") else entry.required_by
	expense_date = get_expense_date(required_by)
	if expense_date:
		return expense_date, "required_by"

	return None, None


def execute(dry_run=True, company=None, from_date=None, to_date=None, name=None):
	"""Fix posting_date on submitted Expense Entries."""
	frappe.only_for("System Manager")

	entries = get_mismatched_entries(
		company=company, from_date=from_date, to_date=to_date, name=name
	)
	summary = {"total": len(entries), "fixed": 0, "skipped": 0, "failed": 0, "dry_run": dry_run}

	if not entries:
		frappe.msgprint("No submitted Expense Entries with mismatched posting dates found.")
		return summary

	frappe.msgprint(f"Found {len(entries)} Expense Entries to process.")

	for row in entries:
		entry_name = row.name
		target_date, source = get_target_posting_date(row)
		current_date = getdate(row.posting_date)

		if dry_run:
			print(
				f"[DRY RUN] {entry_name}: posting_date {current_date} -> {target_date} "
				f"(from {source}, clearance_date={row.clearance_date}, required_by={row.required_by})"
			)
			summary["fixed"] += 1
			continue

		try:
			result = fix_expense_entry(entry_name)
			frappe.db.commit()
			print(f"[OK] {entry_name}: {result}")
			if result.startswith("skipped"):
				summary["skipped"] += 1
			else:
				summary["fixed"] += 1
		except Exception:
			frappe.db.rollback()
			summary["failed"] += 1
			frappe.log_error(
				title=f"Failed to sync posting date for {entry_name}",
				message=frappe.get_traceback(),
			)
			print(f"[FAILED] {entry_name}: see Error Log")

	print_summary(summary)
	return summary


def get_mismatched_entries(company=None, from_date=None, to_date=None, name=None):
	"""Return submitted Approved entries where posting_date != target date."""
	filters = {
		"docstatus": 1,
		"status": "Approved",
	}

	if company:
		filters["company"] = company
	if name:
		filters["name"] = name

	entries = frappe.get_all(
		"Expense Entry",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"clearance_date",
			"required_by",
			"set_posting_time",
			"company",
		],
		order_by="posting_date asc",
	)

	mismatched = []
	for entry in entries:
		target_date, _source = get_target_posting_date(entry)
		if not target_date:
			continue

		current_date = getdate(entry.posting_date) if entry.posting_date else None
		if current_date == target_date:
			continue

		if from_date and target_date < getdate(from_date):
			continue
		if to_date and target_date > getdate(to_date):
			continue

		mismatched.append(entry)

	return mismatched


def fix_expense_entry(name):
	"""Cancel, amend, and resubmit with posting_date from clearance or expense date."""
	if frappe.db.exists("Expense Entry", {"amended_from": name, "docstatus": ["!=", 2]}):
		return "skipped (active amendment already exists)"

	doc = frappe.get_doc("Expense Entry", name)
	target_posting_date, source = get_target_posting_date(doc)

	if not target_posting_date:
		return "skipped (no clearance date or expense date)"

	if getdate(doc.posting_date) == target_posting_date:
		return "skipped (already correct)"

	cancel_linked_journal_entries(name)

	doc.reload()
	doc.flags.ignore_permissions = True
	doc.cancel()
	frappe.db.set_value("Expense Entry", doc.name, "status", "Cancelled", update_modified=False)

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

	ensure_posting_date_and_je(amended.name, target_posting_date)

	return f"amended to {amended.name}, posting_date={target_posting_date} (from {source})"


def ensure_posting_date_and_je(expense_entry_name, target_posting_date):
	"""Ensure amended entry and its JE use the target posting_date."""
	target_posting_date = getdate(target_posting_date)
	doc = frappe.get_doc("Expense Entry", expense_entry_name)

	updates = {}
	if getdate(doc.posting_date) != target_posting_date:
		updates["posting_date"] = target_posting_date
	if cint(doc.set_posting_time) != 1:
		updates["set_posting_time"] = 1

	if updates:
		frappe.db.set_value("Expense Entry", expense_entry_name, updates, update_modified=True)
		doc.reload()

	je_name = frappe.db.get_value(
		"Journal Entry", {"bill_no": expense_entry_name, "docstatus": 1}, "name"
	)
	je_posting_date = (
		frappe.db.get_value("Journal Entry", je_name, "posting_date") if je_name else None
	)

	if je_name and getdate(je_posting_date) != target_posting_date:
		cancel_linked_journal_entries(expense_entry_name)
		from expense_request.api import make_journal_entry

		make_journal_entry(doc)


def cancel_linked_journal_entries(expense_entry_name):
	for je_name in frappe.get_all(
		"Journal Entry",
		filters={"bill_no": expense_entry_name, "docstatus": 1},
		pluck="name",
	):
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
