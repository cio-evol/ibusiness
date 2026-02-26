# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _


class ProductProduct(models.Model):
    _inherit = "product.product"

    # Related from template so Ejari tab works on product.product (e.g. Sales Catalog Dashboard form)
    ejari_record_ids = fields.One2many(
        related="product_tmpl_id.ejari_record_ids",
        string="Ejari Records",
    )
    ejari_count = fields.Integer(related="product_tmpl_id.ejari_count", string="Ejari Count")
    ejari_active_id = fields.Many2one(related="product_tmpl_id.ejari_active_id", string="Active Ejari")
    ejari_status = fields.Selection(related="product_tmpl_id.ejari_status", string="Ejari Status")
    ejari_expiry_date = fields.Date(related="product_tmpl_id.ejari_expiry_date", string="Ejari Expiry Date")
    ejari_days_to_expire = fields.Integer(
        related="product_tmpl_id.ejari_days_to_expire",
        string="Days to Ejari Expiry",
    )
    ejari_ribbon = fields.Char(related="product_tmpl_id.ejari_ribbon", string="Ejari Ribbon")
    ejari_selected_id = fields.Many2one(related="product_tmpl_id.ejari_selected_id", string="Selected Ejari", readonly=False)

    def action_view_ejari_records(self):
        self.ensure_one()
        return self.product_tmpl_id.action_view_ejari_records()

    def action_create_ejari(self):
        self.ensure_one()
        return self.product_tmpl_id.action_create_ejari()

