# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe.model.document import Document


class OuterSignalConnectorSettings(Document):
    def validate(self):
        # old_enabled is the last-committed DB value, so this comparison has
        # to run before the save overwrites it. Heavy setup runs only on the
        # 0 -> 1 transition, not on every save.
        old_enabled = frappe.db.get_single_value(
            "OuterSignal Connector Settings", "is_enabled"
        ) or 0
        self.flags.outersignal_just_enabled = bool(self.is_enabled and not old_enabled)
        self._ensure_secret()
        self._sync_registry_is_enabled()

    def _ensure_secret(self):
        # The receiver rejects every delivery without a secret, so enabling with
        # none set creates one. A typed or already stored value is left alone.
        if (
            self.is_enabled
            and not self.outersignal_webhook_secret
            and not self.get_password("outersignal_webhook_secret", raise_exception=False)
        ):
            self.outersignal_webhook_secret = secrets.token_hex(32)

    def on_update(self):
        if self.flags.outersignal_just_enabled:
            from alaiy_os_connector_outersignal.setup.install import setup_custom_fields
            setup_custom_fields()

    def _sync_registry_is_enabled(self):
        if frappe.db.exists("OS Connector Registry", "outersignal"):
            frappe.db.set_value(
                "OS Connector Registry", "outersignal", "is_enabled", self.is_enabled
            )
