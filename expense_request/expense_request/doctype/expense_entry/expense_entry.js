// Copyright (c) 2020, Bantoo and contributors
// For license information, please see license.txt

frappe.provide("expense_entry.expense_entry");

function update_totals(frm, cdt, cdn){
	var items = locals[cdt][cdn];
    var total = 0;
    var quantity = 0;
    frm.doc.expenses.forEach(
        function(items) { 
            total += items.amount;
            quantity +=1;
        });
    frm.set_value("total", total);
    refresh_field("total");
    frm.set_value("quantity", quantity);
    refresh_field("quantity");
}

frappe.ui.form.on('Expense Entry Item', {
	amount: function(frm, cdt, cdn) {
        update_totals(frm, cdt, cdn);
	},
	expenses_remove: function(frm, cdt, cdn){
        update_totals(frm, cdt, cdn);
	},
    expenses_add: function(frm, cdt, cdn){
        var d = locals[cdt][cdn];
        
        if((d.cost_center === "" || typeof d.cost_center == 'undefined')) { 

            if (cur_frm.doc.default_cost_center != "" || typeof cur_frm.doc.default_cost_center != 'undefined') {
                
                d.cost_center = cur_frm.doc.default_cost_center; 
                cur_frm.refresh_field("expenses");
            }
        }
	}
	
});


frappe.ui.form.on('Expense Entry', {
    before_save: function(frm) { 

        $.each(frm.doc.expenses, function(i, d) { 
            let label = "";
            
            if((d.cost_center === "" || typeof d.cost_center == 'undefined')) { 
                
                if (cur_frm.doc.default_cost_center === "" || typeof cur_frm.doc.default_cost_center == 'undefined') {
                    frappe.validated = false;
                    frappe.msgprint("Set a Default Cost Center or specify the Cost Center for expense <strong>No. " 
                                    + (i + 1) + "</strong>.");
                    return false;
                }
                else {
                    d.cost_center = cur_frm.doc.default_cost_center; 
                }
            }
        }); 
        
    },
    refresh(frm) {
        show_accounting_ledger(frm);
	},
	onload(frm) {
        set_queries(frm);
	},
	company(frm) {
        set_queries(frm);
        unset_default_cost_center(frm);
	}
});


function set_queries(frm) {
    frm.set_query("expense_account", 'expenses', () => {
        return {
            query: "expense_request.queries.expense_account_query",
            filters: {
                company: frm.doc.company
            }
        }
    });
    frm.set_query("cost_center", 'expenses', () => {
        return {
            filters: [
                ["Cost Center", "is_group", "=", "0"],
                ["Cost Center", "company", "=", frm.doc.company]
            ]
        }
    });
    frm.set_query("default_cost_center", () => {
        return {
            filters: [
                ["Cost Center", "is_group", "=", "0"],
                ["Cost Center", "company", "=", frm.doc.company]
            ]
        }
    });
}

function unset_default_cost_center(frm) {
    frm.set_value("default_cost_center", '');
}

function show_accounting_ledger(frm) {
    if (!(frm.doc.docstatus > 0)) {
        return;
    }

    frappe.db
        .get_value("Journal Entry", { bill_no: frm.doc.name }, ["name", "finance_book", "posting_date"])
        .then((r) => {
            const je = r && r.message;
            if (!je || !je.name) {
                return;
            }

            frm.add_custom_button(
                __("Accounting Ledger"),
                function () {
                    // Match Journal Entry / Payment Entry View → Ledger options.
                    // Expense Entry posts via JE, so filter GL by that voucher.
                    const route_options = {
                        voucher_no: je.name,
                        from_date: je.posting_date || frm.doc.posting_date,
                        to_date: frappe.datetime.get_today(),
                        company: frm.doc.company,
                        categorize_by: "",
                        show_cancelled_entries: frm.doc.docstatus === 2,
                        include_default_book_entries: 1,
                        ignore_prepared_report: true,
                    };
                    if (je.finance_book) {
                        route_options.finance_book = je.finance_book;
                    }
                    frappe.route_options = route_options;
                    frappe.set_route("query-report", "General Ledger");
                },
                __("View")
            );

            frm.add_custom_button(
                __("Journal Entry"),
                function () {
                    frappe.set_route("Form", "Journal Entry", je.name);
                },
                __("View")
            );
        });
}

