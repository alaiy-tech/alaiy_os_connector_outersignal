# Alaiy OS Connector: OuterSignal

Receives enriched customer profiles from OuterSignal and stores them on the native
`Customer`. It is receive-only: OuterSignal reads orders from the connected store
itself, so nothing is sent to it from Alaiy OS.

## Flow

1. A playbook in OuterSignal (segment: All Customers, action: Webhook, trigger: Live Sync)
   posts a JSON payload to the receiver.
2. The receiver checks the `X-Signature-256` HMAC-SHA256 header against the Signing Secret.
3. The delivery is matched to a Customer by the store's order name
   (`Sales Order.sh_shopify_order_name`), narrowed by email when several customers share
   that name, then by email alone. An ambiguous delivery is logged as skipped, never guessed.
4. The profile is written to the Customer's `osg_*` fields; the full profile is kept as JSON
   in `osg_profile_json`. A delivery older than the stored `osg_research_updated_at` is ignored.

Every delivery writes one `OuterSignal Sync Log` row (status, order name, reason). No
personal data is written to the log.

## Setup

```bash
bench get-app alaiy_os_connector_outersignal <repo>
bench install-app alaiy_os_connector_outersignal
bench --site <site> migrate
```

Open **OuterSignal Connector Settings** and enable it. This creates the Customer fields and a
Signing Secret (reveal it in the form, or use Actions > Generate Secret for a new one). Use the shown Webhook URL and the same secret in the playbook's webhook
action, with this payload template:

```json
{
  "event": "segment_entered",
  "triggered_at": "{{triggered_at}}",
  "research_updated_at": "{{research_updated_at}}",
  "profile": {
    "name": "{{profile.name}}", "email": "{{profile.email}}", "phone": "{{profile.phone}}",
    "gender": "{{profile.gender}}", "age": "{{profile.age}}", "birth_date": "{{profile.birth_date}}",
    "relationship_status": "{{profile.relationship_status}}", "persona": "{{profile.persona}}",
    "biography": "{{profile.biography}}", "city": "{{profile.city}}", "state": "{{profile.state}}",
    "country": "{{profile.country}}", "job_title": "{{profile.job_title}}",
    "company_name": "{{profile.company_name}}",
    "education_institution": "{{profile.education_institution}}",
    "education_degree": "{{profile.education_degree}}",
    "property_value": "{{profile.property_value}}",
    "social_profiles": "{{profile.social_profiles}}", "lists": "{{profile.lists}}"
  },
  "order": {
    "name": "{{order.name}}", "count": "{{order.count}}",
    "total_spent": "{{order.total_spent}}", "avg_value": "{{order.avg_value}}"
  },
  "segment": { "name": "{{segment.name}}" }
}
```

All values arrive as strings; list fields arrive as JSON text. `order.email` is not rendered
by the platform, so matching uses `profile.email`.

## Profiles, repeat orders and the customer export

Every delivery and every row of the customer export is kept as an **OuterSignal
Profile**, one per person (keyed by email, or by the Shopify customer id when there is
no email), with every column of the export as its own field. A person is kept whether
or not they are a Customer in Alaiy OS.

One person can appear many times, and each case is handled:

- **Several orders on the file** (one row per order): the rows fold into one profile.
  Each order is listed on it, the order counters keep the largest value seen, a value a
  row lacks never erases one already stored, and a stored value is replaced only by a
  more recent order.
- **Several deliveries** (one per new order): the same profile is updated, the newest
  delivery wins, and an older dated one leaves the profile alone but still records its
  order.
- **Several Customer records for one person** (Alaiy OS may hold one per order): the
  person is looked up by Shopify customer id, by email and by each of their orders, and
  the profile is copied onto every Customer found.
- **A person who has no Customer yet:** the profile waits, and an hourly job links it
  when the Customer appears.
- **The same file twice:** nothing changes.

To load the customers that the webhook has not delivered (it fires on a new order),
export the customers as a CSV from the platform's dashboard and use **Actions > Import
Profiles (CSV)** on the settings form. The totals are written as one `OuterSignal Sync
Log` row (type `import`), and the file, which holds personal data, is deleted as soon
as the import has finished.

## Tests

```bash
python -m unittest tests.test_parse tests.test_profile_store tests.test_csv_import   # from the inner app directory, no Frappe needed
```

The Customer matching and storage (`outersignal/profile.py`) and the endpoint
(`api/webhook.py`) need a bench to exercise.
