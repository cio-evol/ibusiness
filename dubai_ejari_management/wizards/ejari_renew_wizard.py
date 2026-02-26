# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class EjariRenewWizard(models.TransientModel):
    _name = "ejari.renew.wizard"
    _description = "Ejari Renewal Wizard"

    ejari_id = fields.Many2one(
        "ejari.record",
        string="Current Ejari",
        required=True,
        readonly=True,
    )
    new_start_date = fields.Date(
        string="New Contract Start Date",
        required=True,
    )
    new_end_date = fields.Date(
        string="New Contract End Date",
        required=True,
    )
    new_issue_date = fields.Date(
        string="New Issue Date",
        required=True,
        help="Expiry date will be computed automatically as Issue Date + 365 days.",
    )
    new_ejari_number = fields.Char(
        string="New Ejari Number",
        help="If left empty, a placeholder will be used; you can edit after creation.",
    )
    copy_attachments = fields.Boolean(
        string="Copy Attachments",
        default=True,
        help="If enabled, copy attachments from previous Ejari to the new one.",
    )
    activate_immediately = fields.Boolean(
        string="Activate Immediately",
        default=False,
        help="If enabled, new Ejari will be set directly to Active status.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        if active_model == "ejari.record" and active_id:
            ejari = self.env["ejari.record"].browse(active_id)
            res["ejari_id"] = ejari.id
            base_date = ejari.expiry_date or ejari.contract_end_date
            if base_date:
                res["new_start_date"] = base_date + timedelta(days=1)
            else:
                res["new_start_date"] = ejari.contract_start_date
            if res.get("new_start_date"):
                res["new_end_date"] = res["new_start_date"] + timedelta(days=365)
                # Default new issue date equal to new contract start
                res["new_issue_date"] = res["new_start_date"]
        return res

    @api.constrains("new_start_date", "new_end_date")
    def _check_dates(self):
        for w in self:
            if w.new_start_date and w.new_end_date and w.new_end_date < w.new_start_date:
                raise ValidationError(
                    _("New contract end date cannot be before new start date.")
                )

    def action_confirm(self):
        self.ensure_one()
        ejari = self.ejari_id
        if not ejari:
            raise ValidationError(_("No Ejari record found to renew."))

        vals = {
            "company_id": ejari.company_id.id,
            "property_product_tmpl_id": ejari.property_product_tmpl_id.id,
            "tenant_partner_id": ejari.tenant_partner_id.id,
            "landlord_partner_id": ejari.landlord_partner_id.id or False,
            "contract_start_date": self.new_start_date,
            "contract_end_date": self.new_end_date,
            "issue_date": self.new_issue_date,
            "ejari_number": self.new_ejari_number or ejari.ejari_number or _("To define"),
            "status": "active" if self.activate_immediately else "draft",
            "notes": ejari.notes,
        }
        new_ejari = self.env["ejari.record"].create(vals)

        if self.copy_attachments and ejari.attachment_ids:
            new_ejari.attachment_ids = [(6, 0, ejari.attachment_ids.ids)]

        ejari.status = "expired"

        ejari.message_post(
            body=_(
                "New Ejari created: <a href=# data-oe-model='ejari.record' "
                "data-oe-id='%(id)d'>%(name)s</a>. This record set to Expired."
            )
            % {"id": new_ejari.id, "name": new_ejari.name}
        )
        new_ejari.message_post(
            body=_(
                "Ejari created (replacing <a href=# data-oe-model='ejari.record' "
                "data-oe-id='%(id)d'>%(name)s</a>)."
            )
            % {"id": ejari.id, "name": ejari.name}
        )

        return {
            "name": _("Ejari"),
            "type": "ir.actions.act_window",
            "res_model": "ejari.record",
            "view_mode": "form",
            "res_id": new_ejari.id,
            "target": "current",
        }
