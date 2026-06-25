import os

import frappe
from frappe.modules.import_file import import_file_by_path

EXPENSE_ENTRY_DOCTYPE = "Expense Entry"
EXPENSE_ENTRY_LABEL = "Bills & Expenses"
EXPENSES_REGISTER_REPORT = "Expenses Register"
BILLS_AND_EXPENSES_WORKSPACE = "Bills and Expenses"
LEGACY_BILLS_AND_EXPENSES_WORKSPACE = "Bills & Expenses"


def after_install():
	setup_bills_and_expenses_workspace()


def after_migrate():
	setup_bills_and_expenses_workspace()


def before_uninstall():
	remove_bills_and_expenses_workspace()


def setup_bills_and_expenses_workspace():
	_cleanup_legacy_workspace_names()
	_import_bills_and_expenses_assets()
	_remove_legacy_accounting_links()
	_fix_stale_workspace_links()
	_ensure_desktop_icon_under_accounting()
	frappe.clear_cache()


def _fix_stale_workspace_links():
	frappe.db.sql(
		"""
		UPDATE `tabWorkspace Sidebar Item`
		SET link_to = %s
		WHERE link_to = %s AND link_type = 'Workspace'
		""",
		(BILLS_AND_EXPENSES_WORKSPACE, LEGACY_BILLS_AND_EXPENSES_WORKSPACE),
	)


def remove_bills_and_expenses_workspace():
	_remove_legacy_accounting_links()
	_cleanup_legacy_workspace_names()


def _cleanup_legacy_workspace_names():
	for doctype in ("Workspace", "Workspace Sidebar", "Desktop Icon"):
		if frappe.db.exists(doctype, LEGACY_BILLS_AND_EXPENSES_WORKSPACE):
			frappe.delete_doc(doctype, LEGACY_BILLS_AND_EXPENSES_WORKSPACE, force=True)


def _import_bills_and_expenses_assets():
	app_path = frappe.get_app_path("expense_request")
	asset_paths = [
		os.path.join(app_path, "workspace_sidebar", "bills_and_expenses.json"),
		os.path.join(app_path, "desktop_icon", "bills_and_expenses.json"),
		os.path.join(
			app_path,
			"expense_request",
			"workspace",
			"bills_and_expenses",
			"bills_and_expenses.json",
		),
	]

	for path in asset_paths:
		if os.path.exists(path):
			import_file_by_path(path, force=True)


def _remove_legacy_accounting_links():
	_remove_workspace_sidebar_item("Payments", EXPENSE_ENTRY_DOCTYPE, "DocType")
	_remove_workspace_sidebar_item("Financial Reports", EXPENSES_REGISTER_REPORT, "Report")
	_remove_workspace_link("Invoicing", EXPENSE_ENTRY_DOCTYPE, "DocType")
	_remove_workspace_link("Financial Reports", EXPENSES_REGISTER_REPORT, "Report")


def _ensure_desktop_icon_under_accounting():
	if not frappe.db.exists("Desktop Icon", BILLS_AND_EXPENSES_WORKSPACE):
		return

	updates = {}
	if frappe.db.get_value("Desktop Icon", BILLS_AND_EXPENSES_WORKSPACE, "parent_icon") != "Accounting":
		updates["parent_icon"] = "Accounting"
	if frappe.db.get_value("Desktop Icon", BILLS_AND_EXPENSES_WORKSPACE, "label") != EXPENSE_ENTRY_LABEL:
		updates["label"] = EXPENSE_ENTRY_LABEL
	if frappe.db.get_value("Desktop Icon", BILLS_AND_EXPENSES_WORKSPACE, "link_to") != BILLS_AND_EXPENSES_WORKSPACE:
		updates["link_to"] = BILLS_AND_EXPENSES_WORKSPACE

	if updates:
		frappe.db.set_value("Desktop Icon", BILLS_AND_EXPENSES_WORKSPACE, updates, update_modified=False)

	if frappe.db.exists("Workspace Sidebar", BILLS_AND_EXPENSES_WORKSPACE):
		if frappe.db.get_value("Workspace Sidebar", BILLS_AND_EXPENSES_WORKSPACE, "title") != EXPENSE_ENTRY_LABEL:
			frappe.db.set_value(
				"Workspace Sidebar",
				BILLS_AND_EXPENSES_WORKSPACE,
				"title",
				EXPENSE_ENTRY_LABEL,
				update_modified=False,
			)


def _remove_workspace_sidebar_item(sidebar_name, link_to, link_type):
	if not frappe.db.exists("Workspace Sidebar", sidebar_name):
		return

	sidebar = frappe.get_doc("Workspace Sidebar", sidebar_name)
	rows = [
		item.as_dict()
		for item in sidebar.items
		if not (item.link_to == link_to and item.link_type == link_type)
	]
	if len(rows) == len(sidebar.items):
		return

	sidebar.set("items", rows)
	for idx, item in enumerate(sidebar.items, start=1):
		item.idx = idx
	sidebar.save(ignore_permissions=True)


def _remove_workspace_link(workspace_name, link_to, link_type):
	if not frappe.db.exists("Workspace", workspace_name):
		return

	workspace = frappe.get_doc("Workspace", workspace_name)
	rows = [
		link.as_dict()
		for link in workspace.links
		if not (link.link_to == link_to and link.link_type == link_type)
	]
	if len(rows) == len(workspace.links):
		return

	workspace.set("links", rows)
	workspace.save(ignore_permissions=True)
