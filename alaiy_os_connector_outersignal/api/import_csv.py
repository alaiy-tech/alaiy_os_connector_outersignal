# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""Start the import of an uploaded customer export (see outersignal/csv_import.py)."""

import frappe
from frappe import _

SETTINGS = "OuterSignal Connector Settings"


@frappe.whitelist(methods=["POST"])
def start_import(file_url):
    frappe.only_for("System Manager")
    if not frappe.db.get_single_value(SETTINGS, "is_enabled") or not frappe.get_meta("Customer").has_field("osg_age"):
        frappe.throw(_("Enable OuterSignal first; enabling it creates the Customer fields the profiles are stored in."))

    file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not file_name:
        frappe.throw(_("The uploaded file was not found."))

    frappe.enqueue(
        "alaiy_os_connector_outersignal.outersignal.csv_import.run_import",
        queue="long",
        timeout=1800,
        file_name=file_name,
    )
    return {"queued": True}
