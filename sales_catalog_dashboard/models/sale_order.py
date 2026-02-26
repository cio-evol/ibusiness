# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_catalog_order_line_commands(self, main_product_id):
        """Build (0, 0, line_vals) for assets, parking, and other items; one line per product with total qty."""
        if not main_product_id:
            return []
        ProductProduct = self.env['product.product']
        product = ProductProduct.browse(main_product_id).exists()
        if not product:
            return []
        # One line per product_id: total qty, first uom_id and price_unit seen
        by_product = {}
        for alloc in product.allocated_asset_ids:
            pid = alloc.asset_product_id.id
            if pid not in by_product:
                by_product[pid] = {'product_uom_id': alloc.asset_product_id.uom_id.id, 'product_uom_qty': 0.0, 'price_unit': None}
            by_product[pid]['product_uom_qty'] += alloc.quantity
        for alloc in product.allocated_parking_ids:
            pid = alloc.parking_product_id.id
            if pid not in by_product:
                by_product[pid] = {'product_uom_id': alloc.parking_product_id.uom_id.id, 'product_uom_qty': 0.0, 'price_unit': None}
            by_product[pid]['product_uom_qty'] += alloc.quantity
        for item in product.other_item_ids:
            pid = item.product_id.id
            if pid not in by_product:
                by_product[pid] = {'product_uom_id': item.uom_id.id, 'product_uom_qty': 0.0, 'price_unit': item.price_unit}
            by_product[pid]['product_uom_qty'] += item.quantity
            if by_product[pid]['price_unit'] is None:
                by_product[pid]['price_unit'] = item.price_unit
        lines = []
        for product_id, data in by_product.items():
            line_vals = {
                'product_id': product_id,
                'product_uom_id': data['product_uom_id'],
                'product_uom_qty': data['product_uom_qty'],
            }
            if data.get('price_unit') is not None:
                line_vals['price_unit'] = data['price_unit']
            lines.append((0, 0, line_vals))
        return lines

    @api.model_create_multi
    def create(self, vals_list):
        # Only for rental orders: add assets, parking, other items from Sales Catalog when first line has a product
        for vals in vals_list:
            if not vals.get('is_rental_order'):
                continue
            order_line = vals.get('order_line') or []
            if not order_line:
                continue
            first = order_line[0]
            if isinstance(first, (list, tuple)) and len(first) >= 3 and first[0] == 0 and first[1] == 0:
                line_vals = first[2]
                main_product_id = line_vals.get('product_id')
                extra = self._get_catalog_order_line_commands(main_product_id)
                if extra:
                    vals['order_line'] = order_line + extra
        return super().create(vals_list)

    def action_open_catalog_wizard(self):
        """Open wizard to select assets, parking, other products linked to main product."""
        self.ensure_one()
        main_product = self.order_line[:1].product_id if self.order_line else self.env['product.product']
        return {
            'name': _('Add from Catalog'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.catalog.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_main_product_id': main_product.id if main_product else False,
            },
        }
