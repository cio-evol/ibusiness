# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProductScheduleWizard(models.TransientModel):
    _name = 'product.schedule.wizard'
    _description = 'Schedule: Select Date Range & Create Quotation'

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='cascade',
    )
    start_datetime = fields.Datetime(
        string='Start Date & Time',
        required=True,
        help='Start of the rental or service period.',
    )
    end_datetime = fields.Datetime(
        string='End Date & Time',
        required=True,
        help='End of the rental or service period.',
    )

    def action_confirm(self):
        self.ensure_one()
        if self.end_datetime <= self.start_datetime:
            raise UserError(_(
                'End Date & Time must be after Start Date & Time. '
                'Please select a valid range.'
            ))
        return self._create_quotation()

    def _create_quotation(self):
        self.ensure_one()
        product = self.product_id
        is_rental = bool(getattr(product, 'rent_ok', False))

        # 1. Rental/Service duration from selected start/end stored on SO
        order_vals = {
            'partner_id': False,
            'order_line': [
                (0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': 1.0,  # 2. Order line: current product, 3. Quantity: 1
                }),
            ],
        }
        if is_rental:
            order_vals['is_rental_order'] = True
            order_vals['rental_start_date'] = self.start_datetime
            order_vals['rental_return_date'] = self.end_datetime

        order = self.env['sale.order'].with_context(
            in_rental_app=is_rental,
        ).create(order_vals)

        return {
            'name': _('Quotation'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }
