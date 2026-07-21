# -*- coding: utf-8 -*-
# Copyright (c) 2020, Bantoo and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from frappe.model.document import Document


class ExpenseEntry(Document):
	def before_cancel(self):
		# Workflow cancel does not always persist status; enforce explicitly.
		self.status = "Cancelled"
