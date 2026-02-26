from odoo import models, fields

class StockLot(models.Model):
    _inherit = 'stock.lot'

    property_id = fields.Many2one(
        'product.product', 
        string='Property',
        domain="[('is_property', '=', True)]"
    )
