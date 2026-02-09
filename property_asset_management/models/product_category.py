# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    sync_property = fields.Boolean(
        string='Is Property',
        default=False,
        help='If enabled, treat this product category as a property.',
    )
    property_id = fields.Many2one(
        'property.property',
        string='Property',
        ondelete='set null',
        index=True,
    )
    asset_assignment_ids = fields.One2many(
        'asset.assignment',
        'property_category_id',
        string='Asset Assignments',
    )
    account_stock_variation_id = fields.Many2one(
        'account.account',
        string='Stock Variation Account',
        ondelete='set null',
        help='Compatibility field for custom views referencing account stock variation.',
    )
