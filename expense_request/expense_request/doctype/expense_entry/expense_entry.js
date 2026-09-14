// Copyright (c) 2020, Bantoo and contributors
// For license information, please see license.txt

frappe.provide("expense_entry.expense_entry");

function update_totals(frm) {
	let total = 0;
	let quantity = 0;
	(frm.doc.expenses || []).forEach(function (row) {
		total += flt(row.amount);
		quantity += 1;
	});
	frm.set_value("total", total);
	frm.set_value("quantity", quantity);
	calculate_taxes(frm);
}

function calculate_taxes(frm) {
	const net_total = flt(frm.doc.total);
	let taxes_added = 0;
	let taxes_deducted = 0;
	const taxes = frm.doc.taxes || [];

	taxes.forEach(function (tax, i) {
		let tax_amount = 0;
		const charge_type = tax.charge_type || "Actual";

		if (charge_type === "Actual") {
			tax_amount = flt(tax.tax_amount);
		} else if (charge_type === "On Net Total") {
			tax_amount = (net_total * flt(tax.rate)) / 100;
		} else if (charge_type === "On Previous Row Amount") {
			const ref = taxes[cint(tax.row_id) - 1];
			tax_amount = ref ? (flt(ref.tax_amount) * flt(tax.rate)) / 100 : 0;
		} else if (charge_type === "On Previous Row Total") {
			const ref = taxes[cint(tax.row_id) - 1];
			tax_amount = ref ? (flt(ref.total) * flt(tax.rate)) / 100 : 0;
		} else if (charge_type === "On Item Quantity") {
			tax_amount = flt(frm.doc.quantity) * flt(tax.rate);
		}

		tax.tax_amount = flt(tax_amount, precision("tax_amount", tax));
		tax.tax_amount_after_discount_amount = tax.tax_amount;

		let signed = 0;
		if (tax.category !== "Valuation") {
			signed = tax.add_deduct_tax === "Deduct" ? -flt(tax.tax_amount) : flt(tax.tax_amount);
		}

		if (i === 0) {
			tax.total = flt(net_total + signed, precision("total", tax));
		} else {
			tax.total = flt(flt(taxes[i - 1].total) + signed, precision("total", tax));
		}

		if (!tax.category || tax.category === "Total" || tax.category === "Valuation and Total") {
			if (tax.add_deduct_tax === "Deduct") {
				taxes_deducted += flt(tax.tax_amount);
			} else {
				taxes_added += flt(tax.tax_amount);
			}
		}
	});

	frm.set_value(
		"total_taxes_and_charges",
		flt(taxes_added - taxes_deducted, precision("total_taxes_and_charges", frm.doc))
	);
	frm.set_value(
		"grand_total",
		flt(net_total + flt(frm.doc.total_taxes_and_charges), precision("grand_total", frm.doc))
	);
	frm.refresh_field("taxes");
}

function get_taxes_from_template(frm) {
	if (!frm.doc.taxes_and_charges) {
		return;
	}

	return frappe.call({
		method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
		args: {
			master_doctype: "Purchase Taxes and Charges Template",
			master_name: frm.doc.taxes_and_charges,
		},
		callback: function (r) {
			if (!r.message) {
				return;
			}
			frm.set_value("taxes", r.message).then(() => {
				calculate_taxes(frm);
			});
		},
	});
}

frappe.ui.form.on("Expense Entry Item", {
	amount: function (frm) {
		update_totals(frm);
	},
	expenses_remove: function (frm) {
		update_totals(frm);
	},
	expenses_add: function (frm, cdt, cdn) {
		var d = locals[cdt][cdn];

		if (d.cost_center === "" || typeof d.cost_center == "undefined") {
			if (
				cur_frm.doc.default_cost_center != "" ||
				typeof cur_frm.doc.default_cost_center != "undefined"
			) {
				d.cost_center = cur_frm.doc.default_cost_center;
				cur_frm.refresh_field("expenses");
			}
		}
		update_totals(frm);
	},
});

frappe.ui.form.on("Purchase Taxes and Charges", {
	taxes_add: function (frm) {
		calculate_taxes(frm);
	},
	taxes_remove: function (frm) {
		calculate_taxes(frm);
	},
	charge_type: function (frm) {
		calculate_taxes(frm);
	},
	row_id: function (frm) {
		calculate_taxes(frm);
	},
	rate: function (frm) {
		calculate_taxes(frm);
	},
	tax_amount: function (frm) {
		calculate_taxes(frm);
	},
	add_deduct_tax: function (frm) {
		calculate_taxes(frm);
	},
	category: function (frm) {
		calculate_taxes(frm);
	},
	account_head: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.account_head && !row.description) {
			frappe.model.set_value(cdt, cdn, "description", row.account_head);
		}
	},
});

frappe.ui.form.on("Expense Entry", {
	before_save: function (frm) {
		$.each(frm.doc.expenses, function (i, d) {
			if (d.cost_center === "" || typeof d.cost_center == "undefined") {
				if (
					cur_frm.doc.default_cost_center === "" ||
					typeof cur_frm.doc.default_cost_center == "undefined"
				) {
					frappe.validated = false;
					frappe.msgprint(
						"Set a Default Cost Center or specify the Cost Center for expense <strong>No. " +
							(i + 1) +
							"</strong>."
					);
					return false;
				} else {
					d.cost_center = cur_frm.doc.default_cost_center;
				}
			}
		});
		calculate_taxes(frm);
	},
	refresh(frm) {
		enable_edit_posting_date_on_amend(frm);
		show_accounting_ledger(frm);
	},
	onload(frm) {
		enable_edit_posting_date_on_amend(frm);
		set_queries(frm);
		if (!frm.doc.grand_total && frm.doc.total) {
			calculate_taxes(frm);
		}
		if (frm.is_new()) {
			set_default_cost_center_from_company(frm);
		}
	},
	company(frm) {
		set_queries(frm);
		set_default_cost_center_from_company(frm, true);
	},
	taxes_and_charges(frm) {
		if (!frm.doc.taxes_and_charges) {
			frm.clear_table("taxes");
			frm.refresh_field("taxes");
			calculate_taxes(frm);
			return;
		}
		get_taxes_from_template(frm);
	},
});

function enable_edit_posting_date_on_amend(frm) {
	if (!(frm.is_new() && frm.doc.amended_from)) {
		return;
	}
	if (cint(frm.doc.set_posting_time) === 1) {
		return;
	}
	frm.set_value("set_posting_time", 1);
}

function set_default_cost_center_from_company(frm, force) {
	if (!frm.doc.company) {
		if (force) {
			frm.set_value("default_cost_center", "");
		}
		return;
	}
	if (!force && frm.doc.default_cost_center) {
		return;
	}
	frappe.db.get_value("Company", frm.doc.company, "cost_center").then((r) => {
		const cc = r && r.message && r.message.cost_center;
		if (cc) {
			frm.set_value("default_cost_center", cc);
		} else if (force) {
			frm.set_value("default_cost_center", "");
		}
	});
}

function set_queries(frm) {
	frm.set_query("expense_account", "expenses", () => {
		return {
			query: "expense_request.queries.expense_account_query",
			filters: {
				company: frm.doc.company,
			},
		};
	});
	frm.set_query("cost_center", "expenses", () => {
		return {
			filters: [
				["Cost Center", "is_group", "=", "0"],
				["Cost Center", "company", "=", frm.doc.company],
			],
		};
	});
	frm.set_query("default_cost_center", () => {
		return {
			filters: [
				["Cost Center", "is_group", "=", "0"],
				["Cost Center", "company", "=", frm.doc.company],
			],
		};
	});
	frm.set_query("taxes_and_charges", () => {
		return {
			filters: {
				company: frm.doc.company,
			},
		};
	});
	frm.set_query("account_head", "taxes", () => {
		return {
			filters: {
				company: frm.doc.company,
				is_group: 0,
			},
		};
	});
	frm.set_query("cost_center", "taxes", () => {
		return {
			filters: [
				["Cost Center", "is_group", "=", "0"],
				["Cost Center", "company", "=", frm.doc.company],
			],
		};
	});
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
