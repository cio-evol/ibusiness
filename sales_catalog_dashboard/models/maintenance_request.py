from odoo import models, fields

class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    product_id = fields.Many2one('product.product', string='Product')
