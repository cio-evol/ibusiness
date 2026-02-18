from odoo import models, fields

class ProductCategory(models.Model):
    _inherit = 'product.category'

    visible_on_sales_catalog = fields.Boolean(
        string='Visible on Sales Catalog Dashboard',
        default=True,
        help='If checked, this category will appear in the Sales Catalog Dashboard category filter'
    )
