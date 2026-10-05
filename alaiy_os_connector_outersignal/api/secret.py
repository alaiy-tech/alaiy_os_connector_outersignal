# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""Create a new signing secret from the settings form."""

import secrets

import frappe

SETTINGS = "OuterSignal Connector Settings"


@frappe.whitelist(methods=["POST"])
def generate_secret():
    """
    Store a new random secret and return it once so it can be copied into the
    platform's webhook action. The previous secret stops working immediately.
    """
    frappe.only_for("System Manager")
    secret = secrets.token_hex(32)
    doc = frappe.get_single(SETTINGS)
    doc.outersignal_webhook_secret = secret
    doc.save()
    return secret
