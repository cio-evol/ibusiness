# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _add_catalog_lines_if_rental(self):
        """Automatically add assets, parking, and other products from Sales Catalog to this order."""
        for line in self:
            if not line.product_id or not line.order_id:
                continue
            product = line.product_id
            has_catalog = (
                product.allocated_asset_ids
                or product.allocated_parking_ids
                or product.other_item_ids
            )
            if not has_catalog:
                continue
            is_rental = getattr(line, 'is_rental', False) or getattr(
                line.order_id, 'is_rental_order', False
            )
            if not is_rental:
                continue
            extra_commands = line.order_id._get_catalog_order_line_commands(product.id)
            if not extra_commands:
                continue
            # Avoid duplicates: only add products not already on the order
            existing_product_ids = set(line.order_id.order_line.mapped('product_id').ids)
            new_commands = []
            for cmd in extra_commands:
                if cmd[0] != 0:
                    continue
                pid = cmd[2].get('product_id')
                if pid and pid not in existing_product_ids:
                    new_commands.append(cmd)
                    existing_product_ids.add(pid)
            if new_commands:
                line.order_id.write({'order_line': new_commands})

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._add_catalog_lines_if_rental()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'product_id' in vals:
            self._add_catalog_lines_if_rental()
        return res
