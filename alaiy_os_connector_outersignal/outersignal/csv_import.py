# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Load the platform's customer export (a CSV file) onto the Customers.

Each row goes through the same code as a webhook delivery: it is kept as a profile
record whether or not the person is a Customer here, and copied onto the Customer
when exactly one matches. Running the same file twice changes nothing. The file holds
personal data, so it is deleted as soon as the import has finished.
"""

import csv
import io

import frappe

from alaiy_os_connector_outersignal.outersignal import profile, sync_log
from alaiy_os_connector_outersignal.outersignal.parse import normalize_csv_row

_COMMIT_EVERY = 200


def import_rows(rows):
    """Keep every row as a profile record and copy it onto every Customer the person
    is found under. One person appears on several rows when they placed several orders:
    each row adds its order to the same profile and fills in what the others lacked."""
    counts = {"rows": 0, "customers": 0, "orders": 0, "linked": 0, "updated": 0, "failed": 0}
    people = set()
    linked = set()
    for row in rows:
        counts["rows"] += 1
        data = normalize_csv_row(row)
        key = profile.profile_key(data)
        if not key:
            continue
        people.add(key)
        try:
            name, customers, updated = profile.process(data, "import")
            counts["orders"] += 1 if data["order_name"] else 0
            if customers:
                linked.add(key)
            counts["updated"] += updated
        except Exception:
            frappe.db.rollback()
            counts["failed"] += 1
            frappe.log_error(title="OuterSignal import: a row could not be stored", message=frappe.get_traceback())
        if counts["rows"] % _COMMIT_EVERY == 0:
            frappe.db.commit()
    frappe.db.commit()
    counts["customers"] = len(people)
    counts["linked"] = len(linked)
    return counts


def run_import(file_name):
    """Background job: read the uploaded file, import it, log the totals, delete the file."""
    status, error, counts = "success", None, None
    try:
        content = frappe.get_doc("File", file_name).get_content()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        counts = import_rows(csv.DictReader(io.StringIO(content, newline="")))
        if counts["failed"]:
            status = "failed"
    except Exception:
        status, error = "failed", frappe.get_traceback()
        frappe.db.rollback()
    finally:
        # The upload is a copy of customer data; nothing needs it after this.
        frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)

    message = (
        "file import: " + ", ".join(f"{k} {v}" for k, v in counts.items()) if counts else "file import did not finish"
    )
    sync_log.record(
        status, error=error, sync_type="import", trigger="manual",
        processed=counts["customers"] if counts else 0,
        updated=counts["updated"] if counts else 0,
        failed=(counts["failed"] if counts else 1),
        message=message,
    )
    frappe.db.commit()
