# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderCatalogWizard(models.TransientModel):
    _name = 'sale.order.catalog.wizard'
    _description = 'Add from Sales Catalog (Assets, Parking, Other Products)'

    order_id = fields.Many2one('sale.order', string='Order', required=True, ondelete='cascade')
    main_product_id = fields.Many2one(
        'product.product',
        string='Main Product',
        help='Product from first order line; catalog items linked to this product are shown.',
    )
    selected_asset_allocation_ids = fields.Many2many(
        'sales.catalog.asset.allocation',
        'sale_order_catalog_wizard_asset_rel',
        'wizard_id',
        'allocation_id',
        string='Assets to add',
        domain="[('parent_product_id', '=', main_product_id)]",
    )
    selected_parking_allocation_ids = fields.Many2many(
        'sales.catalog.parking.allocation',
        'sale_order_catalog_wizard_parking_rel',
        'wizard_id',
        'allocation_id',
        string='Parking to add',
        domain="[('parent_product_id', '=', main_product_id)]",
    )
    selected_other_item_ids = fields.Many2many(
        'product.product.other.item',
        'sale_order_catalog_wizard_other_rel',
        'wizard_id',
        'other_item_id',
        string='Other products to add',
        domain="[('parent_product_id', '=', main_product_id)]",
    )

    def action_add_to_order(self):
        self.ensure_one()
        if not self.order_id or not self.main_product_id:
            raise UserError(_('Please set the main product (first order line) first.'))
        order = self.order_id
        existing_product_ids = set(order.order_line.mapped('product_id').ids)
        commands = []
        for alloc in self.selected_asset_allocation_ids:
            pid = alloc.asset_product_id.id
            if pid in existing_product_ids:
                continue
            commands.append((0, 0, {
                'product_id': pid,
                'product_uom_qty': alloc.quantity,
                'product_uom_id': alloc.asset_product_id.uom_id.id,
            }))
            existing_product_ids.add(pid)
        for alloc in self.selected_parking_allocation_ids:
            pid = alloc.parking_product_id.id
            if pid in existing_product_ids:
                continue
            commands.append((0, 0, {
                'product_id': pid,
                'product_uom_qty': alloc.quantity,
                'product_uom_id': alloc.parking_product_id.uom_id.id,
            }))
            existing_product_ids.add(pid)
        for item in self.selected_other_item_ids:
            pid = item.product_id.id
            if pid in existing_product_ids:
                continue
            commands.append((0, 0, {
                'product_id': pid,
                'product_uom_qty': item.quantity,
                'product_uom_id': item.uom_id.id,
                'price_unit': item.price_unit,
            }))
            existing_product_ids.add(pid)
        if commands:
            order.write({'order_line': commands})
        return {'type': 'ir.actions.act_window_close'}
