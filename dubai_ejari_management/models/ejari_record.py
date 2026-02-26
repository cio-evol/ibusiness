# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class EjariRecord(models.Model):
    _name = "ejari.record"
    _description = "Ejari Record"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "expiry_date desc, id desc"

    name = fields.Char(
        string="Ejari Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    property_product_tmpl_id = fields.Many2one(
        "product.template",
        string="Property / Unit",
        required=True,
        index=True,
        tracking=True,
        help="Rentable unit/room/service product this Ejari applies to.",
    )
    tenant_partner_id = fields.Many2one(
        "res.partner",
        string="Tenant",
        required=True,
        index=True,
        tracking=True,
        help="Tenant associated with this Ejari contract.",
    )
    landlord_partner_id = fields.Many2one(
        "res.partner",
        string="Landlord",
        tracking=True,
        help="Optional landlord. Can be the operating company or an external owner.",
    )
    ejari_number = fields.Char(
        string="Ejari Number",
        required=True,
        tracking=True,
        help="Official Ejari number. Must be unique per company.",
    )
    contract_start_date = fields.Date(
        string="Contract Start Date",
        required=True,
        tracking=True,
    )
    contract_end_date = fields.Date(
        string="Contract End Date",
        required=True,
        tracking=True,
    )
    issue_date = fields.Date(
        string="Issue Date",
        required=True,
        tracking=True,
        help="Issue date of the Ejari certificate. Expiry is computed as Issue Date + 365 days.",
    )
    expiry_date = fields.Date(
        string="Expiry Date",
        tracking=True,
        compute="_compute_expiry_date",
        store=True,
        help="Computed as Issue Date + 365 days.",
    )
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("active", "Active"),
            ("expiring_soon", "Expiring Soon"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        required=True,
    )
    notes = fields.Text(string="Internal Notes")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ejari_record_ir_attachments_rel",
        "ejari_id",
        "attachment_id",
        string="Attachments",
        help="Store Ejari certificates, contracts, and related documents here.",
    )
    color = fields.Integer(string="Color Index")
    active = fields.Boolean(default=True, tracking=True)

    days_to_expire = fields.Integer(
        string="Days to Expire",
        compute="_compute_days_and_flags",
        store=True,
    )
    expiring_flag = fields.Boolean(
        string="Expiring Soon?",
        compute="_compute_days_and_flags",
        store=True,
    )
    expired_flag = fields.Boolean(
        string="Expired?",
        compute="_compute_days_and_flags",
        store=True,
    )

    property_default_code = fields.Char(
        related="property_product_tmpl_id.default_code",
        store=True,
        readonly=True,
    )
    property_name = fields.Char(
        related="property_product_tmpl_id.name",
        store=True,
        readonly=True,
    )
    property_ref = fields.Char(
        string="Property Reference",
        compute="_compute_property_ref",
        store=True,
        help="Convenient reference combining property code and name.",
    )

    _sql_constraints = [
        (
            "ejari_number_company_unique",
            "unique(company_id, ejari_number)",
            "Ejari number must be unique per company.",
        ),
    ]

    @api.depends(
        "property_product_tmpl_id",
        "property_product_tmpl_id.default_code",
        "property_product_tmpl_id.name",
    )
    def _compute_property_ref(self):
        for rec in self:
            tmpl = rec.property_product_tmpl_id
            if tmpl:
                parts = [p for p in [tmpl.default_code, tmpl.name] if p]
                rec.property_ref = " - ".join(parts)
            else:
                rec.property_ref = False

    @api.depends("issue_date")
    def _compute_expiry_date(self):
        """Expiry date is always Issue Date + 365 days."""
        for rec in self:
            if rec.issue_date:
                rec.expiry_date = rec.issue_date + timedelta(days=365)
            else:
                rec.expiry_date = False

    @api.depends("expiry_date", "company_id.ejari_expiry_warning_days")
    def _compute_days_and_flags(self):
        today = date.today()
        for rec in self:
            if rec.expiry_date:
                delta = (rec.expiry_date - today).days
                rec.days_to_expire = delta
                warning_days = rec.company_id.ejari_expiry_warning_days or 30
                rec.expired_flag = delta < 0
                rec.expiring_flag = 0 <= delta <= warning_days
            else:
                rec.days_to_expire = 0
                rec.expired_flag = False
                rec.expiring_flag = False

    @api.constrains("contract_start_date", "contract_end_date", "expiry_date")
    def _check_dates(self):
        for rec in self:
            if rec.contract_start_date and rec.contract_end_date:
                if rec.contract_end_date < rec.contract_start_date:
                    raise ValidationError(
                        _("Contract end date cannot be before contract start date.")
                    )
            if rec.contract_start_date and rec.expiry_date:
                if rec.expiry_date < rec.contract_start_date:
                    raise ValidationError(
                        _("Expiry date cannot be before contract start date.")
                    )

    @api.constrains("status", "property_product_tmpl_id", "company_id", "active")
    def _check_unique_active_per_property(self):
        """Ensure only one active Ejari per property per company."""
        for rec in self:
            if (
                rec.status == "active"
                and rec.property_product_tmpl_id
                and rec.company_id
                and rec.active
            ):
                domain = [
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("property_product_tmpl_id", "=", rec.property_product_tmpl_id.id),
                    ("status", "=", "active"),
                    ("active", "=", True),
                ]
                if self.search_count(domain):
                    raise ValidationError(
                        _(
                            "Only one active Ejari is allowed per property and company. "
                            "Please cancel or expire the other Ejari first."
                        )
                    )

    @api.model_create_multi
    def create(self, vals_list):
        """Support multi-create API in Odoo 19."""
        for vals in vals_list:
            if not vals.get("company_id"):
                vals["company_id"] = self.env.company.id
            if vals.get("name", _("New")) in (False, "/", _("New")):
                company = self.env["res.company"].browse(vals["company_id"])
                seq = (
                    self.env["ir.sequence"]
                    .with_company(company)
                    .next_by_code("ejari.record")
                )
                year = fields.Date.context_today(self).year
                # Use company name (no dedicated code field in Odoo 19)
                company_code = (company.name or "COMP")[:8]
                vals["name"] = f"EJARI/{company_code}/{year}/{seq}"
        records = super().create(vals_list)
        records._adjust_previous_active_ejari_on_activation()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "status" in vals:
            self._adjust_previous_active_ejari_on_activation()
        return res

    def _adjust_previous_active_ejari_on_activation(self):
        """When an Ejari becomes active, mark previous active ones as expired."""
        for rec in self:
            if rec.status != "active" or not rec.property_product_tmpl_id or not rec.company_id:
                continue
            domain = [
                ("id", "!=", rec.id),
                ("company_id", "=", rec.company_id.id),
                ("property_product_tmpl_id", "=", rec.property_product_tmpl_id.id),
                ("status", "in", ["active", "expiring_soon"]),
                ("active", "=", True),
            ]
            previous_records = self.search(domain)
            previous_records.write({"status": "expired"})

    def action_submit(self):
        for rec in self:
            if rec.status != "draft":
                continue
            rec.status = "submitted"
            rec.message_post(body=_("Ejari submitted for approval."))
        return True

    def action_activate(self):
        for rec in self:
            if rec.status not in ("submitted", "draft", "expiring_soon"):
                continue
            rec.status = "active"
            rec.message_post(body=_("Ejari activated."))
        self._adjust_previous_active_ejari_on_activation()
        return True

    def action_cancel(self):
        for rec in self:
            if rec.status == "cancelled":
                continue
            rec.status = "cancelled"
            rec.message_post(body=_("Ejari cancelled."))
        return True

    @api.model
    def _cron_update_ejari_status(self):
        """Daily cron: update status based on expiry date and create activities."""
        today = date.today()
        Activity = self.env["mail.activity"]
        todo_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        manager_group = self.env.ref(
            "dubai_ejari_management.group_ejari_manager",
            raise_if_not_found=False,
        )

        for company in self.env["res.company"].search([]):
            warning_days = company.ejari_expiry_warning_days or 30

            expired_domain = [
                ("company_id", "=", company.id),
                ("active", "=", True),
                ("status", "not in", ["cancelled", "expired"]),
                ("expiry_date", "<", today),
            ]
            expired_records = self.search(expired_domain)
            expired_records.write({"status": "expired"})

            soon_domain = [
                ("company_id", "=", company.id),
                ("active", "=", True),
                ("status", "in", ["active", "submitted"]),
                ("expiry_date", ">=", today),
                ("expiry_date", "<=", date.fromordinal(today.toordinal() + warning_days)),
            ]
            soon_records = self.search(soon_domain)
            soon_records.write({"status": "expiring_soon"})

            if todo_type and manager_group:
                manager_users = self.env["res.users"].search(
                    [
                        ("company_ids", "in", company.ids),
                        ("groups_id", "in", manager_group.ids),
                    ]
                )
                for rec in expired_records | soon_records:
                    for user in manager_users:
                        existing = Activity.search(
                            [
                                ("res_model", "=", rec._name),
                                ("res_id", "=", rec.id),
                                ("user_id", "=", user.id),
                                ("activity_type_id", "=", todo_type.id),
                                ("date_deadline", "=", today),
                            ],
                            limit=1,
                        )
                        if not existing:
                            rec.activity_schedule(
                                activity_type_id=todo_type.id,
                                user_id=user.id,
                                date_deadline=today,
                                summary=_("Ejari expiring or expired"),
                                note=_(
                                    "Ejari %(name)s (%(ejari)s) for property %(prop)s "
                                    "is expiring or has expired."
                                )
                                % {
                                    "name": rec.name,
                                    "ejari": rec.ejari_number or "",
                                    "prop": rec.property_ref or "",
                                },
                            )

            template = self.env.ref(
                "dubai_ejari_management.email_template_ejari_expiry",
                raise_if_not_found=False,
            )
            if template:
                for rec in expired_records | soon_records:
                    if rec.tenant_partner_id and rec.tenant_partner_id.email:
                        template.send_mail(rec.id, force_send=False, raise_exception=False)
