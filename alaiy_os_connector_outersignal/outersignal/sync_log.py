# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""OuterSignal Sync Log rows. No personal data goes in them."""

import frappe
from frappe.utils import now_datetime


def record(status, order_name=None, error=None, updated=0, *, sync_type="webhook", trigger="webhook",
           processed=1, failed=None, message=None):
    """One row: a webhook delivery by default, or the totals of a file import."""
    log = frappe.new_doc("OuterSignal Sync Log")
    log.sync_type = sync_type
    log.trigger = trigger
    log.status = status
    log.started_at = log.finished_at = now_datetime()
    log.items_processed = processed
    log.items_updated = updated
    log.items_failed = (1 if status == "failed" else 0) if failed is None else failed
    log.error_message = (error or "")[:2000]
    log.log_messages = message or (f"order {order_name}" if order_name else "")
    log.insert(ignore_permissions=True)
    return log.name
