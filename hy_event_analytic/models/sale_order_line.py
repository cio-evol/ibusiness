# -*- coding: utf-8 -*-

from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Set analytic distribution to 100% when product has analytic account"""
        res = super()._onchange_product_id()
        if self.product_id and self.product_id.product_tmpl_id.analytic_account_id:
            # Set analytic distribution to 100% for the product's analytic account
            self.analytic_distribution = {
                self.product_id.product_tmpl_id.analytic_account_id.id: 100
            }
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Set analytic distribution on create if product has analytic account"""
        lines = super().create(vals_list)
        for line in lines:
            if line.product_id and line.product_id.product_tmpl_id.analytic_account_id:
                if not line.analytic_distribution:
                    line.analytic_distribution = {
                        line.product_id.product_tmpl_id.analytic_account_id.id: 100
                    }
        return lines

    def write(self, vals):
        """Set analytic distribution on write if product is changed and has analytic account"""
        res = super().write(vals)
        if 'product_id' in vals:
            for line in self:
                if line.product_id and line.product_id.product_tmpl_id.analytic_account_id:
                    if not line.analytic_distribution:
                        line.analytic_distribution = {
                            line.product_id.product_tmpl_id.analytic_account_id.id: 100
                        }
        return res

