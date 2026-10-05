app_name = "alaiy_os_connector_outersignal"
app_title = "Alaiy Os Connector OuterSignal"
app_publisher = "Alaiy"
app_description = "OuterSignal customer intelligence connector for Alaiy OS"
app_email = "mail@alaiy.com"
app_license = "agpl-3.0"

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
# Every Alaiy OS connector runs on top of alaiy_os (registry, workspace,
# connector card) and erpnext (Customer, Sales Order, ...).
required_apps = ["alaiy_os", "erpnext"]

# ---------------------------------------------------------------------------
# Installation / migration
# ---------------------------------------------------------------------------
# after_install runs once on `bench install-app`; after_migrate runs on every
# `bench migrate`. sync_connector_registry() (re)registers this connector in
# alaiy_os's OS Connector Registry and is idempotent, so it is safe on migrate.
after_install = [
    "alaiy_os_connector_outersignal.setup.install.after_install"
]

after_migrate = [
    "alaiy_os_connector_outersignal.setup.install.sync_connector_registry"
]

# ---------------------------------------------------------------------------
# Alaiy OS sidebar
# ---------------------------------------------------------------------------
# Register this connector's Sync Log under the Alaiy OS "Logs" sidebar section.
# alaiy_os reads this hook in create_or_update_workspace_sidebar().
alaiy_os_sidebar_log_items = [
    {
        "link_type": "DocType",
        "link_to": "OuterSignal Sync Log",
        "label": "OuterSignal Logs",
        "icon": "activity",
    }
]
