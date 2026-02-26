# Dubai Ejari Management

Odoo 19 module for end-to-end **Ejari** lifecycle management for Dubai rental properties. Multi-company aware and compatible with Odoo Enterprise.

## Features

- **Ejari records** linked to properties (product.template) with tenant, landlord, dates, and status workflow
- **One active Ejari per property** enforced by constraint; renewal links (renewal_of / renewed_to)
- **Renewal wizard** to create a new Ejari from an existing one with default dates and optional attachment copy
- **Expiry tracking**: daily cron marks records as *Expiring Soon* or *Expired*, creates activities for Ejari Managers, optional email to tenant
- **Product integration**: smart button, Ejari tab, status badges (Active / Expiring / Expired), and actions for **Create Ejari** / **Renew Ejari** (for Catalog Dashboard)
- **Security**: Ejari User (read/create) and Ejari Manager (full); record rules for multi-company

## Installation

1. Copy `dubai_ejari_management` into your addons path (e.g. `custom_addons/`).
2. Restart Odoo and update the app list.
3. Install **Dubai Ejari Management** (depends: base, mail, product).

## Configuration

1. **Companies**: Settings → Companies → [Your company] → **Ejari Settings** tab.  
   Set **Ejari Expiry Warning (Days)** (default: 30).
2. **Access**: Assign users to **Ejari User** or **Ejari Manager** (Settings → Users & Companies → Users → Access Rights, or via the group in the user form).

## Usage

1. **Create Ejari**  
   From a product (property/unit): use the **Ejari** smart button → New, or **Create Ejari** from your Catalog Dashboard. Fill tenant, dates, Ejari number; save as Draft.

2. **Submit & Activate**  
   On the Ejari form: **Submit** (Draft → Submitted), then **Activate** (→ Active). Only one Active Ejari per property/company is allowed.

3. **Renew**  
   Open an Ejari in Active / Expiring Soon / Expired. Click **Renew**, set new dates and options in the wizard, then **Create Renewal**. The old record is set to Renewed and linked to the new one.

4. **Expiry**  
   The scheduled action **Ejari Expiry Status Update** runs daily, updates statuses and creates To-Do activities for Ejari Managers. Optional email template sends reminders to tenants if configured.

## Integration (Catalog Dashboard)

On `product.template`:

- **Smart button**: `action_view_ejari_records()` — opens Ejari list for the product.
- **Create**: `action_create_ejari()` — opens new Ejari form with product and company set.
- **Renew**: `action_renew_ejari()` — opens renewal wizard if there is an active Ejari.
- **Display**: use computed fields `ejari_status`, `ejari_expiry_date`, `ejari_days_to_expire`, `ejari_ribbon` for badges and indicators.

## Extensibility

- Ejari is linked to **product.template** (room/unit service product). To support another model (e.g. property unit), add a Many2one and extend domains/actions in a dependent module.
- All business logic is in `ejari.record` and the renewal wizard for easy override or extension.

## License

LGPL-3.
