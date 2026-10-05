frappe.ui.form.on("OuterSignal Connector Settings", {
  refresh(frm) {
    frm.page.set_title(__("OuterSignal Settings"));

    // Mount the shared Alaiy OS connector status card + password reveal.
    alaiy_os.connector_card.mount(frm, "outersignal");
    alaiy_os.connector_card.setup_password_reveal(
      frm,
      "outersignal_webhook_secret",
      "outersignal",
    );

    // Display only; assigning directly keeps the form from turning dirty.
    frm.doc.outersignal_webhook_url = `${window.location.origin}/api/method/alaiy_os_connector_outersignal.api.webhook.receive`;
    frm.refresh_field("outersignal_webhook_url");

    frm.add_custom_button(
      __("Generate Secret"),
      () => {
        frappe.confirm(
          __(
            "This replaces the current secret. Deliveries stop being accepted until the new value is pasted into the webhook action. Continue?",
          ),
          () => {
            frappe.call({
              method: "alaiy_os_connector_outersignal.api.secret.generate_secret",
              callback(r) {
                if (!r.message) return;
                frappe.msgprint({
                  title: __("New Signing Secret"),
                  message: `<p>${__("Copy it now; it is not shown again here.")}</p><p><code style="word-break:break-all">${frappe.utils.escape_html(r.message)}</code></p>`,
                });
                frm.reload_doc();
              },
            });
          },
        );
      },
      __("Actions"),
    );

    frm.add_custom_button(
      __("Import Profiles (CSV)"),
      () => {
        new frappe.ui.FileUploader({
          doctype: frm.doctype,
          docname: frm.docname,
          folder: "Home/Attachments",
          make_attachments_public: false,
          allow_multiple: false,
          restrictions: { allowed_file_types: [".csv"] },
          on_success(file_doc) {
            frappe.call({
              method: "alaiy_os_connector_outersignal.api.import_csv.start_import",
              args: { file_url: file_doc.file_url },
              callback() {
                frappe.show_alert(
                  {
                    message: __("Import queued. The totals appear in OuterSignal Logs when it finishes."),
                    indicator: "blue",
                  },
                  8,
                );
              },
            });
          },
        });
      },
      __("Actions"),
    );

    frm.add_custom_button(
      __("Check Setup"),
      () => {
        frappe.call({
          // Through the registry wrapper so the result also updates the
          // Connector Status card at the top of this form.
          method: "alaiy_os.api.connectors.test_connector",
          args: { connector_id: "outersignal" },
          callback(r) {
            const res = r.message || {};
            frappe.show_alert(
              {
                message:
                  res.message ||
                  (res.success ? __("Ready") : __("Not ready")),
                indicator: res.success ? "green" : "red",
              },
              res.success ? 5 : 7,
            );
            frm.reload_doc();
          },
        });
      },
      __("Actions"),
    );
  },
});
