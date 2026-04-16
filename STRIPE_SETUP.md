# Stripe Setup — CRM Backend

## 1. Create Restricted API Key (RAK)

Go to **Stripe Dashboard → Developers → API Keys → Create restricted key**.

- **Name:** CRM Backend
- **Permissions:**

| Resource | Permission |
|---|---|
| Checkout Sessions | Write |
| Customers | Write |
| Invoices | Write |
| Invoice Items | Write |
| Payment Intents | Write |
| Subscriptions | Write |
| Prices | Read |
| Products | Read |
| Charges | Read |
| Events | Read |

**Why RAK over secret key:** If the key leaks, damage is limited to these exact resources. A full secret key grants unrestricted access to your Stripe account.

**Note:** Publishable key is not needed — the frontend does not load Stripe.js.

Copy the key (starts with `rk_live_` or `rk_test_`).

---

## 2. Register Webhook Endpoint

Go to **Stripe Dashboard → Developers → Webhooks → Add endpoint**.

- **URL:** `https://backend-production-29c6.up.railway.app/api/payments/webhook`
- **Events to subscribe:**
  - `checkout.session.completed`
  - `checkout.session.async_payment_succeeded`
  - `checkout.session.async_payment_failed`
  - `payment_intent.succeeded`
  - `payment_intent.payment_failed`
  - `charge.refunded`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.paid`
  - `invoice.payment_failed`
  - `invoice.sent`
  - `setup_intent.succeeded`

After saving, click **Reveal signing secret** and copy it (starts with `whsec_`).

---

## 3. Set Railway Environment Variables

In **Railway Dashboard → backend service → Variables**, add:

| Variable | Value |
|---|---|
| `STRIPE_SECRET_KEY` | RAK from step 1 (`rk_live_...` or `rk_test_...`) |
| `STRIPE_PUBLISHABLE_KEY` | Publishable key from Dashboard (for future use) |
| `STRIPE_WEBHOOK_SECRET` | Signing secret from step 2 (`whsec_...`) |

Railway will redeploy automatically after saving variables.

---

## 4. Stripe Dashboard Branding (optional)

**Settings → Branding** — upload Link Creative logo, set business name and colors. Affects hosted invoices and checkout pages.

---

## 5. Testing

Do **all steps above in TEST mode first** (toggle at top-left of Stripe Dashboard).

**Test cards:**
- `4242 4242 4242 4242` — success
- `4000 0000 0000 0002` — card declined

**Test ACH bank transfer:**
- Routing: `110000000`
- Account: `000123456789`

Confirm test invoices send and webhooks appear in **Developers → Webhooks → [your endpoint] → Recent deliveries** before switching to live keys.

**Switch to live keys** by repeating steps 1–3 with live mode active in the Stripe Dashboard.
