import frappe
from frappe import _
from frappe import utils

# Re-export for older cached clients calling expense_request.api.expense_account_query
from expense_request.queries import expense_account_query  # noqa: F401


"""
TODO

Permissions 
- Settings Checbox - Employee can create Expenses
- Add Employee User Permission
Report

More Features - v2
- Alert Approvers - manual - for pending / draft
- Tax Templates
- Separate Request Document
   - Add approved amount on expense entry - auto filled from requested amount but changeable
- Rename App. Expense Voucher vs Expense Entry
- Tests

- Fix
    - Prevent Making JE's before submission / non-approvers

- Add dependant fields
    - Workflow entries
    - JV type: Expense Entry
    - JV Account Reference Type: Expense Entry
    - Mode of Payment: Petty Cash


DONE
  - Issues Fixed
    - Wire Transfer requires reference date, and minor improvements
    - Approver field vanishing
  
  - Print Format improvements - (Not done: Add signatures)
  - Prevent duplicate entry - done
  - Workflow: Pending Approval, Approved (set-approved by)
  - Creation of JV
  - expense refs
  - Roles:
    - Expense Approver
  - Set authorising party

  Add sections to EE and EE Items
    Section: Accounting Dimensions
    - Project
    - Cost Center

  - Add settings fields to Accounts Settings
    Section: Expense Settings
    - Link: Default Payment Account (Link: Mode of Payment) 
      - Desc: Create a Mode of Payment for expenses and link it to your usual expenditure account like Petty Cash
    - Checkbox: Notify all Approvers
      - Desc: when a expense request is made
    - Checkbox: Create Journals Automatically

Add all the fixtures to the app so that it is fully portable
a. Workflows
b. Accounts Settings Fields
c. Fix minor issues
   - Cant set custom print format as default - without customisation

Enhancements
- Added Cost Center Filters
"""


def setup(expense_entry, method):
    # add expenses up and set the total field
    # add default project and cost center to expense items

    total = 0
    count = 0
    expense_items = []

    
    for detail in expense_entry.expenses:
        total += float(detail.amount)        
        count += 1
        
        if not detail.project and expense_entry.default_project:
            detail.project = expense_entry.default_project
        
        if not detail.cost_center and expense_entry.default_cost_center:
            detail.cost_center = expense_entry.default_cost_center

        expense_items.append(detail)

    expense_entry.expenses = expense_items

    expense_entry.total = total
    expense_entry.quantity = count

    # Recalculate purchase taxes / grand_total before JE (on_update runs after validate).
    if hasattr(expense_entry, "calculate_totals_and_taxes"):
        expense_entry.calculate_totals_and_taxes()

    make_journal_entry(expense_entry)

    


@frappe.whitelist()
def initialise_journal_entry(expense_entry_name):
    # make JE from javascript form Make JE button

    make_journal_entry(
        frappe.get_doc('Expense Entry', expense_entry_name)
    )


def cancel_linked_journal_entries(expense_entry_name):
	"""Cancel submitted Journal Entries linked to an Expense Entry via bill_no."""
	for je_name in frappe.get_all(
		"Journal Entry",
		filters={"bill_no": expense_entry_name, "docstatus": 1},
		pluck="name",
	):
		je = frappe.get_doc("Journal Entry", je_name)
		je.flags.ignore_permissions = True
		je.cancel()


def make_journal_entry(expense_entry):

    if expense_entry.status == "Approved":         

        # check for duplicates (submitted only — cancelled JEs must not block recreate)
        
        if frappe.db.exists(
            {"doctype": "Journal Entry", "bill_no": expense_entry.name, "docstatus": 1}
        ):
            frappe.throw(
                title="Error",
                msg="Journal Entry {} already exists.".format(expense_entry.name)
            )


        # Preparing the JE: convert expense_entry details into je account details

        accounts = []

        for detail in expense_entry.expenses:            

            accounts.append({  
                'debit_in_account_currency': float(detail.amount),
                'user_remark': str(detail.description),
                'account': detail.expense_account,
                'project': detail.project,
                'cost_center': detail.cost_center
            })

        # Debit tax / charge account heads (skip Valuation-only rows)
        for tax in expense_entry.get("taxes") or []:
            if getattr(tax, "category", None) == "Valuation":
                continue
            tax_amount = float(tax.tax_amount or 0)
            if not tax_amount:
                continue
            if tax.add_deduct_tax == "Deduct":
                accounts.append({
                    'credit_in_account_currency': tax_amount,
                    'user_remark': str(tax.description or tax.account_head),
                    'account': tax.account_head,
                    'cost_center': tax.cost_center or expense_entry.default_cost_center,
                    'project': tax.project,
                })
            else:
                accounts.append({
                    'debit_in_account_currency': tax_amount,
                    'user_remark': str(tax.description or tax.account_head),
                    'account': tax.account_head,
                    'cost_center': tax.cost_center or expense_entry.default_cost_center,
                    'project': tax.project,
                })

        # finally add the payment account detail

        pay_account = ""

        if (expense_entry.mode_of_payment != "Cash" and (not 
            expense_entry.payment_reference or not expense_entry.clearance_date)):
            frappe.throw(
                title="Enter Payment Reference",
                msg="Payment Reference and Date are Required for all non-cash payments."
            )
        else:
            expense_entry.clearance_date = ""
            expense_entry.payment_reference = ""


        pay_account = frappe.db.get_value('Mode of Payment Account', {'parent' : expense_entry.mode_of_payment, 'company' : expense_entry.company}, 'default_account')
        if not pay_account or pay_account == "":
            frappe.throw(
                title="Error",
                msg="The selected Mode of Payment has no linked account."
            )

        payment_amount = float(
            expense_entry.grand_total
            if expense_entry.grand_total is not None
            else expense_entry.total
        )

        accounts.append({  
            'credit_in_account_currency': payment_amount,
            'user_remark': str(detail.description),
            'account': pay_account,
            'cost_center': expense_entry.default_cost_center
        })

        # create the journal entry
        je = frappe.get_doc({
            'title': expense_entry.name,
            'doctype': 'Journal Entry',
            'voucher_type': 'Journal Entry',
            'posting_date': expense_entry.posting_date,
            'company': expense_entry.company,
            'accounts': accounts,
            'user_remark': expense_entry.remarks,
            'mode_of_payment': expense_entry.mode_of_payment,
            'cheque_date': expense_entry.clearance_date,
            'reference_date': expense_entry.clearance_date,
            'cheque_no': expense_entry.payment_reference,
            'pay_to_recd_from': expense_entry.payment_to,
            'bill_no': expense_entry.name
        })

        user = frappe.get_doc("User", frappe.session.user)

        full_name = str(user.first_name) + ' ' + str(user.last_name)
        expense_entry.db_set('approved_by', full_name)
        

        je.insert()
        je.submit()