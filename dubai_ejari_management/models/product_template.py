# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = "product.template"

    ejari_record_ids = fields.One2many(
        "ejari.record",
        "property_product_tmpl_id",
        string="Ejari Records",
    )
    ejari_selected_id = fields.Many2one(
        "ejari.record",
        string="Selected Ejari",
        help="Select which Ejari record to use for this property.",
    )
    ejari_count = fields.Integer(
        string="Ejari Count",
        compute="_compute_ejari_status",
    )
    ejari_active_id = fields.Many2one(
        "ejari.record",
        string="Active Ejari",
        compute="_compute_ejari_status",
    )
    ejari_status = fields.Selection(
        [
            ("none", "No Ejari"),
            ("active", "Active"),
            ("expiring_soon", "Expiring Soon"),
            ("expired", "Expired"),
        ],
        string="Ejari Status",
        compute="_compute_ejari_status",
        store=False,
    )
    ejari_expiry_date = fields.Date(
        string="Ejari Expiry Date",
        compute="_compute_ejari_status",
        store=False,
    )
    ejari_days_to_expire = fields.Integer(
        string="Days to Ejari Expiry",
        compute="_compute_ejari_status",
        store=False,
    )
    ejari_ribbon = fields.Char(
        string="Ejari Ribbon",
        compute="_compute_ejari_status",
        store=False,
        help="Text used by the ribbon widget to show Ejari status indicators.",
    )

    @api.depends(
        "ejari_record_ids.status",
        "ejari_record_ids.expiry_date",
        "ejari_record_ids.days_to_expire",
        "ejari_selected_id",
    )
    def _compute_ejari_status(self):
        for product in self:
            recs = product.ejari_record_ids.filtered(lambda r: r.active)
            product.ejari_count = len(recs)
            if product.ejari_selected_id and product.ejari_selected_id in recs:
                product.ejari_active_id = product.ejari_selected_id
            else:
                active_rec = recs.filtered(lambda r: r.status in ("active", "expiring_soon"))
                if not active_rec:
                    expired_rec = recs.filtered(lambda r: r.status == "expired")
                    product.ejari_active_id = expired_rec[:1]
                else:
                    product.ejari_active_id = active_rec.sorted("expiry_date")[:1]
            ejari = product.ejari_active_id

            if not ejari:
                product.ejari_status = "none"
                product.ejari_expiry_date = False
                product.ejari_days_to_expire = 0
                product.ejari_ribbon = False
                continue

            product.ejari_expiry_date = ejari.expiry_date
            product.ejari_days_to_expire = ejari.days_to_expire

            if ejari.status == "expiring_soon":
                product.ejari_status = "expiring_soon"
                product.ejari_ribbon = _("EJARI ACTIVE - expires in %(days)s day(s)") % {
                    "days": ejari.days_to_expire
                }
            elif ejari.status == "active":
                product.ejari_status = "active"
                product.ejari_ribbon = _("EJARI ACTIVE - expires in %(days)s day(s)") % {
                    "days": ejari.days_to_expire
                }
            elif ejari.status == "expired":
                product.ejari_status = "expired"
                product.ejari_ribbon = _("EJARI EXPIRED")
            else:
                product.ejari_status = "none"
                product.ejari_ribbon = False

    def action_view_ejari_records(self):
        self.ensure_one()
        action = self.env.ref("dubai_ejari_management.action_ejari_record").read()[0]
        action["domain"] = [("property_product_tmpl_id", "=", self.id)]
        action["context"] = {
            "default_property_product_tmpl_id": self.id,
            "default_company_id": self.env.company.id,
        }
        return action

    def action_create_ejari(self):
        self.ensure_one()
        return {
            "name": _("Create Ejari"),
            "type": "ir.actions.act_window",
            "res_model": "ejari.record",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_property_product_tmpl_id": self.id,
                "default_company_id": self.env.company.id,
                "default_landlord_partner_id": self.env.company.partner_id.id,
            },
        }

