# -*- coding: utf-8 -*-
# Copyright (c) 2020, Bantoo and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from frappe.model.document import Document

from expense_request.api import cancel_linked_journal_entries


class ExpenseEntry(Document):
    def before_insert(self):
        # Keep Edit Posting Date checked on amend so posting_date stays editable.
        if self.amended_from:
            self.set_posting_time = 1

    def validate(self):
        if self.is_new() and self.amended_from:
            self.set_posting_time = 1

    def before_cancel(self):
        # Workflow cancel does not always persist status; enforce explicitly.
        self.status = "Cancelled"

    def on_cancel(self):
        # Amend requires cancel first — cancel linked JE so GL is reversed.
        cancel_linked_journal_entries(self.name)
