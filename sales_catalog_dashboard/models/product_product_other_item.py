# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductProductOtherItem(models.Model):
    _name = 'product.product.other.item'
    _description = 'Product Other Items Line'

    parent_product_id = fields.Many2one(
        'product.product',
        string='Product',
        ondelete='cascade',
        required=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='restrict',
    )
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True,
    )
    price_unit = fields.Float(string='Unit Price', required=True, default=0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            if self.product_id.list_price:
                self.price_unit = self.product_id.list_price
