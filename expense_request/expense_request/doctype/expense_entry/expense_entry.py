# -*- coding: utf-8 -*-
# Copyright (c) 2020, Bantoo and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt

from expense_request.api import cancel_linked_journal_entries


class ExpenseEntry(Document):
	def before_insert(self):
		# Keep Edit Posting Date checked on amend so posting_date stays editable.
		if self.amended_from:
			self.set_posting_time = 1

	def validate(self):
		if self.is_new() and self.amended_from:
			self.set_posting_time = 1

		self.set_default_cost_center()
		self.calculate_totals_and_taxes()

	def set_default_cost_center(self):
		"""Use company default cost center (Main) when header cost center is blank."""
		if self.default_cost_center or not self.company:
			return
		self.default_cost_center = frappe.db.get_value("Company", self.company, "cost_center")

	def before_cancel(self):
		# Workflow cancel does not always persist status; enforce explicitly.
		self.status = "Cancelled"

	def on_cancel(self):
		# Amend requires cancel first — cancel linked JE so GL is reversed.
		cancel_linked_journal_entries(self.name)

	def calculate_totals_and_taxes(self):
		"""Sum expense lines, apply Purchase Taxes and Charges, set grand_total."""
		total = 0.0
		count = 0

		for detail in self.get("expenses") or []:
			total += flt(detail.amount)
			count += 1

			if not detail.project and self.default_project:
				detail.project = self.default_project

			if not detail.cost_center and self.default_cost_center:
				detail.cost_center = self.default_cost_center

		self.total = flt(total, self.precision("total"))
		self.quantity = count

		self._calculate_taxes()

	def _calculate_taxes(self):
		net_total = flt(self.total)
		taxes_added = 0.0
		taxes_deducted = 0.0

		for i, tax in enumerate(self.get("taxes") or []):
			tax_amount = self._get_tax_amount(tax, net_total, i)
			tax.tax_amount = flt(tax_amount, tax.precision("tax_amount"))
			tax.tax_amount_after_discount_amount = tax.tax_amount

			# Cumulative row total (net + taxes so far); Valuation-only excluded from running total.
			signed = self._signed_tax_for_total(tax)
			if i == 0:
				tax.total = flt(net_total + signed, tax.precision("total"))
			else:
				prev_total = flt(self.taxes[i - 1].total)
				tax.total = flt(prev_total + signed, tax.precision("total"))

			if tax.category in (None, "", "Total", "Valuation and Total"):
				if tax.add_deduct_tax == "Deduct":
					taxes_deducted += flt(tax.tax_amount)
				else:
					taxes_added += flt(tax.tax_amount)

		self.total_taxes_and_charges = flt(
			taxes_added - taxes_deducted, self.precision("total_taxes_and_charges")
		)
		self.grand_total = flt(
			net_total + self.total_taxes_and_charges, self.precision("grand_total")
		)

	def _get_tax_amount(self, tax, net_total, idx):
		charge_type = tax.charge_type or "Actual"

		if charge_type == "Actual":
			return flt(tax.tax_amount)

		if charge_type == "On Net Total":
			return net_total * flt(tax.rate) / 100.0

		if charge_type == "On Previous Row Amount":
			ref = self._get_tax_row(tax.row_id)
			return flt(ref.tax_amount) * flt(tax.rate) / 100.0

		if charge_type == "On Previous Row Total":
			ref = self._get_tax_row(tax.row_id)
			return flt(ref.total) * flt(tax.rate) / 100.0

		if charge_type == "On Item Quantity":
			return flt(self.quantity) * flt(tax.rate)

		frappe.throw(
			frappe._("Row #{0}: Unsupported charge type {1}").format(idx + 1, charge_type)
		)

	def _get_tax_row(self, row_id):
		row_idx = cint(row_id)
		if not row_idx or row_idx > len(self.taxes):
			frappe.throw(frappe._("Please enter a valid Reference Row # in Purchase Taxes and Charges"))
		return self.taxes[row_idx - 1]

	@staticmethod
	def _signed_tax_for_total(tax):
		if getattr(tax, "category", None) == "Valuation":
			return 0.0
		amount = flt(tax.tax_amount)
		return -amount if tax.add_deduct_tax == "Deduct" else amount
